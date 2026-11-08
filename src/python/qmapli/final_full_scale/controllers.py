"""Frozen controller training, attribution, and paired statistics."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..cpsr_aq.model import AQConfiguration, CPSRAQController
from ..cpsr_aq.training import evaluate_fitted, fit_ranking_model
from ..cpsr_vqc.training import create_model, fit_cst_normalizer, model_parameter_count
from ..quantum_feature_seal.models import bind_runtime_seed, frozen_cpsr_configuration
from ..quantum_feature_seal.seed_audit import state_dict_sha256
from ..workload_action_interaction.statistics import paired_bootstrap_difference
from .models import AQZeroEntController, CAQFController


MODEL_NAMES = (
    "AQ",
    "AQ-ZeroEnt",
    "QF",
    "QF-Gap",
    "NoQ-Base",
    "NoQ-Gap",
    "FrozenQ",
    "CAQF",
    "QB3",
    "CST",
    "Qold",
    "C2",
    "C4",
    "C5",
    "R4",
)


@dataclass(frozen=True)
class LossSpecification:
    lambda_gap: float
    lambda_top1: float


def loss_for_model(name: str, config: dict) -> LossSpecification:
    if name in {"NoQ-Base"}:
        return LossSpecification(0.0, 0.0)
    # QF was already frozen with the gap/top-1 loss. QF-Gap is intentionally
    # retained as an identical protocol alias so this fact is not obscured.
    return LossSpecification(
        float(config["controller"]["lambda_gap"]),
        float(config["controller"]["lambda_top1"]),
    )


def create_final_model(name: str, scalar_size: int, seed: int, *, cst_normalizer=None):
    bind_runtime_seed(seed)
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
            seed=seed,
        )
    if name == "AQ-ZeroEnt":
        return AQZeroEntController(scalar_size, seed=seed)
    if name in {"QF", "QF-Gap"}:
        return create_model(
            "NoEnt", scalar_size, seed,
            cpsr_config=frozen_cpsr_configuration(entangled=False),
        )
    if name in {"NoQ-Base", "NoQ-Gap"}:
        return create_model(
            "NoQ", scalar_size, seed,
            cpsr_config=frozen_cpsr_configuration(entangled=True),
        )
    if name == "CAQF":
        return CAQFController(scalar_size, seed=seed)
    if name == "CST":
        return create_model(
            "CST", scalar_size, seed,
            cpsr_config=frozen_cpsr_configuration(entangled=True),
            cst_normalizer=cst_normalizer,
        )
    aliases = {
        "FrozenQ": "FrozenQ",
        "QB3": "QB3",
        "Qold": "Qold",
        "C2": "C2",
        "C4": "C4",
        "C5": "C5",
        "R4": "R4",
    }
    if name not in aliases:
        raise ValueError(name)
    return create_model(
        aliases[name], scalar_size, seed,
        cpsr_config=frozen_cpsr_configuration(entangled=True),
    )


def fit_final_controller(
    name,
    development,
    train_indices,
    validation_indices,
    evaluation,
    evaluation_indices,
    *,
    config,
    model_seed,
    cst_normalizer=None,
):
    bind_runtime_seed(model_seed)
    model = create_final_model(
        name, development.scalar.shape[-1], model_seed,
        cst_normalizer=cst_normalizer,
    )
    initial_hash = state_dict_sha256(model)
    loss = loss_for_model(name, config)
    fitted = fit_ranking_model(
        model,
        development,
        train_indices,
        validation_indices,
        seed=int(model_seed),
        epochs=int(config["controller"]["epochs"]),
        learning_rate=float(config["controller"]["learning_rate"]),
        batch_size=int(config["controller"]["batch_size"]),
        patience=int(config["controller"]["early_stopping_patience"]),
        ranking_temperature=float(config["controller"]["ranking_temperature"]),
        lambda_gap=loss.lambda_gap,
        lambda_top1=loss.lambda_top1,
        lambda_sparse=(0.0001 if name == "AQ" else 0.0),
    )
    inference_started = time.perf_counter()
    frame, metrics, _output = evaluate_fitted(
        fitted, evaluation, evaluation_indices, label_split="test"
    )
    inference_seconds = time.perf_counter() - inference_started
    quantum_statevector = name in {"AQ", "AQ-ZeroEnt", "QF", "QF-Gap", "FrozenQ", "QB3", "CST", "Qold"}
    metrics.update(
        {
            "model": name,
            "model_seed": int(model_seed),
            "parameter_count": model_parameter_count(model),
            "trainable_parameter_count": sum(
                value.numel() for value in model.parameters() if value.requires_grad
            ),
            "training_seconds": fitted["training_seconds"],
            "epochs_run": fitted["epochs_run"],
            "offline_inference_seconds": inference_seconds,
            "statevector_evaluation_seconds": inference_seconds if quantum_statevector else 0.0,
            "analytical_feature_seconds": inference_seconds if name == "CAQF" else 0.0,
            "lambda_gap": loss.lambda_gap,
            "lambda_top1": loss.lambda_top1,
            "initialization_hash": initial_hash,
            "final_model_hash": state_dict_sha256(model),
        }
    )
    frame["model"] = name
    frame["model_seed"] = int(model_seed)
    return fitted, frame, metrics


def aggregate_controller_rows(rows: pd.DataFrame) -> pd.DataFrame:
    metrics = ("normalized_regret", "ndcg_at_5", "top1_accuracy", "spearman")
    named = {
        "normalized_regret": "regret",
        "ndcg_at_5": "ndcg",
        "top1_accuracy": "top1",
        "spearman": "spearman",
    }
    aggregations = {}
    for metric in metrics:
        aggregations[named[metric]] = (metric, "mean")
        aggregations[f"{named[metric]}_std"] = (metric, "std")
    for metric in (
        "parameter_count", "trainable_parameter_count", "training_seconds",
        "epochs_run", "offline_inference_seconds", "statevector_evaluation_seconds",
        "analytical_feature_seconds",
    ):
        aggregations[metric] = (metric, "mean")
    return rows.groupby("model", as_index=False).agg(**aggregations)


def paired_controller_statistics(frames: dict[str, pd.DataFrame], config: dict) -> pd.DataFrame:
    ordering = ["model_seed", "root_id", "workload"]
    rows = []
    pairs = (
        ("AQ", "NoQ-Gap"),
        ("QF-Gap", "NoQ-Gap"),
        ("AQ", "AQ-ZeroEnt"),
        ("AQ", "QF"),
        ("AQ", "CAQF"),
        ("QF", "CAQF"),
        ("AQ", "C2"),
        ("AQ", "C4"),
        ("AQ", "C5"),
        ("NoQ-Gap", "NoQ-Base"),
        ("QF-Gap", "QF"),
    )
    for pair_index, (left, right) in enumerate(pairs):
        for metric_index, metric in enumerate(
            ("normalized_regret", "ndcg_at_5", "top1_accuracy", "spearman")
        ):
            left_values = frames[left].sort_values(ordering)[metric].reset_index(drop=True)
            right_values = frames[right].sort_values(ordering)[metric].reset_index(drop=True)
            statistics = paired_bootstrap_difference(
                left_values,
                right_values,
                samples=int(config["controller"]["bootstrap_samples"]),
                seed=int(config["seed"]) + pair_index * 10 + metric_index,
            )
            rows.append({"left": left, "right": right, "metric": metric, **statistics})
    return pd.DataFrame(rows)


def caqf_equivalence_diagnostic(scalar_size: int, seed: int = 0) -> dict[str, float | str]:
    qf = create_final_model("QF", scalar_size, seed)
    caqf = create_final_model("CAQF", scalar_size, seed)
    caqf.load_state_dict(qf.state_dict(), strict=True)
    generator = np.random.default_rng(20260826)
    scalar = torch_from_numpy(generator.normal(size=(8, scalar_size)).astype(np.float32))
    spatial = torch_from_numpy(generator.normal(size=(8, 7, 4, 4)).astype(np.float32))
    with __import__("torch").no_grad():
        qf_features = qf.core.circuit_features(scalar, spatial)
        caqf_features = caqf.core.circuit_features(scalar, spatial)
    error = float(__import__("torch").max(__import__("torch").abs(qf_features - caqf_features)))
    return {
        "diagnostic": "QF_vs_CAQF_projected_features",
        "max_absolute_error": error,
        "status": "PASS" if error <= 1e-5 else "FAIL",
    }


def torch_from_numpy(values):
    import torch

    return torch.from_numpy(values)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
