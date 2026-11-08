"""Shared ranking, multitask training, evaluation, and model factory."""

from __future__ import annotations

import copy
import time

import numpy as np
import torch

from ..quantum.channel_tensor_encoding import ChannelTensorNormalizer
from ..quantum.cst_qvqc import CSTQuantumController
from ..quantum.old_additive_phase_vqc import OldAdditivePhaseVQC
from ..workload_action_interaction.metrics import aggregate_ranking, ranking_rows
from ..scorer import StrongSmallCNN
from .controls import FactorizedTensorController, ProjectedMLP, StandardReuploadingVQC, StrongCNN733
from .model import CPSRConfiguration, CPSRController


LOSS_WEIGHTS = {
    "A": (0.10, 0.10, 0.10),
    "B": (0.20, 0.10, 0.20),
    "C": (0.25, 0.15, 0.25),
}


def model_parameter_count(model):
    return sum(parameter.numel() for parameter in model.parameters())


class ScoreOnlyAdapter(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def task_outputs(self, scalar, spatial):
        score = self.model(scalar, spatial)
        return torch.stack((score, score, score, score), dim=1)

    def forward(self, scalar, spatial):
        return self.model(scalar, spatial)


def create_model(name, scalar_size, seed, *, cpsr_config=None, cst_normalizer=None):
    cpsr_config = cpsr_config or CPSRConfiguration()
    if name == "QB3":
        return StandardReuploadingVQC(scalar_size, seed, blocks=1)
    if name == "CPSR_NoEnt_111":
        return CPSRController(scalar_size, budget=111, config=cpsr_config, ablation="no_entangle", seed=seed)
    if name == "CPSR_111":
        return CPSRController(scalar_size, budget=111, config=cpsr_config, seed=seed)
    if name == "CPSR_733":
        return CPSRController(scalar_size, budget=733, config=cpsr_config, seed=seed)
    if name == "NoQ":
        return CPSRController(scalar_size, budget=733, config=cpsr_config, ablation="no_quantum", seed=seed)
    if name == "FrozenQ":
        return CPSRController(scalar_size, budget=733, config=cpsr_config, ablation="frozen_quantum", seed=seed)
    if name == "NoEnt":
        return CPSRController(scalar_size, budget=733, config=cpsr_config, ablation="no_entangle", seed=seed)
    if name == "C1":
        return ProjectedMLP(scalar_size, 111, seed)
    if name == "C3":
        return FactorizedTensorController(scalar_size, 111, seed)
    if name == "C4":
        return ProjectedMLP(scalar_size, 733, seed)
    if name == "C5":
        return FactorizedTensorController(scalar_size, 733, seed)
    if name == "C2":
        return StrongCNN733(scalar_size, seed)
    if name == "R4":
        return ScoreOnlyAdapter(StrongSmallCNN(scalar_size, seed))
    if name == "Qold":
        return ScoreOnlyAdapter(OldAdditivePhaseVQC(scalar_size, variant="geometry", seed=seed))
    if name == "CST":
        if cst_normalizer is None:
            raise ValueError("CST requires a train-only normalizer")
        return ScoreOnlyAdapter(CSTQuantumController(cst_normalizer, seed=seed))
    raise ValueError(name)


def standardize_scalar(scalar, train_indices):
    scalar = np.asarray(scalar, dtype=np.float32)
    values = scalar[np.asarray(train_indices)].reshape(-1, scalar.shape[-1])
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-6] = 1.0
    mean[-5:] = 0.0
    scale[-5:] = 1.0
    return ((scalar - mean) / scale).astype(np.float32), mean, scale


def channel_mask(spatial, channels):
    spatial = np.asarray(spatial, dtype=np.float32)
    result = spatial.copy()
    if channels == "compact":
        result[:, :, 4] = 0.0
    elif channels != "full":
        raise ValueError(channels)
    return result


def _normalized_auxiliary_targets(raw_metrics, valid):
    raw = np.asarray(raw_metrics, dtype=np.float32)[..., :3]
    output = np.zeros_like(raw)
    for group in range(len(raw)):
        legal = valid[group]
        for metric in range(3):
            values = raw[group, legal, metric]
            low, span = float(values.min()), max(float(np.ptp(values)), 1e-6)
            output[group, :, metric] = (raw[group, :, metric] - low) / span
    return output


def multitask_loss(outputs, costs, valid, auxiliary, tau, weights):
    scores = outputs[..., 0]
    masked_scores = scores.masked_fill(~valid, -1e9)
    target_logits = (-costs / float(tau)).masked_fill(~valid, -1e9)
    target_probability = torch.softmax(target_logits, dim=1)
    rank = -(target_probability * torch.log_softmax(masked_scores, dim=1)).sum(dim=1).mean()
    losses = []
    for metric in range(3):
        losses.append(torch.nn.functional.mse_loss(outputs[..., metric + 1][valid], auxiliary[..., metric][valid]))
    total = rank + sum(float(weight) * loss for weight, loss in zip(weights, losses, strict=True))
    return total, rank, losses


