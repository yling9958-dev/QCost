"""Leakage-safe ranking losses for CPSR-AQ."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as functional


LOSS_OPTIONS = {
    "A": {"lambda_gap": 0.25, "lambda_top1": 0.25},
    "B": {"lambda_gap": 0.50, "lambda_top1": 0.25},
    "C": {"lambda_gap": 0.50, "lambda_top1": 0.50},
}


def positive_cost_gap_scale(costs, valid) -> float:
    """Median positive pairwise cost gap, using only registered train labels."""

    costs = np.asarray(costs, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    gaps = []
    for row, legal in zip(costs, valid, strict=True):
        values = row[legal]
        differences = np.abs(values[:, None] - values[None, :])
        gaps.extend(differences[differences > 0].tolist())
    return max(float(np.median(gaps)) if gaps else 0.0, 1e-6)


def cost_gap_weights(delta: torch.Tensor, scale: float) -> torch.Tensor:
    return torch.clamp(delta / (float(scale) + 1e-12), min=0.0, max=3.0)


def listwise_ranking_loss(scores, costs, valid, temperature: float):
    masked_scores = scores.masked_fill(~valid, -1e9)
    target_logits = (-costs / float(temperature)).masked_fill(~valid, -1e9)
    target = torch.softmax(target_logits, dim=1)
    return -(target * torch.log_softmax(masked_scores, dim=1)).sum(dim=1).mean()


def gap_ranking_loss(scores, costs, valid, cost_scale: float):
    # Row i, column j is a preferred pair when C_j - C_i > 0.
    safe_costs = torch.where(valid, costs, torch.zeros_like(costs))
    delta = safe_costs.unsqueeze(1) - safe_costs.unsqueeze(2)
    pair_valid = valid.unsqueeze(1) & valid.unsqueeze(2) & (delta > 0)
    score_difference = scores.unsqueeze(2) - scores.unsqueeze(1)
    weighted = cost_gap_weights(delta, cost_scale) * functional.softplus(-score_difference)
    denominator = pair_valid.sum().clamp_min(1)
    return torch.where(pair_valid, weighted, torch.zeros_like(weighted)).sum() / denominator


def top1_ranking_loss(scores, costs, valid):
    masked_scores = scores.masked_fill(~valid, -1e9)
    masked_costs = costs.masked_fill(~valid, torch.inf)
    targets = torch.argmin(masked_costs, dim=1)
    return functional.cross_entropy(masked_scores, targets)


def combined_ranking_loss(
    scores,
    costs,
    valid,
    *,
    ranking_temperature: float,
    cost_scale: float,
    lambda_gap: float,
    lambda_top1: float,
    sparse_penalty: torch.Tensor | None = None,
    lambda_sparse: float = 0.0,
):
    listwise = listwise_ranking_loss(scores, costs, valid, ranking_temperature)
    gap = gap_ranking_loss(scores, costs, valid, cost_scale)
    top1 = top1_ranking_loss(scores, costs, valid)
    sparse = scores.new_zeros(()) if sparse_penalty is None else sparse_penalty
    total = (
        listwise
        + float(lambda_gap) * gap
        + float(lambda_top1) * top1
        + float(lambda_sparse) * sparse
    )
    return total, {"listwise": listwise, "gap": gap, "top1": top1, "sparse": sparse}
