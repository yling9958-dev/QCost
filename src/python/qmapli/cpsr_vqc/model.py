"""Eight-qubit CPSR-VQC and parameter-matched component controls.

This module is deliberately isolated from qmapli.quantum.controller, which is
the frozen production six-qubit controller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn as nn

from ..quantum.gates import (
    _apply_single_qubit_gate,
    _apply_two_qubit_gate,
    ry_gate,
    rz_gate,
    two_qubit_gate,
)


CPSR_OBSERVABLES = (
    "z4", "z5", "z6", "z7",
    "x4", "x5", "x6", "x7",
    "z4z5", "z5z6", "z6z7",
    "z5z2", "z5z3", "z6z2", "z6z3", "z7z2", "z7z3",
    "x4x5", "x5x6", "x6x7",
    "y5y6", "y6y7", "z4z0", "z7z1",
)

CHANNEL_INDEX = {"P": 0, "W": 1, "M": 2, "B": 3, "I_DQ": 4, "I_QB": 5, "I_DQB": 6}
FULL_CHANNELS = tuple(CHANNEL_INDEX)
COMPACT_CHANNELS = ("P", "W", "M", "B", "I_QB", "I_DQB")


def rx_gate(angle: torch.Tensor | float) -> torch.Tensor:
    """Local RX implementation; the frozen production gate module is untouched."""

    angle = torch.as_tensor(angle)
    half = angle.to(torch.float32) / 2.0
    cosine = torch.cos(half).to(torch.complex64)
    off = torch.complex(torch.zeros_like(half), -torch.sin(half))
    return torch.stack(
        (torch.stack((cosine, off), dim=-1), torch.stack((off, cosine), dim=-1)),
        dim=-2,
    )


def _pauli(kind: str, device) -> torch.Tensor:
    if kind == "x":
        return torch.tensor([[0, 1], [1, 0]], dtype=torch.complex64, device=device)
    if kind == "y":
        return torch.tensor([[0, -1j], [1j, 0]], dtype=torch.complex64, device=device)
    if kind == "z":
        return torch.tensor([[1, 0], [0, -1]], dtype=torch.complex64, device=device)
    raise ValueError(kind)


def _multiplexed_single(state, angles, gate_factory, semantic_wire):
    """Apply one angle per spatial basis state without a Python cell loop."""

    batch = state.shape[0]
    semantic = state.reshape(batch, 16, 16).reshape(batch * 16, 16)
    gates = gate_factory(angles.reshape(batch * 16))
    semantic = _apply_single_qubit_gate(semantic, gates, semantic_wire - 4, 4)
    return semantic.reshape(batch, 16, 16).reshape(batch, 256)


class BudgetResidual(nn.Module):
    """Fixed random feature residual with an exact trainable parameter budget."""

    def __init__(self, input_size: int, budget: int, seed: int, outputs: int = 1):
        super().__init__()
        if budget < outputs:
            raise ValueError("residual budget is too small")
        generator = torch.Generator().manual_seed(int(seed) + 1907)
        projection = torch.randn(outputs, budget, input_size, generator=generator)
        projection /= torch.clamp(torch.linalg.vector_norm(projection, dim=2, keepdim=True), min=1e-6)
        self.register_buffer("projection", projection)
        # A shared coefficient bank keeps ``budget`` equal to the total number
        # of trainable parameters while fixed output-specific projections make
        # the four task heads distinct.
        self.weights = nn.Parameter(torch.zeros(budget))

    def forward(self, values):
        hidden = torch.tanh(torch.einsum("bi,oki->bok", values, self.projection))
        return torch.einsum("bok,k->bo", hidden, self.weights)


@dataclass(frozen=True)
class CPSRConfiguration:
    channels: str = "compact"
    reupload_blocks: int = 1
    topology: str = "T1"
    entangled: bool = True
    trainable_scaling: bool = True
    projected_readout: bool = True


class CPSRQuantumCore(nn.Module):
    """Semantic-separated, shallow re-uploading circuit with exact 111 parameters."""

    def __init__(self, config: CPSRConfiguration, seed: int = 42):
        super().__init__()
        if config.channels not in {"full", "compact"}:
            raise ValueError(config.channels)
        if config.reupload_blocks not in {1, 2}:
            raise ValueError("CPSR permits one or two re-upload blocks")
        if config.topology not in {"T1", "T2"}:
            raise ValueError(config.topology)
        self.config = config
        self.num_qubits = 8
        self.observables = CPSR_OBSERVABLES
        self.channel_names = FULL_CHANNELS if config.channels == "full" else COMPACT_CHANNELS
        edges = 3 if config.topology == "T1" else 9
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            scales = torch.ones(len(self.channel_names))
            self.semantic_scales = nn.Parameter(scales, requires_grad=config.trainable_scaling)
            self.context_scales = nn.Parameter(torch.ones(2), requires_grad=config.trainable_scaling)
            self.local_y = nn.Parameter(0.05 * torch.randn(config.reupload_blocks, 8))
            self.local_z = nn.Parameter(0.05 * torch.randn(config.reupload_blocks, 8))
            self.interaction_angles = nn.Parameter(0.05 * torch.randn(config.reupload_blocks, edges))
            self.head_weights = nn.Parameter(0.05 * torch.randn(4, 8))
            self.head_bias = nn.Parameter(torch.zeros(4))
        base = sum(parameter.numel() for parameter in self.parameters())
        filler = 111 - base
        if filler < 1:
            raise AssertionError(f"CPSR circuit consumes {base} parameters before its projected readout")
        generator = torch.Generator().manual_seed(int(seed) + 911)
        projection = torch.randn(filler, len(CPSR_OBSERVABLES), generator=generator)
        projection /= torch.clamp(torch.linalg.vector_norm(projection, dim=1, keepdim=True), min=1e-6)
        self.register_buffer("score_projection", projection)
        self.score_weights = nn.Parameter(
            0.05 * torch.randn(filler, generator=generator)
        )
        head_projection = torch.randn(4, 8, len(CPSR_OBSERVABLES), generator=generator)
        head_projection /= torch.clamp(torch.linalg.vector_norm(head_projection, dim=2, keepdim=True), min=1e-6)
        self.register_buffer("head_projection", head_projection)
        if self.parameter_count != 111:
            raise AssertionError(f"CPSR-111 has {self.parameter_count} parameters")

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    @property
    def trainable_parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)

    @property
    def two_qubit_gate_count(self):
        return self.config.reupload_blocks * self.interaction_angles.shape[1]

    @property
    def one_qubit_gate_count(self):
        per_block = 16 * len(self.channel_names) + 16 + 2
        return 4 + self.config.reupload_blocks * per_block

    def _initial_state(self, batch, device):
        state = torch.zeros((batch, 256), dtype=torch.complex64, device=device)
        state[:, torch.arange(16, device=device) * 16] = 0.25
        return state

    def _load_channel(self, state, spatial, channel, scale, gate, wire):
        values = spatial[:, CHANNEL_INDEX[channel]]
        angles = math.pi * torch.tanh(scale * values)
        return _multiplexed_single(state, angles, gate, wire)

    def _feature_loading(self, state, scalar, spatial):
        scale = {name: self.semantic_scales[index] for index, name in enumerate(self.channel_names)}
        state = self._load_channel(state, spatial, "P", scale["P"], ry_gate, 4)
        state = self._load_channel(state, spatial, "W", scale["W"], rz_gate, 5)
        state = self._load_channel(state, spatial, "M", scale["M"], rx_gate, 6)
        state = self._load_channel(state, spatial, "B", scale["B"], rz_gate, 6)
        if "I_DQ" in scale:
            state = self._load_channel(state, spatial, "I_DQ", scale["I_DQ"], rx_gate, 7)
        state = self._load_channel(state, spatial, "I_QB", scale["I_QB"], ry_gate, 7)
        state = self._load_channel(state, spatial, "I_DQB", scale["I_DQB"], rz_gate, 7)
        axis_signal = scalar[:, -5] - scalar[:, -4]
        quantile = 2.0 * scalar[:, -3] - 1.0
        state = _apply_single_qubit_gate(state, ry_gate(math.pi * torch.tanh(self.context_scales[0] * axis_signal)), 7, 8)
        return _apply_single_qubit_gate(state, rz_gate(math.pi * torch.tanh(self.context_scales[1] * quantile)), 7, 8)

    def _interaction(self, state, block):
        pairs = [(4, 5), (5, 6), (6, 7)]
        if self.config.topology == "T2":
            pairs.extend([(5, 2), (5, 3), (6, 2), (6, 3), (7, 2), (7, 3)])
        for angle, (control, target) in zip(self.interaction_angles[block], pairs, strict=True):
            if self.config.entangled:
                state = _apply_two_qubit_gate(
                    state, two_qubit_gate("cry", angle, device=state.device), control, target, 8
                )
            else:
                # The angle remains active and parameter matched.
                state = _apply_single_qubit_gate(state, ry_gate(angle), target, 8)
        return state

    def statevector(self, scalar, spatial):
        scalar = torch.as_tensor(scalar, dtype=torch.float32)
        spatial = torch.as_tensor(spatial, dtype=torch.float32, device=scalar.device)
        state = self._initial_state(len(scalar), scalar.device)
        for block in range(self.config.reupload_blocks):
            state = self._feature_loading(state, scalar, spatial)
            state = self._interaction(state, block)
            for wire in range(8):
                state = _apply_single_qubit_gate(state, ry_gate(self.local_y[block, wire]), wire, 8)
                state = _apply_single_qubit_gate(state, rz_gate(self.local_z[block, wire]), wire, 8)
        return state

    def _expectation(self, state, specification):
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
                transformed, _pauli(kind, state.device), int("".join(digits)), 8
            )
        return torch.sum(state.conj() * transformed, dim=1).real

    def circuit_features(self, scalar, spatial):
        state = self.statevector(scalar, spatial)
        return torch.stack([self._expectation(state, item) for item in self.observables], dim=1)

    def task_outputs(self, scalar, spatial):
        features = self.circuit_features(scalar, spatial)
        if not self.config.projected_readout:
            features = torch.cat((features[:, :8], torch.zeros_like(features[:, 8:])), dim=1)
        head_features = torch.tanh(torch.einsum("bi,oki->bok", features, self.head_projection))
        outputs = torch.einsum("bok,ok->bo", head_features, self.head_weights) + self.head_bias
        outputs[:, 0] = outputs[:, 0] + torch.tanh(features @ self.score_projection.T) @ self.score_weights
        return outputs

    def forward(self, scalar, spatial):
        return self.task_outputs(scalar, spatial)[:, 0]


def _raw_model_values(scalar, spatial):
    return torch.cat((scalar, spatial.flatten(1)), dim=1)


class CPSRController(nn.Module):
    """CPSR-111, CPSR-733, NoEnt, FrozenQ, and NoQ under one interface."""

    def __init__(
        self,
        scalar_size: int,
        *,
        budget: int = 111,
        config: CPSRConfiguration | None = None,
        ablation: str = "full",
        seed: int = 42,
    ):
        super().__init__()
        if budget not in {111, 733}:
            raise ValueError("CPSR budgets are 111 or 733")
        if ablation not in {"full", "no_entangle", "frozen_quantum", "no_quantum"}:
            raise ValueError(ablation)
        config = config or CPSRConfiguration()
        if ablation == "no_entangle":
            config = CPSRConfiguration(
                channels=config.channels,
                reupload_blocks=config.reupload_blocks,
                topology=config.topology,
                entangled=False,
                trainable_scaling=config.trainable_scaling,
                projected_readout=config.projected_readout,
            )
        self.budget = budget
        self.ablation = ablation
        self.scalar_size = int(scalar_size)
        self.core = None if ablation == "no_quantum" else CPSRQuantumCore(config, seed)
        raw_size = self.scalar_size + 7 * 16
        if budget == 733:
            residual_budget = 733 if self.core is None else 622
            self.residual = BudgetResidual(raw_size, residual_budget, seed + 23, outputs=4 if self.core is None else 1)
        else:
            self.residual = None
        if ablation == "frozen_quantum":
            for parameter in self.core.parameters():
                parameter.requires_grad_(False)
        if self.parameter_count != budget:
            raise AssertionError(f"{ablation} footprint is {self.parameter_count}, expected {budget}")

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    @property
    def trainable_parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)

    def task_outputs(self, scalar, spatial):
        raw = _raw_model_values(scalar, spatial)
        if self.core is None:
            return self.residual(raw)
        outputs = self.core.task_outputs(scalar, spatial)
        if self.residual is not None:
            outputs = outputs.clone()
            outputs[:, 0] = outputs[:, 0] + self.residual(raw)[:, 0]
        return outputs

    def forward(self, scalar, spatial):
        return self.task_outputs(scalar, spatial)[:, 0]


def cpsr_metadata(model: CPSRController) -> dict[str, object]:
    core = model.core
    return {
        "name": "CPSR-VQC",
        "qubits": 8 if core is not None else 0,
        "reupload_blocks": core.config.reupload_blocks if core is not None else 0,
        "topology": core.config.topology if core is not None else "none",
        "observables": list(CPSR_OBSERVABLES),
        "parameter_count": model.parameter_count,
        "trainable_parameter_count": model.trainable_parameter_count,
        "one_qubit_gate_count": core.one_qubit_gate_count if core is not None else 0,
        "two_qubit_gate_count": core.two_qubit_gate_count if core is not None else 0,
    }
