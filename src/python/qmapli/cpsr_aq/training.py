"""Common ranking trainer for CPSR-AQ and all controller controls."""

from __future__ import annotations

import copy
import time

import numpy as np
import torch

from ..cpsr_vqc.training import channel_mask, standardize_scalar
from ..workload_action_interaction.metrics import aggregate_ranking, ranking_rows
from .losses import combined_ranking_loss, positive_cost_gap_scale
from .model import CPSRAQController


def _flat_task_scores(model, scalar, spatial):
    shape = scalar.shape[:2]
    flat_scalar = scalar.reshape(-1, scalar.shape[-1])
    flat_spatial = spatial.reshape(-1, *spatial.shape[-3:])
    if hasattr(model, "task_outputs"):
        scores = model.task_outputs(flat_scalar, flat_spatial)[:, 0]
    else:
        scores = model(flat_scalar, flat_spatial)
    return scores.reshape(shape)


def score_groups(model, scalar, spatial, valid):
    if isinstance(model, CPSRAQController):
        return model.group_scores(scalar, spatial, valid)
    scores = _flat_task_scores(model, scalar, spatial)
    margin = CPSRAQController.classical_margin(scores, valid)
    return {
        "scores": scores,
        "classical_scores": scores,
        "quantum_scores": torch.zeros_like(scores),
        "quantum_gate": torch.zeros(len(scores), device=scores.device),
        "classical_margin": margin,
    }


def _batched_scores(model, scalar, spatial, valid, indices, batch_size):
    output = {key: [] for key in (
        "scores", "classical_scores", "quantum_scores", "quantum_gate", "classical_margin"
    )}
    model.eval()
    with torch.no_grad():
        for start in range(0, len(indices), int(batch_size)):
            index = torch.as_tensor(indices[start : start + int(batch_size)], dtype=torch.long)
            result = score_groups(model, scalar[index], spatial[index], valid[index])
            for key in output:
                output[key].append(result[key].detach().cpu().numpy())
    return {key: np.concatenate(values, axis=0) for key, values in output.items()}


def selection_objective(metrics):
    return (
        metrics["normalized_regret"]
        + 0.30 * (1.0 - metrics["ndcg_at_5"])
        + 0.10 * (1.0 - metrics["top1_accuracy"])
    )


