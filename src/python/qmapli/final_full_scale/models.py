"""Frozen controller attribution models for the final experiment.

The production six-qubit QMap controller is deliberately not imported or
modified here.  CAQF evaluates the no-entanglement CPSR feature map as a
classical 16-by-16 tensor contraction, without invoking the eight-qubit
statevector path.
"""

from __future__ import annotations

import math
import re

import torch
import torch.nn as nn

from ..cpsr_aq.model import AQConfiguration, AdaptiveCPSRQuantumCore, CPSRAQController
from ..cpsr_vqc.model import (
    BudgetResidual,
    CHANNEL_INDEX,
    CPSRConfiguration,
    CPSRQuantumCore,
    _raw_model_values,
    rx_gate,
)
from ..quantum.gates import _apply_single_qubit_gate, ry_gate, rz_gate


def _single_qubit_operator(kind: str) -> torch.Tensor:
    if kind == "i":
        return torch.eye(2, dtype=torch.complex64)
    if kind == "x":
        return torch.tensor([[0, 1], [1, 0]], dtype=torch.complex64)
    if kind == "y":
        return torch.tensor([[0, -1j], [1j, 0]], dtype=torch.complex64)
    if kind == "z":
        return torch.tensor([[1, 0], [0, -1]], dtype=torch.complex64)
    raise ValueError(kind)


def _register_operator(specification: str, start: int, stop: int) -> torch.Tensor:
    assignments = {int(wire): kind for kind, wire in re.findall(r"([xyz])(\d+)", specification)}
    operator = torch.ones((1, 1), dtype=torch.complex64)
    for wire in range(start, stop):
        operator = torch.kron(operator, _single_qubit_operator(assignments.get(wire, "i")))
    return operator


class ClassicalAnalyticalQuantumFeatureCore(CPSRQuantumCore):
    """Classically contract the frozen QF-NoEnt circuit's 24 observables.

    The calculation retains the position-conditioned semantic states as a
    ``16 spatial x 16 semantic`` amplitude matrix.  Local sin/cos rotations
    and projected observables are contracted directly; no generic 8-qubit
    statevector routine is called.
    """

    def __init__(self, seed: int = 42):
        super().__init__(
            CPSRConfiguration(
                channels="full",
                reupload_blocks=1,
                topology="T2",
                entangled=False,
                trainable_scaling=True,
                projected_readout=True,
            ),
            seed=seed,
        )
        spatial = torch.stack([_register_operator(item, 0, 4) for item in self.observables])
        semantic = torch.stack([_register_operator(item, 4, 8) for item in self.observables])
        self.register_buffer("analytical_spatial_operators", spatial, persistent=False)
        self.register_buffer("analytical_semantic_operators", semantic, persistent=False)

    @staticmethod
    def _apply_semantic(states, gate, wire):
        batch, cells, width = states.shape
        return _apply_single_qubit_gate(
            states.reshape(batch * cells, width), gate, wire, 4
        ).reshape(batch, cells, width)

    @staticmethod
    def _apply_spatial(amplitudes, gate, wire):
        batch, spatial, semantic = amplitudes.shape
        transposed = amplitudes.permute(0, 2, 1).reshape(batch * semantic, spatial)
        transformed = _apply_single_qubit_gate(transposed, gate, wire, 4)
        return transformed.reshape(batch, semantic, spatial).permute(0, 2, 1)

    def analytical_amplitudes(self, scalar, spatial):
        scalar = torch.as_tensor(scalar, dtype=torch.float32)
        spatial = torch.as_tensor(spatial, dtype=torch.float32, device=scalar.device)
        batch = len(scalar)
        semantic = torch.zeros((batch, 16, 16), dtype=torch.complex64, device=scalar.device)
        semantic[:, :, 0] = 1.0
        scales = {
            name: self.semantic_scales[index]
            for index, name in enumerate(self.channel_names)
        }

        def load(name, gate, wire):
            nonlocal semantic
            values = spatial[:, CHANNEL_INDEX[name]].reshape(batch, 16)
            angles = math.pi * torch.tanh(scales[name] * values)
            semantic = self._apply_semantic(semantic, gate(angles.reshape(-1)), wire)

        load("P", ry_gate, 0)
        load("W", rz_gate, 1)
        load("M", rx_gate, 2)
        load("B", rz_gate, 2)
        load("I_DQ", rx_gate, 3)
        load("I_QB", ry_gate, 3)
        load("I_DQB", rz_gate, 3)

        axis_signal = scalar[:, -5] - scalar[:, -4]
        quantile = 2.0 * scalar[:, -3] - 1.0
        axis_gate = ry_gate(math.pi * torch.tanh(self.context_scales[0] * axis_signal))
        quantile_gate = rz_gate(math.pi * torch.tanh(self.context_scales[1] * quantile))
        semantic = self._apply_semantic(
            semantic, axis_gate.repeat_interleave(16, dim=0), 3
        )
        semantic = self._apply_semantic(
            semantic, quantile_gate.repeat_interleave(16, dim=0), 3
        )

        spatial_gates: list[tuple[torch.Tensor, int]] = []
        pairs = ((4, 5), (5, 6), (6, 7), (5, 2), (5, 3), (6, 2), (6, 3), (7, 2), (7, 3))
        for angle, (_control, target) in zip(self.interaction_angles[0], pairs, strict=True):
            if target >= 4:
                semantic = self._apply_semantic(semantic, ry_gate(angle), target - 4)
            else:
                spatial_gates.append((ry_gate(angle), target))
        for wire in range(8):
            if wire >= 4:
                semantic = self._apply_semantic(semantic, ry_gate(self.local_y[0, wire]), wire - 4)
                semantic = self._apply_semantic(semantic, rz_gate(self.local_z[0, wire]), wire - 4)
            else:
                spatial_gates.append((ry_gate(self.local_y[0, wire]), wire))
                spatial_gates.append((rz_gate(self.local_z[0, wire]), wire))

        amplitudes = semantic * 0.25
        for gate, wire in spatial_gates:
            amplitudes = self._apply_spatial(amplitudes, gate, wire)
        return amplitudes

    def circuit_features(self, scalar, spatial):
        amplitudes = self.analytical_amplitudes(scalar, spatial)
        spatial_operators = self.analytical_spatial_operators.to(amplitudes.device)
        semantic_operators = self.analytical_semantic_operators.to(amplitudes.device)
        spatial_applied = torch.einsum("oij,bjs->bois", spatial_operators, amplitudes)
        transformed = torch.einsum("ots,bois->boit", semantic_operators, spatial_applied)
        return torch.einsum("bit,boit->bo", amplitudes.conj(), transformed).real


