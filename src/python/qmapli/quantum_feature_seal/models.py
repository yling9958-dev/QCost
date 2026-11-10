"""Frozen model registry for the independent Quantum Feature Seal."""

from __future__ import annotations

import random

import numpy as np
import torch

from ..cpsr_aq.model import AQConfiguration, CPSRAQController
from ..cpsr_vqc.model import CPSRConfiguration
from ..cpsr_vqc.training import create_model


QF_MODEL_NAMES = (
    "QF-VQC",
    "AQ",
    "QB3",
    "NoQ",
    "FrozenQ",
    "C2",
    "C4",
    "C5",
    "R4",
)


def bind_runtime_seed(model_seed: int) -> None:
    """Bind every process-global RNG used by an experiment worker."""

    seed = int(model_seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def frozen_cpsr_configuration(*, entangled: bool = False) -> CPSRConfiguration:
    """The immutable FULL, 8-qubit, one-block CPSR configuration."""

    return CPSRConfiguration(
        channels="full",
        reupload_blocks=1,
        topology="T2",
        entangled=bool(entangled),
        trainable_scaling=True,
        projected_readout=True,
    )


def create_seal_model(name: str, scalar_size: int, model_seed: int):
    """Create one controller with all randomness keyed by ``model_seed``."""

    if name not in QF_MODEL_NAMES:
        raise ValueError(f"unknown Quantum Feature Seal model: {name}")
    bind_runtime_seed(model_seed)
    if name == "QF-VQC":
        return create_model(
            "NoEnt",
            scalar_size,
            int(model_seed),
            cpsr_config=frozen_cpsr_configuration(entangled=False),
        )
    if name == "AQ":
        return CPSRAQController(
            scalar_size,
            configuration=AQConfiguration(
                interaction_mode="adaptive",
                ambiguity_gated=False,
                ambiguity_tau=0.04028049111366272,
                ambiguity_temperature=0.10,
                sparse_weight=0.0001,
            ),
            seed=int(model_seed),
        )
    aliases = {
        "QB3": "QB3",
        "NoQ": "NoQ",
        "FrozenQ": "FrozenQ",
        "C2": "C2",
        "C4": "C4",
        "C5": "C5",
        "R4": "R4",
    }
    return create_model(
        aliases[name],
        scalar_size,
        int(model_seed),
        cpsr_config=frozen_cpsr_configuration(entangled=True),
    )


def model_parameter_count(model) -> int:
    return sum(parameter.numel() for parameter in model.parameters())
