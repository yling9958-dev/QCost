"""Vectorized two-level oracle with the archived pilot cost definition."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from .actions import SplitAction, enumerate_actions, split_positions


@dataclass
class ActionEvaluation:
    action: SplitAction
    mean_candidate_count: float
    mean_visited_leaves: float
    cross_partition_rate: float
    imbalance_penalty: float
    normalized_candidate_count: float = 0.0
    normalized_visited_leaves: float = 0.0
    normalized_cross_partition_rate: float = 0.0
    normalized_imbalance_penalty: float = 0.0
    cost: float = 0.0
    rollout_actions: tuple[str, str] = ("", "")


@dataclass
class OracleResult:
    evaluations: list[ActionEvaluation]
    best_action: str
    ambiguous: bool
    normalized_margin: float

    def by_action(self) -> dict[str, ActionEvaluation]:
        return {row.action.key: row for row in self.evaluations}


@dataclass(frozen=True)
class _RootStructure:
    action: SplitAction
    left_options: tuple
    right_options: tuple


class CompiledOracle:
    """Query-independent two-level action structures compiled once per node."""

    def __init__(self, points: np.ndarray, minimum_fraction: float = 0.05):
        self.points = np.asarray(points, dtype=np.float64)
        self.minimum_fraction = float(minimum_fraction)
        self.bounds = (
            float(self.points[:, 0].min()),
            float(self.points[:, 1].min()),
            float(self.points[:, 0].max()),
            float(self.points[:, 1].max()),
        )
        structures = []
        for root_action in enumerate_actions(self.points, self.minimum_fraction):
            if not root_action.valid:
                continue
            left_positions, right_positions = split_positions(self.points, root_action)
            left_bounds, right_bounds = _split_bounds(self.bounds, root_action)
            structures.append(
                _RootStructure(
                    action=root_action,
                    left_options=tuple(
                        _leaf_options(
                            self.points, left_positions, left_bounds, self.minimum_fraction
                        )
                    ),
                    right_options=tuple(
                        _leaf_options(
                            self.points, right_positions, right_bounds, self.minimum_fraction
                        )
                    ),
                )
            )
        if not structures:
            raise RuntimeError("node has no legal split actions")
        self.structures = tuple(structures)

    def evaluate(self, queries, *, weights, ambiguity_fraction=0.01) -> OracleResult:
        return _evaluate_compiled(
            self,
            np.asarray(queries, dtype=np.float64),
            weights=weights,
            ambiguity_fraction=ambiguity_fraction,
        )


def _split_bounds(bounds, action: SplitAction):
    xmin, ymin, xmax, ymax = bounds
    if action.axis == 0:
        return (xmin, ymin, action.threshold, ymax), (action.threshold, ymin, xmax, ymax)
    return (xmin, ymin, xmax, action.threshold), (xmin, action.threshold, xmax, ymax)


def _leaf_options(points, positions, bounds, minimum_fraction):
    local = points[positions]
    options = []
    for action in enumerate_actions(local, minimum_fraction):
        if not action.valid:
            continue
        left_local, right_local = split_positions(local, action)
        left_bounds, right_bounds = _split_bounds(bounds, action)
        options.append(
            (
                action.key,
                ((len(left_local), left_bounds), (len(right_local), right_bounds)),
            )
        )
    if not options:
        options.append(("none", ((len(positions), bounds),)))
    return options


def _option_metrics(queries: np.ndarray, options):
    candidate, visited, counts = [], [], []
    for _key, leaves in options:
        hit_columns = []
        leaf_counts = []
        for count, (xmin, ymin, xmax, ymax) in leaves:
            hit_columns.append(
                (queries[:, 2] >= xmin)
                & (queries[:, 0] <= xmax)
                & (queries[:, 3] >= ymin)
                & (queries[:, 1] <= ymax)
            )
            leaf_counts.append(count)
        hits = np.column_stack(hit_columns)
        leaf_counts_array = np.asarray(leaf_counts, dtype=np.int64)
        candidate.append(float(np.mean(hits @ leaf_counts_array)))
        visited.append(float(np.mean(hits.sum(axis=1))))
        counts.append(tuple(leaf_counts))
    return np.asarray(candidate), np.asarray(visited), counts


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    minimum = values.min(axis=0)
    span = values.max(axis=0) - minimum
    span[span < 1e-12] = 1.0
    return (values - minimum) / span


def _evaluate_compiled(
    compiled: CompiledOracle,
    queries: np.ndarray,
    *,
    weights: dict[str, float],
    ambiguity_fraction: float = 0.01,
) -> OracleResult:
    queries = np.asarray(queries, dtype=np.float64)
    evaluations = []
    for structure in compiled.structures:
        root_action = structure.action
        left_options = structure.left_options
        right_options = structure.right_options
        left_candidate, left_visited, left_counts = _option_metrics(queries, left_options)
        right_candidate, right_visited, right_counts = _option_metrics(queries, right_options)
        candidate = left_candidate[:, None] + right_candidate[None, :]
        visited = left_visited[:, None] + right_visited[None, :]
        if root_action.axis == 0:
            crossed = (queries[:, 0] <= root_action.threshold) & (queries[:, 2] >= root_action.threshold)
        else:
            crossed = (queries[:, 1] <= root_action.threshold) & (queries[:, 3] >= root_action.threshold)
        cross = np.full_like(candidate, float(np.mean(crossed)))
        imbalance = np.empty_like(candidate)
        for left_index, right_index in product(range(len(left_options)), range(len(right_options))):
            leaf_counts = np.asarray((*left_counts[left_index], *right_counts[right_index]), dtype=np.float64)
            imbalance[left_index, right_index] = np.std(leaf_counts) / max(float(np.mean(leaf_counts)), 1.0)
        shape = candidate.shape
        raw = np.column_stack(
            (candidate.ravel(), visited.ravel(), cross.ravel(), imbalance.ravel())
        )
        normalized = _normalize(raw)
        costs = (
            weights["candidate"] * normalized[:, 0]
            + weights["visited_leaves"] * normalized[:, 1]
            + weights["cross_partition"] * normalized[:, 2]
            + weights["imbalance"] * normalized[:, 3]
        )
        indices = [(left, right) for left in range(shape[0]) for right in range(shape[1])]
        best_flat = min(
            range(len(indices)),
            key=lambda index: (
                costs[index],
                left_options[indices[index][0]][0],
                right_options[indices[index][1]][0],
            ),
        )
        left_index, right_index = indices[best_flat]
        metrics = raw[best_flat]
        evaluations.append(
            ActionEvaluation(
                root_action,
                *map(float, metrics),
                rollout_actions=(left_options[left_index][0], right_options[right_index][0]),
            )
        )
    raw_values = np.asarray(
        [
            (
                row.mean_candidate_count,
                row.mean_visited_leaves,
                row.cross_partition_rate,
                row.imbalance_penalty,
            )
            for row in evaluations
        ]
    )
    normalized = _normalize(raw_values)
    for row, values in zip(evaluations, normalized, strict=True):
        (
            row.normalized_candidate_count,
            row.normalized_visited_leaves,
            row.normalized_cross_partition_rate,
            row.normalized_imbalance_penalty,
        ) = map(float, values)
        row.cost = (
            weights["candidate"] * row.normalized_candidate_count
            + weights["visited_leaves"] * row.normalized_visited_leaves
            + weights["cross_partition"] * row.normalized_cross_partition_rate
            + weights["imbalance"] * row.normalized_imbalance_penalty
        )
    ordered = sorted(evaluations, key=lambda row: (row.cost, row.action.key))
    costs = np.asarray([row.cost for row in ordered])
    span = max(float(np.ptp(costs)), 1e-12)
    margin = float((costs[1] - costs[0]) / span) if len(costs) > 1 else 1.0
    return OracleResult(
        evaluations=evaluations,
        best_action=ordered[0].action.key,
        ambiguous=margin < float(ambiguity_fraction),
        normalized_margin=margin,
    )


def evaluate_oracle(
    points: np.ndarray,
    queries: np.ndarray,
    *,
    weights: dict[str, float],
    ambiguity_fraction: float = 0.01,
    minimum_fraction: float = 0.05,
) -> OracleResult:
    return CompiledOracle(points, minimum_fraction).evaluate(
        queries,
        weights=weights,
        ambiguity_fraction=ambiguity_fraction,
    )


def aligned_action_arrays(result: OracleResult, actions: list[SplitAction]):
    by_action = result.by_action()
    costs = np.full(len(actions), np.inf, dtype=np.float32)
    raw = np.full((len(actions), 4), np.nan, dtype=np.float32)
    valid = np.zeros(len(actions), dtype=bool)
    for index, action in enumerate(actions):
        if action.key not in by_action:
            continue
        row = by_action[action.key]
        costs[index] = row.cost
        raw[index] = (
            row.mean_candidate_count,
            row.mean_visited_leaves,
            row.cross_partition_rate,
            row.imbalance_penalty,
        )
        valid[index] = True
    return costs, raw, valid