class CAQFController(nn.Module):
    """733-parameter classical analytical surrogate of QF-VQC."""

    def __init__(self, scalar_size: int, seed: int = 42):
        super().__init__()
        self.scalar_size = int(scalar_size)
        self.core = ClassicalAnalyticalQuantumFeatureCore(seed=seed)
        self.residual = BudgetResidual(self.scalar_size + 7 * 16, 622, seed + 23, outputs=1)
        if self.parameter_count != 733:
            raise AssertionError(f"CAQF has {self.parameter_count} parameters")

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    def task_outputs(self, scalar, spatial):
        output = self.core.task_outputs(scalar, spatial).clone()
        output[:, 0] += self.residual(_raw_model_values(scalar, spatial))[:, 0]
        return output

    def forward(self, scalar, spatial):
        return self.task_outputs(scalar, spatial)[:, 0]


class ZeroEntAdaptiveCore(AdaptiveCPSRQuantumCore):
    """AQ core with all nine adaptive controlled rotations fixed to zero."""

    @property
    def edge_gate_values(self):
        return torch.zeros_like(self.edge_logits)

    def sparse_penalty(self):
        return self.edge_logits.new_zeros(())

    def _interaction(self, state, block):
        del block
        return state


class AQZeroEntController(CPSRAQController):
    """The complete AQ scoring framework with zero effective entanglement."""

    def __init__(self, scalar_size: int, seed: int = 42):
        super().__init__(
            scalar_size,
            configuration=AQConfiguration(
                interaction_mode="adaptive",
                ambiguity_gated=False,
                ambiguity_tau=0.04028049111366272,
                ambiguity_temperature=0.10,
                sparse_weight=0.0001,
            ),
            seed=seed,
        )
        self.core = ZeroEntAdaptiveCore(seed=seed)
        if self.parameter_count != 733:
            raise AssertionError(f"AQ-ZeroEnt has {self.parameter_count} parameters")
