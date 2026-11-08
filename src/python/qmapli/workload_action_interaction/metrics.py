"""Action-ranking and selected-structure metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


RAW_METRIC_NAMES = (
    "candidate_count",
    "visited_leaves",
    "cross_partition_rate",
    "imbalance_penalty",
)


def ndcg_at_k(scores, costs, legal, k=5) -> float:
    legal = np.flatnonzero(legal)
    if not len(legal):
        return np.nan
    maximum = float(np.max(costs[legal]))
    relevance = np.maximum(maximum - costs[legal], 0.0)
    predicted_order = np.argsort(scores[legal])[::-1][:k]
    ideal_order = np.argsort(relevance)[::-1][:k]
    discounts = 1.0 / np.log2(np.arange(2, 2 + min(k, len(legal))))
    dcg = float(np.sum(relevance[predicted_order] * discounts))
    idcg = float(np.sum(relevance[ideal_order] * discounts))
    return 1.0 if idcg <= 1e-12 else dcg / idcg


def ranking_rows(scores, costs, valid, raw_metrics, groups: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for index, (score_row, cost_row, valid_row, raw_row) in enumerate(
        zip(scores, costs, valid, raw_metrics, strict=True)
    ):
        legal = np.flatnonzero(valid_row)
        selected = int(legal[np.argmax(score_row[legal])])
        oracle = int(legal[np.argmin(cost_row[legal])])
        cost_range = max(float(np.ptp(cost_row[legal])), 1e-12)
        correlation = spearmanr(score_row[legal], -cost_row[legal]).statistic
        metadata = groups.iloc[index].to_dict()
        rows.append(
            {
                **metadata,
                "selected_action_index": selected,
                "oracle_action_index": oracle,
                "normalized_regret": float((cost_row[selected] - cost_row[oracle]) / cost_range),
                "ndcg_at_5": ndcg_at_k(score_row, cost_row, valid_row, 5),
                "top1_accuracy": float(selected == oracle),
                "spearman": float(correlation) if np.isfinite(correlation) else 0.0,
                "ambiguous": bool(
                    np.partition(cost_row[legal], 1)[1] - np.min(cost_row[legal])
                    < 0.01 * cost_range
                ),
                **{
                    name: float(raw_row[selected, metric_index])
                    for metric_index, name in enumerate(RAW_METRIC_NAMES)
                },
                **{
                    f"oracle_{name}": float(raw_row[oracle, metric_index])
                    for metric_index, name in enumerate(RAW_METRIC_NAMES)
                },
            }
        )
    return pd.DataFrame(rows)


def aggregate_ranking(frame: pd.DataFrame) -> dict[str, float | int]:
    return {
        "normalized_regret": float(frame.normalized_regret.mean()),
        "ndcg_at_5": float(frame.ndcg_at_5.mean()),
        "top1_accuracy": float(frame.top1_accuracy.mean()),
        "spearman": float(frame.spearman.mean()),
        "candidate_count": float(frame.candidate_count.mean()),
        "visited_leaves": float(frame.visited_leaves.mean()),
        "cross_partition_rate": float(frame.cross_partition_rate.mean()),
        "ambiguous_groups": int(frame.ambiguous.sum()),
        "group_count": int(len(frame)),
    }


def workload_action_shift(costs, valid, groups: pd.DataFrame) -> pd.DataFrame:
    rows = []
    actions = []
    ambiguity = []
    for cost_row, valid_row in zip(costs, valid, strict=True):
        legal = np.flatnonzero(valid_row)
        ordered = legal[np.argsort(cost_row[legal])]
        span = max(float(np.ptp(cost_row[legal])), 1e-12)
        actions.append(int(ordered[0]))
        ambiguity.append(bool(cost_row[ordered[1]] - cost_row[ordered[0]] < 0.01 * span))
    temporary = groups.copy()
    temporary["oracle_action_index"] = actions
    temporary["ambiguous"] = ambiguity
    for node_id, group in temporary.groupby("node_id", sort=True):
        stable = group[~group.ambiguous]
        action_values = stable.oracle_action_index.to_numpy(dtype=int)
        pairs = [
            float(action_values[left] != action_values[right])
            for left in range(len(action_values))
            for right in range(left + 1, len(action_values))
        ]
        axes = action_values // 5
        quantiles = action_values % 5
        axis_pairs = [
            float(axes[left] != axes[right])
            for left in range(len(axes))
            for right in range(left + 1, len(axes))
        ]
        threshold_pairs = [
            float(quantiles[left] != quantiles[right])
            for left in range(len(quantiles))
            for right in range(left + 1, len(quantiles))
        ]
        rows.append(
            {
                "node_id": node_id,
                "root_id": group.iloc[0].root_id,
                "dataset": group.iloc[0].dataset,
                "distribution_type": group.iloc[0].distribution_type,
                "non_ambiguous_workloads": len(stable),
                "ambiguous_workloads": int(group.ambiguous.sum()),
                "distinct_actions": int(stable.oracle_action_index.nunique()),
                "action_change_rate": float(np.mean(pairs)) if pairs else np.nan,
                "axis_change_rate": float(np.mean(axis_pairs)) if axis_pairs else np.nan,
                "threshold_change_rate": float(np.mean(threshold_pairs)) if threshold_pairs else np.nan,
            }
        )
    return pd.DataFrame(rows)
