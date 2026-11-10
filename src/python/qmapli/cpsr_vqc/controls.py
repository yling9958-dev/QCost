"""Fair classical and standard quantum controls for CPSR experiments."""

from __future__ import annotations

import torch
import torch.nn as nn

from ..quantum.gates import _apply_single_qubit_gate, _apply_two_qubit_gate, ry_gate, rz_gate, two_qubit_gate
from .model import BudgetResidual, CPSR_OBSERVABLES, _pauli, _raw_model_values


def _projection(rows, columns, seed):
    generator = torch.Generator().manual_seed(int(seed))
    matrix = torch.randn(rows, columns, generator=generator)
    return matrix / torch.clamp(torch.linalg.vector_norm(matrix, dim=1, keepdim=True), min=1e-6)


class ProjectedMLP(nn.Module):
    """Nonlinear MLP with an exact 111- or 733-parameter budget."""

    def __init__(self, scalar_size, budget, seed):
        super().__init__()
        raw_size = int(scalar_size) + 7 * 16
        width, hidden = (10, 6) if budget == 111 else (24, 20)
        self.register_buffer("projection", _projection(width, raw_size, seed + 1))
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.hidden = nn.Linear(width, hidden)
            self.output = nn.Linear(hidden, 4)
        used = sum(parameter.numel() for parameter in self.parameters())
        self.extra = BudgetResidual(raw_size, budget - used, seed + 2, outputs=4)
        if self.parameter_count != budget:
            raise AssertionError(self.parameter_count)

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    def task_outputs(self, scalar, spatial):
        raw = _raw_model_values(scalar, spatial)
        return self.output(torch.tanh(self.hidden(raw @ self.projection.T))) + self.extra(raw)

    def forward(self, scalar, spatial):
        return self.task_outputs(scalar, spatial)[:, 0]


class FactorizedTensorController(nn.Module):
    """Low-rank channel-by-cell controller with an exact budget."""

    def __init__(self, scalar_size, budget, seed):
        super().__init__()
        raw_size = int(scalar_size) + 7 * 16
        rank = 3 if budget == 111 else 20
        generator = torch.Generator().manual_seed(int(seed) + 3)
        self.register_buffer("scalar_projection", _projection(rank, int(scalar_size), seed + 4))
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.channel_factor = nn.Parameter(0.05 * torch.randn(rank, 7))
            self.spatial_factor = nn.Parameter(0.05 * torch.randn(rank, 16))
            self.scalar_factor = nn.Parameter(0.05 * torch.randn(rank))
            self.output = nn.Linear(rank * 2, 4)
        used = sum(parameter.numel() for parameter in self.parameters())
        self.extra = BudgetResidual(raw_size, budget - used, seed + 5, outputs=4)
        if self.parameter_count != budget:
            raise AssertionError(self.parameter_count)

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    def task_outputs(self, scalar, spatial):
        tensor_feature = torch.einsum(
            "bkc,rk,rc->br", spatial.flatten(2), self.channel_factor, self.spatial_factor
        )
        scalar_feature = (scalar @ self.scalar_projection.T) * self.scalar_factor
        raw = _raw_model_values(scalar, spatial)
        return self.output(torch.tanh(torch.cat((tensor_feature, scalar_feature), dim=1))) + self.extra(raw)

    def forward(self, scalar, spatial):
        return self.task_outputs(scalar, spatial)[:, 0]


class StrongCNN733(nn.Module):
    """A genuinely convolutional 733-parameter upper classical control."""

    def __init__(self, scalar_size, seed):
        super().__init__()
        raw_size = int(scalar_size) + 7 * 16
        self.register_buffer("scalar_projection", _projection(8, int(scalar_size), seed + 6))
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.conv1 = nn.Conv2d(7, 4, 2)
            self.conv2 = nn.Conv2d(4, 4, 2)
            self.fusion = nn.Linear(12, 16)
            self.output = nn.Linear(16, 4)
        used = sum(parameter.numel() for parameter in self.parameters())
        self.extra = BudgetResidual(raw_size, 733 - used, seed + 7, outputs=4)
        if self.parameter_count != 733:
            raise AssertionError(self.parameter_count)

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    def task_outputs(self, scalar, spatial):
        hidden = torch.tanh(self.conv1(spatial))
        hidden = torch.tanh(self.conv2(hidden)).mean(dim=(-2, -1))
        scalar_hidden = scalar @ self.scalar_projection.T
        raw = _raw_model_values(scalar, spatial)
        return self.output(torch.tanh(self.fusion(torch.cat((hidden, scalar_hidden), dim=1)))) + self.extra(raw)

    def forward(self, scalar, spatial):
        return self.task_outputs(scalar, spatial)[:, 0]


