"""Adaptive sparse entanglement and ambiguity-gated CPSR residual."""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn

from ..cpsr_vqc.model import (
    BudgetResidual,
    CPSRConfiguration,
    CPSRQuantumCore,
    _raw_model_values,
)
from ..quantum.gates import _apply_two_qubit_gate, two_qubit_gate


ADAPTIVE_EDGES = (
    (4, 5),
    (5, 6),
    (6, 7),
    (5, 2),
    (5, 3),
    (6, 2),
    (6, 3),
    (7, 2),
    (7, 3),
)


@dataclass(frozen=True)
class AQConfiguration:
    """Frozen CPSR backbone plus the only development-selectable AQ fields."""

    interaction_mode: str = "adaptive"
    ambiguity_gated: bool = True
    ambiguity_tau: float = 0.0
    ambiguity_temperature: float = 0.10
    sparse_weight: float = 0.0

    def __post_init__(self):
        if self.interaction_mode not in {"adaptive", "no_entangle", "fixed_t2"}:
            raise ValueError(self.interaction_mode)
        if self.ambiguity_temperature <= 0:
            raise ValueError("ambiguity temperature must be positive")


class AdaptiveCPSRQuantumCore(CPSRQuantumCore):
    """The frozen full/T2 core with nine learnable edge gates.

    Nine score-projection filler parameters are exchanged for nine gate logits,
    so the circuit remains exactly 111 trainable parameters. Gate logits start
    at -3, which places the circuit close to the empirically stronger NoEnt
    solution without removing any candidate edge.
    """

    def __init__(self, seed: int = 42):
        config = CPSRConfiguration(
            channels="full",
            reupload_blocks=1,
            topology="T2",
            entangled=True,
            trainable_scaling=True,
            projected_readout=True,
        )
        super().__init__(config, seed=seed)
        old_filler = int(self.score_weights.numel())
        new_filler = old_filler - len(ADAPTIVE_EDGES)
        if new_filler < 1:
            raise AssertionError("adaptive gates exceed the projected-readout filler budget")
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed) + 2801)
            self.score_weights = nn.Parameter(0.05 * torch.randn(new_filler))
            self.edge_logits = nn.Parameter(torch.full((len(ADAPTIVE_EDGES),), -3.0))
        generator = torch.Generator().manual_seed(int(seed) + 2802)
        projection = torch.randn(new_filler, len(self.observables), generator=generator)
        projection /= torch.clamp(
            torch.linalg.vector_norm(projection, dim=1, keepdim=True), min=1e-6
        )
        self.score_projection = projection
        if self.parameter_count != 111:
            raise AssertionError(f"adaptive core has {self.parameter_count}, expected 111")

    @property
    def edge_gate_values(self) -> torch.Tensor:
        return torch.sigmoid(self.edge_logits)

    def sparse_penalty(self) -> torch.Tensor:
        return self.edge_gate_values.sum()

    def _interaction(self, state, block):
        gates = self.edge_gate_values
        for edge_index, ((control, target), angle) in enumerate(
            zip(ADAPTIVE_EDGES, self.interaction_angles[block], strict=True)
        ):
            effective_angle = gates[edge_index] * angle
            state = _apply_two_qubit_gate(
                state,
                two_qubit_gate("cry", effective_angle, device=state.device),
                control,
                target,
                8,
            )
        return state


