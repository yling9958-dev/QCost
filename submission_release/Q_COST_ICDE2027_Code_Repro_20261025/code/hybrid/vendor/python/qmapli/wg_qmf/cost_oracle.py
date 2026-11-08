"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Sequence

import numpy as np

from .configuration import JointConfiguration

from .cached_oracle import cached_work_metrics

@dataclass(frozen=True)
class CostTable:
    costs: np.ndarray
    mean_refined_points: np.ndarray
    mean_visited_leaves: np.ndarray
    mean_cross_partitions: np.ndarray
    distinct_costs: int
    cost_std: float
    best_worst_gap: float
    degenerate: bool
    query_split: str

def _intersects(bounds: np.ndarray, queries: np.ndarray) -> np.ndarray:
    return (
        (queries[None, :, 2, None] >= bounds[:, None, :, 0])
        & (queries[None, :, 0, None] <= bounds[:, None, :, 2])
        & (queries[None, :, 3, None] >= bounds[:, None, :, 1])
        & (queries[None, :, 1, None] <= bounds[:, None, :, 3])
    )

def evaluate_subtree_costs(
    configurations: Sequence[JointConfiguration],
    queries: np.ndarray,
    *,
    beta_leaf: float,
    beta_point: float,
    query_split: str = "train",
    batch_size: int = 512,
) -> CostTable:
    """Evaluate real temporary-tree work without consulting validation/test queries."""

    if query_split != "train":
        raise ValueError("the micro-subtree oracle may use TRAIN WORKLOAD ONLY")
    queries = np.asarray(queries, dtype=np.float64)
    if queries.ndim != 2 or queries.shape[1] != 4 or len(queries) == 0:
        raise ValueError("queries must be a non-empty [Q,4] array")
    if beta_leaf < 0 or beta_point < 0:
        raise ValueError("calibrated work coefficients must be non-negative")
    cached = cached_work_metrics(configurations, queries)
    if cached is not None:
        refined, visited, cross = cached
        return _cost_table(refined, visited, cross, beta_leaf, beta_point, query_split)
    refined_rows: list[np.ndarray] = []
    visited_rows: list[np.ndarray] = []
    cross_rows: list[np.ndarray] = []
    for start in range(0, len(configurations), int(batch_size)):
        batch = configurations[start : start + int(batch_size)]
        leaf_bounds = np.asarray(
            [[leaf.bounds for leaf in item.leaves] for item in batch], dtype=np.float64
        )
        leaf_counts = np.asarray(
            [[leaf.point_count for leaf in item.leaves] for item in batch], dtype=np.float64
        )
        hits = _intersects(leaf_bounds, queries)
        refined_rows.append(np.mean(np.einsum("bql,bl->bq", hits, leaf_counts), axis=1))
        visited_rows.append(np.mean(hits.sum(axis=2), axis=1))

        left_bounds = np.asarray(
            [[partition.left_bounds for partition in item.partitions] for item in batch],
            dtype=np.float64,
        )
        right_bounds = np.asarray(
            [[partition.right_bounds for partition in item.partitions] for item in batch],
            dtype=np.float64,
        )
        left_hits = _intersects(left_bounds, queries)
        right_hits = _intersects(right_bounds, queries)
        cross_rows.append(np.mean((left_hits & right_hits).sum(axis=2), axis=1))
    refined = np.concatenate(refined_rows)
    visited = np.concatenate(visited_rows)
    cross = np.concatenate(cross_rows)
    return _cost_table(refined, visited, cross, beta_leaf, beta_point, query_split)

def _cost_table(refined, visited, cross, beta_leaf, beta_point, query_split):
    costs = float(beta_leaf) * visited + float(beta_point) * refined
    rounded = np.round(costs, decimals=12)
    distinct = int(len(np.unique(rounded)))
    degenerate = bool(distinct <= max(1, int(np.ceil(0.10 * len(costs)))))
    return CostTable(
        costs=costs,
        mean_refined_points=refined,
        mean_visited_leaves=visited,
        mean_cross_partitions=cross,
        distinct_costs=distinct,
        cost_std=float(np.std(costs)),
        best_worst_gap=float(np.ptp(costs)),
        degenerate=degenerate,
        query_split=query_split,
    )
