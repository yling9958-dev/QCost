"""Channel-preserving signed tensor amplitude encoding (CST-QE)."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import torch

from .gates import _apply_single_qubit_gate, ry_gate, rz_gate


CHANNEL_NAMES = ("P", "W", "M", "B", "I_DQ", "I_QB", "I_DQB")
CHANNEL_COUNT = 7
SPATIAL_CELLS = 16
AMPLITUDE_DIMENSION = 128
TOTAL_QUBITS = 8


def basis_index(channel: int, row: int, column: int) -> int:
    """Map |row bits,column bits,channel bits> to the q0..q6 index."""

    return (((int(row) << 2) | int(column)) << 3) | int(channel)


@dataclass(frozen=True)
class ChannelTensorStatistics:
    channel_mean: np.ndarray
    channel_std: np.ndarray
    global_log_norm_mean: float
    global_log_norm_std: float
    selected_channels: tuple[int, ...]
    clip: float = 3.0

    def to_dict(self) -> dict[str, object]:
        return {
            "channel_names": list(CHANNEL_NAMES),
            "channel_mean": self.channel_mean.tolist(),
            "channel_std": self.channel_std.tolist(),
            "global_log_norm_mean": self.global_log_norm_mean,
            "global_log_norm_std": self.global_log_norm_std,
            "selected_channels": list(self.selected_channels),
            "clip": self.clip,
            "fit_split": "quantum_development_train",
        }


class ChannelTensorNormalizer:
    """Per-channel statistics fitted only on quantum development training data."""

    def __init__(self, selected_channels=tuple(range(CHANNEL_COUNT)), clip=3.0):
        self.selected_channels = tuple(int(value) for value in selected_channels)
        self.clip = float(clip)
        self.statistics: ChannelTensorStatistics | None = None

    def fit(self, tensors: np.ndarray) -> "ChannelTensorNormalizer":
        values = np.asarray(tensors, dtype=np.float64)
        if values.shape[-3:] != (CHANNEL_COUNT, 4, 4):
            raise ValueError("CST-QE expects tensors with shape (...,7,4,4)")
        flat = values.reshape(-1, CHANNEL_COUNT, SPATIAL_CELLS)
        means = flat.mean(axis=(0, 2))
        scales = flat.std(axis=(0, 2))
        scales[scales < 1e-8] = 1.0
        standardized = np.clip(
            (flat - means[None, :, None]) / scales[None, :, None],
            -self.clip,
            self.clip,
        ) / self.clip
        channel_mask = np.zeros(CHANNEL_COUNT, dtype=np.float64)
        channel_mask[list(self.selected_channels)] = 1.0
        standardized *= channel_mask[None, :, None]
        log_norms = np.log1p(np.linalg.norm(standardized.reshape(len(standardized), -1), axis=1))
        norm_std = float(log_norms.std())
        self.statistics = ChannelTensorStatistics(
            means,
            scales,
            float(log_norms.mean()),
            norm_std if norm_std >= 1e-8 else 1.0,
            self.selected_channels,
            self.clip,
        )
        return self

    def _stats(self) -> ChannelTensorStatistics:
        if self.statistics is None:
            raise RuntimeError("normalizer must be fitted on development train data")
        return self.statistics

    def transform(self, tensors: np.ndarray | torch.Tensor) -> torch.Tensor:
        stats = self._stats()
        values = torch.as_tensor(tensors, dtype=torch.float32)
        if values.shape[-3:] != (CHANNEL_COUNT, 4, 4):
            raise ValueError("CST-QE expects tensors with shape (...,7,4,4)")
        means = torch.as_tensor(stats.channel_mean, dtype=values.dtype, device=values.device).reshape(7, 1, 1)
        scales = torch.as_tensor(stats.channel_std, dtype=values.dtype, device=values.device).reshape(7, 1, 1)
        result = torch.clamp((values - means) / scales, -stats.clip, stats.clip) / stats.clip
        mask = torch.zeros(7, dtype=values.dtype, device=values.device)
        mask[list(stats.selected_channels)] = 1.0
        return result * mask.reshape(7, 1, 1)

    def amplitude_state(self, tensors) -> tuple[torch.Tensor, torch.Tensor]:
        standardized = self.transform(tensors)
        leading = standardized.shape[:-3]
        flat = standardized.reshape(-1, CHANNEL_COUNT, 4, 4)
        amplitudes = torch.zeros((len(flat), AMPLITUDE_DIMENSION), dtype=torch.float32, device=flat.device)
        for channel in range(CHANNEL_COUNT):
            for row in range(4):
                for column in range(4):
                    amplitudes[:, basis_index(channel, row, column)] = flat[:, channel, row, column]
        norms = torch.linalg.vector_norm(amplitudes, dim=1)
        zero = norms < 1e-12
        amplitudes = amplitudes / torch.where(zero, torch.ones_like(norms), norms)[:, None]
        if torch.any(zero):
            amplitudes[zero, 0] = 1.0
        return amplitudes.reshape(*leading, AMPLITUDE_DIMENSION), norms.reshape(*leading)

    def reconstruct_normalized(self, amplitudes) -> torch.Tensor:
        values = torch.as_tensor(amplitudes)
        if values.shape[-1] != AMPLITUDE_DIMENSION:
            raise ValueError("CST amplitude state must have dimension 128")
        leading = values.shape[:-1]
        flat = values.reshape(-1, AMPLITUDE_DIMENSION).real
        result = torch.zeros((len(flat), CHANNEL_COUNT, 4, 4), dtype=flat.dtype, device=flat.device)
        for channel in range(CHANNEL_COUNT):
            for row in range(4):
                for column in range(4):
                    result[:, channel, row, column] = flat[:, basis_index(channel, row, column)]
        return result.reshape(*leading, CHANNEL_COUNT, 4, 4)

    def context_angles(self, tensors, axis_x, quantile) -> tuple[torch.Tensor, torch.Tensor]:
        stats = self._stats()
        _amplitudes, norms = self.amplitude_state(tensors)
        standardized = torch.clamp(
            (torch.log1p(norms) - stats.global_log_norm_mean) / stats.global_log_norm_std,
            -3.0,
            3.0,
        )
        theta_global = math.pi * standardized / 3.0
        axis = torch.as_tensor(axis_x, dtype=torch.float32, device=theta_global.device)
        quantile = torch.as_tensor(quantile, dtype=torch.float32, device=theta_global.device)
        theta_action = math.pi * ((2.0 * axis - 1.0) * 0.5 + quantile - 0.5)
        return theta_global, theta_action

    def eight_qubit_state(self, tensors, axis_x, quantile) -> torch.Tensor:
        amplitudes, _norms = self.amplitude_state(tensors)
        flat = amplitudes.reshape(-1, AMPLITUDE_DIMENSION).to(torch.complex64)
        state = torch.zeros((len(flat), 256), dtype=torch.complex64, device=flat.device)
        state.reshape(len(flat), AMPLITUDE_DIMENSION, 2)[:, :, 0] = flat
        theta_global, theta_action = self.context_angles(tensors, axis_x, quantile)
        state = _apply_single_qubit_gate(state, ry_gate(theta_global.reshape(-1)), 7, TOTAL_QUBITS)
        return _apply_single_qubit_gate(state, rz_gate(theta_action.reshape(-1)), 7, TOTAL_QUBITS)


def state_fidelity(states: torch.Tensor) -> torch.Tensor:
    states = torch.as_tensor(states, dtype=torch.complex64)
    return torch.abs(states.conj() @ states.T) ** 2


def centered_kernel_alignment(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.shape != right.shape or left.ndim != 2 or left.shape[0] != left.shape[1]:
        raise ValueError("kernel matrices must be equal square matrices")
    count = left.shape[0]
    center = np.eye(count) - np.ones((count, count)) / count
    left_centered = center @ left @ center
    right_centered = center @ right @ center
    denominator = np.linalg.norm(left_centered) * np.linalg.norm(right_centered)
    return float(np.sum(left_centered * right_centered) / denominator) if denominator > 1e-15 else 0.0


def encoding_metadata() -> dict[str, object]:
    return {
        "name": "CST-QE",
        "qubits": 8,
        "spatial_qubits": [0, 1, 2, 3],
        "channel_qubits": [4, 5, 6],
        "context_qubit": 7,
        "input_shape": [7, 4, 4],
        "amplitude_dimension": 128,
        "signed_amplitudes": True,
        "channel_identity_preserved": True,
        "qpu_speedup_claimed": False,
    }