class CPSRAQController(nn.Module):
    """Exact-733 CPSR controller with group-level ambiguity gating."""

    def __init__(
        self,
        scalar_size: int,
        *,
        configuration: AQConfiguration | None = None,
        seed: int = 42,
    ):
        super().__init__()
        self.configuration = configuration or AQConfiguration()
        self.scalar_size = int(scalar_size)
        if self.configuration.interaction_mode == "adaptive":
            self.core = AdaptiveCPSRQuantumCore(seed=seed)
        else:
            self.core = CPSRQuantumCore(
                CPSRConfiguration(
                    channels="full",
                    reupload_blocks=1,
                    topology="T2",
                    entangled=self.configuration.interaction_mode == "fixed_t2",
                    trainable_scaling=True,
                    projected_readout=True,
                ),
                seed=seed,
            )
        raw_size = self.scalar_size + 7 * 16
        self.residual = BudgetResidual(raw_size, 622, seed + 23, outputs=1)
        self.register_buffer(
            "ambiguity_tau", torch.tensor(float(self.configuration.ambiguity_tau), dtype=torch.float32)
        )
        self.register_buffer(
            "ambiguity_temperature",
            torch.tensor(float(self.configuration.ambiguity_temperature), dtype=torch.float32),
        )
        if self.parameter_count != 733:
            raise AssertionError(f"CPSR-AQ has {self.parameter_count}, expected 733")

    @property
    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

    @property
    def trainable_parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)

    @property
    def edge_gate_values(self) -> torch.Tensor:
        if isinstance(self.core, AdaptiveCPSRQuantumCore):
            return self.core.edge_gate_values
        if self.configuration.interaction_mode == "fixed_t2":
            return torch.ones(len(ADAPTIVE_EDGES), device=next(self.parameters()).device)
        return torch.zeros(len(ADAPTIVE_EDGES), device=next(self.parameters()).device)

    def sparse_penalty(self) -> torch.Tensor:
        if isinstance(self.core, AdaptiveCPSRQuantumCore):
            return self.core.sparse_penalty()
        return torch.zeros((), device=next(self.parameters()).device)

    def branch_scores(self, scalar: torch.Tensor, spatial: torch.Tensor):
        shape = scalar.shape[:2]
        flat_scalar = scalar.reshape(-1, scalar.shape[-1])
        flat_spatial = spatial.reshape(-1, *spatial.shape[-3:])
        quantum = self.core(flat_scalar, flat_spatial).reshape(shape)
        classical = self.residual(_raw_model_values(flat_scalar, flat_spatial))[:, 0].reshape(shape)
        return classical, quantum

    @staticmethod
    def classical_margin(classical: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        masked = classical.masked_fill(~valid, -torch.inf)
        if masked.shape[1] < 2:
            return torch.full((len(masked),), torch.inf, device=masked.device)
        values = torch.topk(masked, k=2, dim=1).values
        return values[:, 0] - values[:, 1]

    def quantum_gate(self, classical: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        if not self.configuration.ambiguity_gated:
            return torch.ones(classical.shape[0], device=classical.device)
        margin = self.classical_margin(classical, valid)
        return torch.sigmoid(
            (self.ambiguity_tau.to(classical.device) - margin)
            / self.ambiguity_temperature.to(classical.device)
        )

    def group_scores(self, scalar: torch.Tensor, spatial: torch.Tensor, valid: torch.Tensor):
        classical, quantum = self.branch_scores(scalar, spatial)
        gate = self.quantum_gate(classical, valid)
        scores = classical + gate[:, None] * quantum
        return {
            "scores": scores,
            "classical_scores": classical,
            "quantum_scores": quantum,
            "quantum_gate": gate,
            "classical_margin": self.classical_margin(classical, valid),
        }

    def forward(self, scalar: torch.Tensor, spatial: torch.Tensor):
        """Flat inference is always-on; experiments use ``group_scores``."""

        quantum = self.core(scalar, spatial)
        classical = self.residual(_raw_model_values(scalar, spatial))[:, 0]
        return classical + quantum


def aq_metadata(model: CPSRAQController) -> dict[str, object]:
    gates = model.edge_gate_values.detach().cpu().numpy()
    return {
        "name": "CPSR-AQ",
        "qubits": 8,
        "reupload_blocks": 1,
        "channels": ["P", "W", "M", "B", "I_DQ", "I_QB", "I_DQB"],
        "observables": list(model.core.observables),
        "parameter_count": model.parameter_count,
        "trainable_parameter_count": model.trainable_parameter_count,
        "interaction_mode": model.configuration.interaction_mode,
        "ambiguity_gated": model.configuration.ambiguity_gated,
        "edge_gate_values": gates.tolist(),
        "active_edges": [index + 1 for index, value in enumerate(gates) if value >= 0.20],
        "strong_edges": [index + 1 for index, value in enumerate(gates) if value >= 0.50],
    }
