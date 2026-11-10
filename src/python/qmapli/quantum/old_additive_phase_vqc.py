"""Archived 111-parameter additive-phase VQC retained as Qold."""

from __future__ import annotations

import math

import torch
import torch.nn as nn

from .gates import _apply_single_qubit_gate, _apply_two_qubit_gate, ry_gate, rz_gate, two_qubit_gate
from .old_additive_phase_encoder import (
    apply_spatial_diagonal_phase,
    fixed_layer_phase_maps,
    initial_six_qubit_state,
    spatial_bit_phase_features,
)


GEOMETRY_OBSERVABLES = (
    "z0", "z1", "z2", "z3", "z4", "z5",
    "x0", "x1", "x2", "x3", "x4", "x5",
    "z0z1", "z1z2", "z2z3", "z3z0",
    "z4z0", "z4z2", "z5z1", "z5z3",
)


def _fixed_projection(rows, columns, generator):
    matrix = torch.randn(rows, columns, generator=generator)
    return matrix / torch.clamp(torch.linalg.vector_norm(matrix, dim=1, keepdim=True), min=1e-6)


class OldAdditivePhaseVQC(nn.Module):
    """Joint Q1/Q2 circuit; only cross-register entanglement differs."""

    def __init__(self, scalar_size: int, *, variant="geometry", seed=42):
        super().__init__()
        if variant not in {"geometry", "no_entangle"}:
            raise ValueError(f"unknown geometry VQC variant: {variant}")
        self.variant = variant
        self.num_qubits = 6
        self.layers = 3
        self.observables = GEOMETRY_OBSERVABLES
        self.scalar_size = int(scalar_size)
        generator = torch.Generator().manual_seed(int(seed) + 813)
        self.register_buffer(
            "scalar_projection",
            torch.stack(
                [_fixed_projection(6, self.scalar_size, generator) for _ in range(self.layers)]
            ),
        )
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.theta_y = nn.Parameter(0.05 * torch.randn(3, 6))
            self.theta_z = nn.Parameter(0.05 * torch.randn(3, 6))
            self.encoding_scale = nn.Parameter(torch.ones(3, 6))
            self.encoding_bias = nn.Parameter(torch.zeros(3, 6))
            self.interaction_theta = nn.Parameter(0.05 * torch.randn(3, 6))
            self.readout = nn.Parameter(torch.randn(20) / math.sqrt(20))
            self.readout_bias = nn.Parameter(torch.zeros(()))
        if self.parameter_count != 111:
            raise AssertionError(f"geometry VQC parameter budget is {self.parameter_count}, expected 111")

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    @staticmethod
    def _pauli(name, device):
        if name == "x":
            return torch.tensor([[0, 1], [1, 0]], dtype=torch.complex64, device=device)
        if name == "z":
            return torch.tensor([[1, 0], [0, -1]], dtype=torch.complex64, device=device)
        raise ValueError(name)

    def _expectation(self, state, specification):
        transformed = state
        position = 0
        while position < len(specification):
            pauli = specification[position]
            position += 1
            digits = []
            while position < len(specification) and specification[position].isdigit():
                digits.append(specification[position])
                position += 1
            transformed = _apply_single_qubit_gate(
                transformed,
                self._pauli(pauli, state.device),
                int("".join(digits)),
                self.num_qubits,
            )
        return torch.sum(state.conj() * transformed, dim=1).real

    @staticmethod
    def _masked_two_qubit(state, theta, control, target, mask):
        updated = _apply_two_qubit_gate(
            state,
            two_qubit_gate("cry", theta, device=state.device),
            control,
            target,
            6,
        )
        return torch.where(mask[:, None], updated, state)

    @staticmethod
    def _masked_single(state, theta, target_x, target_y, axis_x):
        updated_x = _apply_single_qubit_gate(state, ry_gate(theta), target_x, 6)
        updated_y = _apply_single_qubit_gate(state, ry_gate(theta), target_y, 6)
        return torch.where(axis_x[:, None], updated_x, updated_y)

    def _interaction_layer(self, state, layer, axis_x):
        theta = self.interaction_theta[layer]
        if self.variant == "no_entangle":
            targets = ((2, 0), (3, 1), (3, 1), (2, 0), (4, 4), (3, 1))
            for value, (target_x, target_y) in zip(theta, targets, strict=True):
                state = self._masked_single(state, value, target_x, target_y, axis_x)
            return state
        specifications = (
            (4, 2, 4, 0),
            (5, 3, 5, 1),
            (4, 3, 4, 1),
            (5, 2, 5, 0),
            (4, 5, 4, 5),
            (2, 3, 0, 1),
        )
        for value, (control_x, target_x, control_y, target_y) in zip(theta, specifications, strict=True):
            if (control_x, target_x) == (control_y, target_y):
                state = _apply_two_qubit_gate(
                    state,
                    two_qubit_gate("cry", value, device=state.device),
                    control_x,
                    target_x,
                    6,
                )
                continue
            state = self._masked_two_qubit(state, value, control_x, target_x, axis_x)
            state = self._masked_two_qubit(state, value, control_y, target_y, ~axis_x)
        return state

    def statevector(self, scalar, spatial):
        scalar = torch.as_tensor(scalar, dtype=torch.float32)
        spatial = torch.as_tensor(spatial, dtype=torch.float32, device=scalar.device)
        state = initial_six_qubit_state(spatial[:, 0])
        phases = fixed_layer_phase_maps(spatial)
        # The final thirteen scalar positions are five action fields followed by
        # the eight workload one-hot fields.
        axis_x = scalar[:, -13] >= scalar[:, -12]
        for layer in range(self.layers):
            phase = phases[:, layer]
            state = apply_spatial_diagonal_phase(state, phase)
            feature = torch.tanh(scalar @ self.scalar_projection[layer].T)
            feature = feature.clone()
            feature[:, :4] = torch.clamp(
                feature[:, :4] + spatial_bit_phase_features(phase), -1.0, 1.0
            )
            angles = math.pi * (
                feature * self.encoding_scale[layer] + self.encoding_bias[layer]
            )
            for wire in range(6):
                state = _apply_single_qubit_gate(state, rz_gate(angles[:, wire]), wire, 6)
                state = _apply_single_qubit_gate(state, ry_gate(self.theta_y[layer, wire]), wire, 6)
                state = _apply_single_qubit_gate(state, rz_gate(self.theta_z[layer, wire]), wire, 6)
            state = self._interaction_layer(state, layer, axis_x)
        # Fixed mixing makes phase information visible to the Z/X readout.
        for wire in range(4):
            state = _apply_single_qubit_gate(state, ry_gate(math.pi / 4), wire, 6)
        return state

    def circuit_features(self, scalar, spatial):
        state = self.statevector(scalar, spatial)
        return torch.stack(
            [self._expectation(state, observable) for observable in self.observables], dim=1
        )

    def forward(self, scalar, spatial):
        return self.circuit_features(scalar, spatial) @ self.readout + self.readout_bias


# Explicit historical alias for old result replay only.
GeometryConditionedVQC = OldAdditivePhaseVQC