class StandardReuploadingVQC(nn.Module):
    """QB3: standard shallow angle re-uploading without semantic alignment."""

    def __init__(self, scalar_size, seed=42, blocks=1):
        super().__init__()
        self.num_qubits = 8
        self.blocks = int(blocks)
        raw_size = int(scalar_size) + 7 * 16
        self.register_buffer("encoding_projection", _projection(self.blocks * 16, raw_size, seed + 8))
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.local = nn.Parameter(0.05 * torch.randn(self.blocks, 16))
            self.entanglement = nn.Parameter(0.05 * torch.randn(self.blocks, 3))
            self.head_weights = nn.Parameter(0.05 * torch.randn(4, 8))
            self.head_bias = nn.Parameter(torch.zeros(4))
        used = sum(parameter.numel() for parameter in self.parameters())
        filler = 111 - used
        generator = torch.Generator().manual_seed(int(seed) + 9)
        projection = torch.randn(filler, 24, generator=generator)
        projection /= torch.clamp(torch.linalg.vector_norm(projection, dim=1, keepdim=True), min=1e-6)
        self.register_buffer("score_projection", projection)
        self.score_weights = nn.Parameter(
            0.05 * torch.randn(filler, generator=generator)
        )
        head_projection = torch.randn(4, 8, 24, generator=generator)
        head_projection /= torch.clamp(torch.linalg.vector_norm(head_projection, dim=2, keepdim=True), min=1e-6)
        self.register_buffer("head_projection", head_projection)
        if self.parameter_count != 111:
            raise AssertionError(self.parameter_count)

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    def statevector(self, scalar, spatial):
        raw = _raw_model_values(scalar, spatial)
        encoded = math_pi() * torch.tanh(raw @ self.encoding_projection.T)
        state = torch.zeros((len(raw), 256), dtype=torch.complex64, device=raw.device)
        state[:, 0] = 1.0
        for block in range(self.blocks):
            angles = encoded[:, block * 16 : (block + 1) * 16]
            for wire in range(8):
                state = _apply_single_qubit_gate(state, ry_gate(angles[:, wire] + self.local[block, wire]), wire, 8)
                state = _apply_single_qubit_gate(state, rz_gate(angles[:, wire + 8] + self.local[block, wire + 8]), wire, 8)
            for angle, pair in zip(self.entanglement[block], ((4, 5), (5, 6), (6, 7)), strict=True):
                state = _apply_two_qubit_gate(state, two_qubit_gate("cry", angle), *pair, 8)
        return state

    def _expectation(self, state, specification):
        transformed, cursor = state, 0
        while cursor < len(specification):
            kind, cursor = specification[cursor], cursor + 1
            digits = []
            while cursor < len(specification) and specification[cursor].isdigit():
                digits.append(specification[cursor]); cursor += 1
            transformed = _apply_single_qubit_gate(transformed, _pauli(kind, state.device), int("".join(digits)), 8)
        return torch.sum(state.conj() * transformed, dim=1).real

    def circuit_features(self, scalar, spatial):
        state = self.statevector(scalar, spatial)
        return torch.stack([self._expectation(state, item) for item in CPSR_OBSERVABLES], dim=1)

    def task_outputs(self, scalar, spatial):
        features = self.circuit_features(scalar, spatial)
        projected = torch.tanh(torch.einsum("bi,oki->bok", features, self.head_projection))
        output = torch.einsum("bok,ok->bo", projected, self.head_weights) + self.head_bias
        output[:, 0] = output[:, 0] + torch.tanh(features @ self.score_projection.T) @ self.score_weights
        return output

    def forward(self, scalar, spatial):
        return self.task_outputs(scalar, spatial)[:, 0]


def math_pi():
    return 3.141592653589793