def _task_matrix(model, scalar, spatial):
    shape = scalar.shape[:2]
    flat_scalar = scalar.reshape(-1, scalar.shape[-1])
    flat_spatial = spatial.reshape(-1, *spatial.shape[-3:])
    if hasattr(model, "task_outputs"):
        output = model.task_outputs(flat_scalar, flat_spatial)
    else:
        score = model(flat_scalar, flat_spatial)
        output = torch.stack((score, score, score, score), dim=1)
    return output.reshape(shape[0], shape[1], 4)


def _batched_outputs(model, scalar, spatial, indices, batch_size):
    rows = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(indices), batch_size):
            index = torch.as_tensor(indices[start : start + batch_size], dtype=torch.long)
            rows.append(_task_matrix(model, scalar[index], spatial[index]).cpu().numpy())
    return np.concatenate(rows, axis=0)


def fit_model(
    model,
    data,
    train_indices,
    validation_indices,
    *,
    channels,
    label_split_train="oracle",
    label_split_validation="validation",
    seed,
    epochs,
    learning_rate,
    batch_size,
    patience,
    ranking_temperature,
    loss_weights,
):
    scalar, mean, scale = standardize_scalar(data.scalar, train_indices)
    spatial = channel_mask(data.spatial, channels)
    scalar_tensor = torch.from_numpy(scalar)
    spatial_tensor = torch.from_numpy(spatial)
    train_cost = torch.from_numpy(np.asarray(data.costs[label_split_train], dtype=np.float32))
    val_cost_np = np.asarray(data.costs[label_split_validation], dtype=np.float32)
    val_cost = torch.from_numpy(val_cost_np)
    valid = torch.from_numpy(np.asarray(data.valid, dtype=bool))
    train_aux = torch.from_numpy(_normalized_auxiliary_targets(data.raw_metrics[label_split_train], data.valid))
    rng = np.random.default_rng(int(seed) + 1701)
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.Adam(parameters, lr=float(learning_rate))
    best_state, best_objective, stale = copy.deepcopy(model.state_dict()), float("inf"), 0
    trace, started = [], time.perf_counter()
    for epoch in range(int(epochs)):
        model.train()
        shuffled = np.asarray(train_indices)[rng.permutation(len(train_indices))]
        gradient_values, losses = [], []
        epoch_started = time.perf_counter()
        for start in range(0, len(shuffled), int(batch_size)):
            index = torch.as_tensor(shuffled[start : start + int(batch_size)], dtype=torch.long)
            output = _task_matrix(model, scalar_tensor[index], spatial_tensor[index])
            loss, _rank, _aux = multitask_loss(
                output, train_cost[index], valid[index], train_aux[index], ranking_temperature, loss_weights
            )
            optimizer.zero_grad(); loss.backward()
            gradients = torch.cat([p.grad.flatten() for p in parameters if p.grad is not None])
            gradient_values.append(gradients.detach())
            optimizer.step(); losses.append(float(loss.detach()))
        validation_outputs = _batched_outputs(
            model, scalar_tensor, spatial_tensor, np.asarray(validation_indices), int(batch_size)
        )
        frame = ranking_rows(
            validation_outputs[..., 0], val_cost_np[validation_indices], data.valid[validation_indices],
            data.raw_metrics[label_split_validation][validation_indices], data.groups.iloc[validation_indices].reset_index(drop=True),
        )
        metrics = aggregate_ranking(frame)
        objective = metrics["normalized_regret"] + 0.25 * (1.0 - metrics["ndcg_at_5"])
        if objective < best_objective - 1e-7:
            best_objective, best_state, stale = objective, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
        gradient = torch.cat(gradient_values) if gradient_values else torch.zeros(1)
        trace.append({
            "epoch": epoch + 1, "loss": float(np.mean(losses)),
            "validation_normalized_regret": metrics["normalized_regret"],
            "validation_ndcg_at_5": metrics["ndcg_at_5"],
            "gradient_norm": float(torch.linalg.vector_norm(gradient)),
            "gradient_variance": float(torch.var(gradient)),
            "near_zero_gradient_ratio": float((torch.abs(gradient) < 1e-6).float().mean()),
            "epoch_seconds": time.perf_counter() - epoch_started,
        })
        if stale >= int(patience):
            break
    model.load_state_dict(best_state)
    return {
        "model": model, "scalar_mean": mean, "scalar_scale": scale, "channels": channels,
        "trace": trace, "training_seconds": time.perf_counter() - started,
        "epochs_run": len(trace), "best_validation_objective": best_objective,
    }


def evaluate_fitted(fitted, data, indices, *, label_split):
    scalar = (np.asarray(data.scalar, dtype=np.float32) - fitted["scalar_mean"]) / fitted["scalar_scale"]
    spatial = channel_mask(data.spatial, fitted["channels"])
    output = _batched_outputs(
        fitted["model"], torch.from_numpy(scalar), torch.from_numpy(spatial), np.asarray(indices), 32
    )
    groups = data.groups.iloc[indices].reset_index(drop=True)
    frame = ranking_rows(
        output[..., 0], data.costs[label_split][indices], data.valid[indices],
        data.raw_metrics[label_split][indices], groups,
    )
    return frame, aggregate_ranking(frame), output


def fit_cst_normalizer(data, train_indices):
    normalizer = ChannelTensorNormalizer()
    spatial = data.spatial[np.asarray(train_indices)].reshape(-1, 7, 4, 4)
    normalizer.fit(spatial)
    return normalizer
