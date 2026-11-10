"""Archived additive-phase encoder retained only as the Qold control."""

from __future__ import annotations

import math

import torch


SPATIAL_QUBITS = (0, 1, 2, 3)
ACTION_QUBITS = (4, 5)


def density_amplitudes(density: torch.Tensor, epsilon: float = 1e-8) -> torch.Tensor:
    """Return normalized real amplitudes for the sixteen 4x4 cells."""

    density = torch.as_tensor(density, dtype=torch.float32)
    if density.shape[-2:] != (4, 4):
        raise ValueError("density amplitude encoding requires a 4x4 map")
    probabilities = torch.clamp(density.reshape(-1, 16), min=0.0) + float(epsilon)
    probabilities = probabilities / probabilities.sum(dim=1, keepdim=True)
    amplitudes = torch.sqrt(probabilities).to(torch.complex64)
    return amplitudes / torch.linalg.vector_norm(amplitudes, dim=1, keepdim=True)


def initial_six_qubit_state(density: torch.Tensor, epsilon: float = 1e-8) -> torch.Tensor:
    amplitudes = density_amplitudes(density, epsilon)
    state = torch.zeros((len(amplitudes), 64), dtype=torch.complex64, device=amplitudes.device)
    tensor = state.reshape(len(amplitudes), 2, 2, 2, 2, 2, 2)
    tensor[:, :, :, :, :, 0, 0] = amplitudes.reshape(len(amplitudes), 2, 2, 2, 2)
    return tensor.reshape(len(amplitudes), 64)


def fixed_layer_phase_maps(spatial: torch.Tensor) -> torch.Tensor:
    """Return the three pre-registered layer maps in the interval [-pi, pi]."""

    spatial = torch.as_tensor(spatial, dtype=torch.float32)
    if spatial.shape[-3:] != (7, 4, 4):
        raise ValueError("joint encoding requires seven aligned 4x4 channels")
    _density, workload, mask, boundary, interaction_dq, interaction_qb, interaction_dqb = spatial.unbind(dim=-3)
    workload_phase = math.pi * torch.clamp(workload, 0.0, 1.0)
    geometry_phase = math.pi * torch.clamp((mask + boundary) / 2.0, -1.0, 1.0)
    interaction_phase = math.pi * torch.clamp(
        interaction_dq + interaction_qb + interaction_dqb, 0.0, 1.0
    )
    return torch.stack((workload_phase, geometry_phase, interaction_phase), dim=1)


def apply_spatial_diagonal_phase(state: torch.Tensor, phase_map: torch.Tensor) -> torch.Tensor:
    """Apply a data-dependent diagonal unitary to q0-q3."""

    phase = torch.exp(torch.complex(torch.zeros_like(phase_map), phase_map)).reshape(-1, 16, 1)
    return (state.reshape(-1, 16, 4) * phase).reshape(-1, 64)


def spatial_bit_phase_features(phase_map: torch.Tensor) -> torch.Tensor:
    """Project cell phases onto the four spatial bit parities."""

    flat = phase_map.reshape(-1, 16)
    indices = torch.arange(16, device=flat.device)
    bit_positions = torch.arange(3, -1, -1, device=flat.device)
    bits = ((indices[:, None] >> bit_positions[None, :]) & 1).to(flat.dtype)
    signs = 1.0 - 2.0 * bits
    return (flat @ signs) / (16.0 * math.pi)


def state_preparation_metadata() -> dict[str, object]:
    return {
        "spatial_qubits": 4,
        "basis_states": 16,
        "full_statevector_amplitudes": 64,
        "per_pair_cost_model": "O(16) amplitude construction plus O(64) state initialization",
        "amplitude_loading": "custom CPU statevector initialization",
        "state_preparation_cost_reported": True,
        "qpu_acceleration_claimed": False,
        "status": "archived_failed_control",
    }
