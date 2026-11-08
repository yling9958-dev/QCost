"""Parameter-identical classical controller used for Stage A representations."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .metrics import aggregate_ranking, ndcg_at_k, ranking_rows


CHANNEL_SCALES = torch.tensor((16.0, 16.0, 1.0, 1.0, 256.0, 16.0, 256.0))
REPRESENTATION_CHANNELS = {
    "R0": (),
    "R1": (0,),
    "R2": (0, 1),
    "R3": (0, 1, 2, 3),
    "R4": (0, 1, 2, 3, 4, 5, 6),
    "R4_minus_W": (0, 2, 3, 4, 5, 6),
    "R4_minus_B": (0, 1, 2, 4, 5, 6),
    "R4_minus_I_DQ": (0, 1, 2, 3, 5, 6),
    "R4_minus_I_QB": (0, 1, 2, 3, 4, 6),
    "R4_minus_I_DQB": (0, 1, 2, 3, 4, 5),
}


class FixedInteractionController(nn.Module):
    """One architecture for every R0-R4 and interaction ablation."""

    def __init__(self, scalar_size: int, seed: int):
        super().__init__()
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.cell_projection = nn.Conv2d(7, 4, kernel_size=1)
            self.spatial_mixing = nn.Conv2d(4, 4, kernel_size=3, padding=1)
            self.scalar_projection = nn.Linear(int(scalar_size), 8)
            self.fusion = nn.Linear(12, 8)
            self.output = nn.Linear(8, 1)

    def forward(self, scalar, spatial):
        shape = scalar.shape[:2]
        scalar_flat = scalar.reshape(-1, scalar.shape[-1])
        spatial_flat = spatial.reshape(-1, *spatial.shape[-3:])
        spatial_hidden = torch.tanh(self.cell_projection(spatial_flat))
        spatial_hidden = torch.tanh(self.spatial_mixing(spatial_hidden)).mean(dim=(-2, -1))
        scalar_hidden = torch.tanh(self.scalar_projection(scalar_flat))
        fused = torch.cat((scalar_hidden, spatial_hidden), dim=1)
        scores = self.output(torch.tanh(self.fusion(fused))).reshape(shape)
        return scores


@dataclass
class FittedController:
    model: FixedInteractionController
    scalar_mean: np.ndarray
    scalar_scale: np.ndarray
    channels: tuple[int, ...]
    trace: list[dict]
    training_seconds: float
    epochs_run: int
    parameter_count: int

    def score(self, scalar, spatial, batch_size=512):
        scalar = (np.asarray(scalar, dtype=np.float32) - self.scalar_mean) / self.scalar_scale
        spatial = masked_spatial(spatial, self.channels)
        rows = []
        self.model.eval()
        with torch.no_grad():
            for start in range(0, len(scalar), int(batch_size)):
                stop = start + int(batch_size)
                rows.append(
                    self.model(
                        torch.from_numpy(scalar[start:stop]),
                        torch.from_numpy(spatial[start:stop]),
                    ).cpu().numpy()
                )
        return np.vstack(rows)


def masked_spatial(spatial, channels):
    result = np.zeros_like(np.asarray(spatial, dtype=np.float32))
    if channels:
        result[:, :, channels] = np.asarray(spatial, dtype=np.float32)[:, :, channels]
    scales = CHANNEL_SCALES.numpy().reshape(1, 1, 7, 1, 1)
    return result * scales


def _loss(scores, costs, valid, tau, mse_weight):
    masked_scores = scores.masked_fill(~valid, -1e9)
    target_logits = (-costs / float(tau)).masked_fill(~valid, -1e9)
    target_probability = torch.softmax(target_logits, dim=1)
    ranking = -(target_probability * torch.log_softmax(masked_scores, dim=1)).sum(dim=1).mean()
    legal_count = valid.sum(dim=1, keepdim=True).clamp(min=1)
    target = -costs
    target_mean = (target * valid).sum(dim=1, keepdim=True) / legal_count
    variance = (((target - target_mean) * valid) ** 2).sum(dim=1, keepdim=True) / legal_count
    normalized_target = (target - target_mean) / torch.sqrt(variance.clamp(min=1e-6))
    centered_scores = scores - (scores * valid).sum(dim=1, keepdim=True) / legal_count
    mse = F.mse_loss(centered_scores[valid], normalized_target[valid])
    return ranking + float(mse_weight) * mse, ranking, mse


def _basic_metrics(scores, costs, valid):
    scores = np.asarray(scores)
    costs = np.asarray(costs)
    valid = np.asarray(valid)
    regrets = []
    ndcg = []
    for score_row, cost_row, valid_row in zip(scores, costs, valid, strict=True):
        legal = np.flatnonzero(valid_row)
        selected = legal[np.argmax(score_row[legal])]
        best = legal[np.argmin(cost_row[legal])]
        regrets.append(
            (cost_row[selected] - cost_row[best]) / max(float(np.ptp(cost_row[legal])), 1e-12)
        )
        ndcg.append(ndcg_at_k(score_row, cost_row, valid_row, 5))
    return float(np.mean(regrets)), float(np.mean(ndcg))


def fit_controller(
    scalar,
    spatial,
    costs,
    valid,
    train_indices,
    validation_indices,
    *,
    variant: str,
    seed: int,
    epochs: int,
    learning_rate: float,
    batch_size: int,
    patience: int,
    tau: float,
    mse_weight: float,
) -> FittedController:
    if variant not in REPRESENTATION_CHANNELS:
        raise ValueError(f"unknown representation variant {variant}")
    scalar = np.asarray(scalar, dtype=np.float32)
    train_scalar = scalar[np.asarray(train_indices)].reshape(-1, scalar.shape[-1])
    scalar_mean = train_scalar.mean(axis=0)
    scalar_scale = train_scalar.std(axis=0)
    scalar_scale[scalar_scale < 1e-6] = 1.0
    standardized = (scalar - scalar_mean) / scalar_scale
    selected_spatial = masked_spatial(spatial, REPRESENTATION_CHANNELS[variant])
    scalar_tensor = torch.from_numpy(standardized)
    spatial_tensor = torch.from_numpy(selected_spatial)
    cost_tensor = torch.from_numpy(np.asarray(costs, dtype=np.float32))
    valid_tensor = torch.from_numpy(np.asarray(valid, dtype=bool))
    train_indices = np.asarray(train_indices, dtype=np.int64)
    validation_indices = np.asarray(validation_indices, dtype=np.int64)
    model = FixedInteractionController(scalar.shape[-1], seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    generator = np.random.default_rng(int(seed) + 991)
    best_state = copy.deepcopy(model.state_dict())
    best_validation = float("inf")
    stale = 0
    trace = []
    started = time.perf_counter()
    for epoch in range(int(epochs)):
        epoch_started = time.perf_counter()
        model.train()
        shuffled = train_indices[generator.permutation(len(train_indices))]
        losses = []
        ranking_losses = []
        mse_losses = []
        for start in range(0, len(shuffled), int(batch_size)):
            index = torch.from_numpy(shuffled[start : start + int(batch_size)])
            scores = model(scalar_tensor[index], spatial_tensor[index])
            loss, ranking, mse = _loss(
                scores, cost_tensor[index], valid_tensor[index], tau, mse_weight
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
            ranking_losses.append(float(ranking.detach()))
            mse_losses.append(float(mse.detach()))
        model.eval()
        with torch.no_grad():
            validation_index_tensor = torch.from_numpy(validation_indices)
            validation_scores = model(
                scalar_tensor[validation_index_tensor], spatial_tensor[validation_index_tensor]
            )
            validation_loss, validation_ranking, validation_mse = _loss(
                validation_scores,
                cost_tensor[validation_index_tensor],
                valid_tensor[validation_index_tensor],
                tau,
                mse_weight,
            )
        validation_regret, validation_ndcg = _basic_metrics(
            validation_scores.cpu().numpy(),
            cost_tensor[validation_index_tensor].cpu().numpy(),
            valid_tensor[validation_index_tensor].cpu().numpy(),
        )
        value = float(validation_loss)
        if value < best_validation - 1e-7:
            best_validation = value
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
        trace.append(
            {
                "epoch": epoch + 1,
                "training_loss": float(np.mean(losses)),
                "ranking_loss": float(np.mean(ranking_losses)),
                "mse": float(np.mean(mse_losses)),
                "validation_loss": value,
                "validation_ranking_loss": float(validation_ranking),
                "validation_mse": float(validation_mse),
                "validation_normalized_regret": validation_regret,
                "validation_ndcg_at_5": validation_ndcg,
                "epoch_seconds": time.perf_counter() - epoch_started,
            }
        )
        if stale >= int(patience):
            break
    model.load_state_dict(best_state)
    return FittedController(
        model=model,
        scalar_mean=scalar_mean,
        scalar_scale=scalar_scale,
        channels=REPRESENTATION_CHANNELS[variant],
        trace=trace,
        training_seconds=time.perf_counter() - started,
        epochs_run=len(trace),
        parameter_count=sum(parameter.numel() for parameter in model.parameters()),
    )


def evaluate_fitted(controller, scalar, spatial, costs, valid, raw_metrics, groups):
    scores = controller.score(scalar, spatial)
    frame = ranking_rows(scores, costs, valid, raw_metrics, groups)
    return scores, frame, aggregate_ranking(frame)
