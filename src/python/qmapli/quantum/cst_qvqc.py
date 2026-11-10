"""Exact-budget Channel-Spatial Tensor variational quantum controller."""

from __future__ import annotations

import math

import torch
import torch.nn as nn

from .channel_tensor_encoding import ChannelTensorNormalizer
from .gates import _apply_single_qubit_gate, _apply_two_qubit_gate, ry_gate, rz_gate, two_qubit_gate


CST_OBSERVABLES = (
    "z0", "z1", "z2", "z3",
    "x0", "x1", "x2", "x3",
    "z4", "z5", "z6", "z7",
    "z4z0", "z4z2", "z5z1", "z5z3",
    "z7z0", "z7z2", "z4z5", "z5z6",
)


class CSTQuantumController(nn.Module):
    """Eight-qubit, three-layer, exactly 111-parameter CST-QVQC."""

    def __init__(
        self,
        normalizer: ChannelTensorNormalizer,
        *,
        variant: str = "full",
        topology: str = "channel_spatial_ring",
        seed: int = 42,
    ):
        super().__init__()
        if variant not in {"full", "no_entangle"}:
            raise ValueError(f"unknown CST-QVQC variant: {variant}")
        if topology not in {"channel_spatial_ring", "channel_spatial_alternating"}:
            raise ValueError(f"unknown channel-spatial topology: {topology}")
        if normalizer.statistics is None:
            raise ValueError("CST-QVQC requires a fitted train-only normalizer")
        self.normalizer = normalizer
        self.variant = variant
        self.topology = topology
        self.num_qubits = 8
        self.layers = 3
        self.observables = CST_OBSERVABLES
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.local_y = nn.Parameter(0.05 * torch.randn(3, 8))
            self.local_z = nn.Parameter(0.05 * torch.randn(3, 8))
            self.spatial_mixing = nn.Parameter(0.05 * torch.randn(3, 4))
            self.channel_mixing = nn.Parameter(0.05 * torch.randn(3, 3))
            self.channel_spatial = nn.Parameter(0.05 * torch.randn(3, 4))
            self.action_interaction = nn.Parameter(0.05 * torch.randn(3, 3))
            self.readout = nn.Parameter(torch.randn(20) / math.sqrt(20))
            self.readout_bias = nn.Parameter(torch.zeros(()))
        if self.parameter_count != 111:
            raise AssertionError(f"CST-QVQC has {self.parameter_count} parameters, expected 111")

    @property
    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

    @staticmethod
    def _pauli(kind: str, device):
        if kind == "x":
            return torch.tensor([[0, 1], [1, 0]], dtype=torch.complex64, device=device)
        if kind == "z":
            return torch.tensor([[1, 0], [0, -1]], dtype=torch.complex64, device=device)
        raise ValueError(kind)

    def _expectation(self, state: torch.Tensor, specification: str) -> torch.Tensor:
        transformed = state
        cursor = 0
        while cursor < len(specification):
            kind = specification[cursor]
            cursor += 1
            digits = []
            while cursor < len(specification) and specification[cursor].isdigit():
                digits.append(specification[cursor])
                cursor += 1
            transformed = _apply_single_qubit_gate(
                transformed,
                self._pauli(kind, state.device),
                int("".join(digits)),
                self.num_qubits,
            )
        return torch.sum(state.conj() * transformed, dim=1).real

    def _controlled_or_local(self, state, angle, control, target):
        if self.variant == "full":
            return _apply_two_qubit_gate(
                state,
                two_qubit_gate("cry", angle, device=state.device),
                control,
                target,
                self.num_qubits,
            )
        # Exact parameter replacement: the same angle remains trainable.
        return _apply_single_qubit_gate(state, ry_gate(angle), target, self.num_qubits)

    def _masked_action_interaction(self, state, angle, axis_x, x_target, y_target):
        if self.variant == "full":
            updated_x = _apply_two_qubit_gate(
                state, two_qubit_gate("cry", angle, device=state.device), 7, x_target, 8
            )
            updated_y = _apply_two_qubit_gate(
                state, two_qubit_gate("cry", angle, device=state.device), 7, y_target, 8
            )
        else:
            updated_x = _apply_single_qubit_gate(state, ry_gate(angle), x_target, 8)
            updated_y = _apply_single_qubit_gate(state, ry_gate(angle), y_target, 8)
        return torch.where(axis_x[:, None], updated_x, updated_y)

    def statevector(self, scalar: torch.Tensor, spatial: torch.Tensor) -> torch.Tensor:
        scalar = torch.as_tensor(scalar, dtype=torch.float32)
        spatial = torch.as_tensor(spatial, dtype=torch.float32, device=scalar.device)
        axis_x = scalar[:, -5] >= scalar[:, -4]
        quantile = scalar[:, -3]
        state = self.normalizer.eight_qubit_state(spatial, axis_x.float(), quantile)
        spatial_pairs = ((0, 1), (1, 3), (3, 2), (2, 0))
        channel_pairs = ((4, 5), (5, 6), (6, 4))
        ring_pairs = ((4, 0), (5, 1), (6, 2), (4, 3))
        alternate_pairs = ((4, 2), (5, 3), (6, 0), (5, 1))
        for layer in range(self.layers):
            # Spatial and channel mixing preserve register identities while
            # allowing within-register correlations.
            for angle, (control, target) in zip(self.spatial_mixing[layer], spatial_pairs, strict=True):
                state = _apply_two_qubit_gate(
                    state, two_qubit_gate("cry", angle, device=state.device), control, target, 8
                )
            for angle, (control, target) in zip(self.channel_mixing[layer], channel_pairs, strict=True):
                state = _apply_two_qubit_gate(
                    state, two_qubit_gate("cry", angle, device=state.device), control, target, 8
                )
            pairs = ring_pairs if self.topology == "channel_spatial_ring" or layer % 2 == 0 else alternate_pairs
            for angle, (control, target) in zip(self.channel_spatial[layer], pairs, strict=True):
                state = self._controlled_or_local(state, angle, control, target)
            action_targets = ((2, 0), (3, 1), (2, 1))
            for angle, (x_target, y_target) in zip(
                self.action_interaction[layer], action_targets, strict=True
            ):
                state = self._masked_action_interaction(
                    state, angle, axis_x, x_target, y_target
                )
            for wire in range(8):
                state = _apply_single_qubit_gate(state, ry_gate(self.local_y[layer, wire]), wire, 8)
                state = _apply_single_qubit_gate(state, rz_gate(self.local_z[layer, wire]), wire, 8)
        return state

    def circuit_features(self, scalar, spatial) -> torch.Tensor:
        state = self.statevector(scalar, spatial)
        return torch.stack(
            [self._expectation(state, observable) for observable in self.observables],
            dim=1,
        )

    def forward(self, scalar, spatial) -> torch.Tensor:
        return self.circuit_features(scalar, spatial) @ self.readout + self.readout_bias


def cst_circuit_metadata() -> dict[str, object]:
    return {
        "name": "CST-QVQC",
        "qubits": 8,
        "layers": 3,
        "trainable_parameters": 111,
        "observables": list(CST_OBSERVABLES),
        "layer_order": [
            "spatial_mixing",
            "channel_mixing",
            "channel_spatial_interaction",
            "action_conditioned_interaction",
            "local_trainable_rotation",
        ],
    }