def fit_ranking_model(
    model,
    data,
    train_indices,
    validation_indices,
    *,
    seed: int,
    epochs: int,
    learning_rate: float,
    batch_size: int,
    patience: int,
    ranking_temperature: float,
    lambda_gap: float,
    lambda_top1: float,
    lambda_sparse: float = 0.0,
):
    train_indices = np.asarray(train_indices, dtype=int)
    validation_indices = np.asarray(validation_indices, dtype=int)
    scalar, scalar_mean, scalar_scale = standardize_scalar(data.scalar, train_indices)
    spatial = channel_mask(data.spatial, "full")
    scalar_tensor = torch.from_numpy(scalar)
    spatial_tensor = torch.from_numpy(spatial)
    valid_tensor = torch.from_numpy(np.asarray(data.valid, dtype=bool))
    train_cost_np = np.asarray(data.costs["oracle"], dtype=np.float32)
    validation_cost_np = np.asarray(data.costs["validation"], dtype=np.float32)
    train_cost = torch.from_numpy(train_cost_np)
    cost_scale = positive_cost_gap_scale(train_cost_np[train_indices], data.valid[train_indices])
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.Adam(parameters, lr=float(learning_rate))
    rng = np.random.default_rng(int(seed) + 3401)
    best_state = copy.deepcopy(model.state_dict())
    best_objective, stale = float("inf"), 0
    trace, started = [], time.perf_counter()
    for epoch in range(int(epochs)):
        model.train()
        shuffled = train_indices[rng.permutation(len(train_indices))]
        epoch_losses, gradient_batches = [], []
        epoch_components = {key: [] for key in ("listwise", "gap", "top1", "sparse")}
        epoch_started = time.perf_counter()
        for start in range(0, len(shuffled), int(batch_size)):
            index = torch.as_tensor(shuffled[start : start + int(batch_size)], dtype=torch.long)
            result = score_groups(
                model, scalar_tensor[index], spatial_tensor[index], valid_tensor[index]
            )
            sparse = model.sparse_penalty() if isinstance(model, CPSRAQController) else None
            loss, components = combined_ranking_loss(
                result["scores"], train_cost[index], valid_tensor[index],
                ranking_temperature=ranking_temperature,
                cost_scale=cost_scale,
                lambda_gap=lambda_gap,
                lambda_top1=lambda_top1,
                sparse_penalty=sparse,
                lambda_sparse=lambda_sparse,
            )
            optimizer.zero_grad()
            loss.backward()
            gradients = [parameter.grad.flatten() for parameter in parameters if parameter.grad is not None]
            if gradients:
                gradient_batches.append(torch.cat(gradients).detach().cpu())
            optimizer.step()
            epoch_losses.append(float(loss.detach()))
            for key, value in components.items():
                epoch_components[key].append(float(value.detach()))
        validation_output = _batched_scores(
            model, scalar_tensor, spatial_tensor, valid_tensor, validation_indices, batch_size
        )
        frame = ranking_rows(
            validation_output["scores"],
            validation_cost_np[validation_indices],
            data.valid[validation_indices],
            data.raw_metrics["validation"][validation_indices],
            data.groups.iloc[validation_indices].reset_index(drop=True),
        )
        metrics = aggregate_ranking(frame)
        objective = selection_objective(metrics)
        if objective < best_objective - 1e-8:
            best_objective, best_state, stale = objective, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
        gradients = torch.cat(gradient_batches) if gradient_batches else torch.zeros(1)
        gates = (
            model.edge_gate_values.detach().cpu().numpy()
            if isinstance(model, CPSRAQController)
            else np.zeros(9)
        )
        trace.append(
            {
                "epoch": epoch + 1,
                "loss": float(np.mean(epoch_losses)),
                **{f"loss_{key}": float(np.mean(values)) for key, values in epoch_components.items()},
                "validation_normalized_regret": metrics["normalized_regret"],
                "validation_ndcg_at_5": metrics["ndcg_at_5"],
                "validation_top1_accuracy": metrics["top1_accuracy"],
                "selection_objective": objective,
                "gradient_norm": float(torch.linalg.vector_norm(gradients)),
                "gradient_variance": float(torch.var(gradients)),
                "near_zero_gradient_ratio": float((torch.abs(gradients) < 1e-6).float().mean()),
                "mean_edge_gate": float(np.mean(gates)),
                "active_edge_count": int(np.sum(gates >= 0.20)),
                "epoch_seconds": time.perf_counter() - epoch_started,
            }
        )
        if stale >= int(patience):
            break
    model.load_state_dict(best_state)
    return {
        "model": model,
        "scalar_mean": scalar_mean,
        "scalar_scale": scalar_scale,
        "trace": trace,
        "training_seconds": time.perf_counter() - started,
        "epochs_run": len(trace),
        "best_validation_objective": best_objective,
        "cost_gap_scale": cost_scale,
    }


def evaluate_fitted(fitted, data, indices, *, label_split: str):
    indices = np.asarray(indices, dtype=int)
    scalar = (
        np.asarray(data.scalar, dtype=np.float32) - fitted["scalar_mean"]
    ) / fitted["scalar_scale"]
    spatial = channel_mask(data.spatial, "full")
    output = _batched_scores(
        fitted["model"],
        torch.from_numpy(scalar),
        torch.from_numpy(spatial),
        torch.from_numpy(np.asarray(data.valid, dtype=bool)),
        indices,
        32,
    )
    groups = data.groups.iloc[indices].reset_index(drop=True)
    frame = ranking_rows(
        output["scores"],
        data.costs[label_split][indices],
        data.valid[indices],
        data.raw_metrics[label_split][indices],
        groups,
    )
    frame["classical_margin"] = output["classical_margin"]
    frame["quantum_gate"] = output["quantum_gate"]
    return frame, aggregate_ranking(frame), output


def fitted_margins(fitted, data, indices):
    indices = np.asarray(indices, dtype=int)
    scalar = (
        np.asarray(data.scalar, dtype=np.float32) - fitted["scalar_mean"]
    ) / fitted["scalar_scale"]
    output = _batched_scores(
        fitted["model"],
        torch.from_numpy(scalar),
        torch.from_numpy(channel_mask(data.spatial, "full")),
        torch.from_numpy(np.asarray(data.valid, dtype=bool)),
        indices,
        32,
    )
    return output["classical_margin"], output
