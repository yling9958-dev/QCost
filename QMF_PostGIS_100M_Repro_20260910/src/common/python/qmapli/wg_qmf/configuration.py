"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Protocol, Sequence

import numpy as np

from ..workload_action_interaction.actions import (
    SplitAction,
    enumerate_actions,
    split_positions,
)

Bounds = tuple[float, float, float, float]

class ActionPriorScorer(Protocol):
    """Score legal actions. Higher values must mean better actions."""

    direction: str

    def score_actions(
        self,
        points: np.ndarray,
        context_queries: np.ndarray,
        actions: Sequence[SplitAction],
    ) -> np.ndarray: ...

@dataclass(frozen=True)
class PlannedAction:
    path: tuple[int, ...]
    action: SplitAction

@dataclass(frozen=True)
class LeafSummary:
    point_count: int
    bounds: Bounds

@dataclass(frozen=True)
class PartitionSummary:
    path: tuple[int, ...]
    left_bounds: Bounds
    right_bounds: Bounds

@dataclass(frozen=True)
class JointConfiguration:
    """One feasible full binary micro-subtree configuration."""

    actions: tuple[PlannedAction, ...]
    leaves: tuple[LeafSummary, ...]
    partitions: tuple[PartitionSummary, ...]
    prior_product: float
    depth: int

    @property
    def root_action(self) -> SplitAction:
        return self.actions[0].action

    @property
    def action_keys(self) -> tuple[str, ...]:
        return tuple(item.action.key for item in self.actions)

    @property
    def identifier(self) -> str:
        return "|".join(self.action_keys)

@dataclass(frozen=True)
class JointUniverse:
    configurations: tuple[JointConfiguration, ...]
    probabilities: np.ndarray
    greedy_configuration: JointConfiguration
    depth: int
    top_k: int | None
    prior_direction: str

    @property
    def size(self) -> int:
        return len(self.configurations)

    @property
    def search_qubits(self) -> int:
        return max(1, int(np.ceil(np.log2(max(self.size, 1)))))

    @property
    def greedy_index(self) -> int:
        key = self.greedy_configuration.identifier
        return next(
            index
            for index, configuration in enumerate(self.configurations)
            if configuration.identifier == key
        )

@dataclass(frozen=True)
class _Enumeration:
    plans: tuple[JointConfiguration, ...]
    greedy: JointConfiguration

def _bounds(points: np.ndarray) -> Bounds:
    values = np.asarray(points, dtype=np.float64)
    lower = np.asarray((values[:, 0].min(), values[:, 1].min()))
    upper = np.asarray((values[:, 0].max(), values[:, 1].max()))
    # Preserve reference signed-zero reduction behavior at degenerate bounds.
    if (lower == 0).any() or (upper == 0).any():
        lower, upper = values.min(axis=0), values.max(axis=0)
    return float(lower[0]), float(lower[1]), float(upper[0]), float(upper[1])

def _stable_softmax(scores: np.ndarray, *, temperature: float, epsilon: float) -> np.ndarray:
    values = np.asarray(scores, dtype=np.float64)
    if len(values) == 0:
        return values
    scale = float(values.std())
    normalized = np.zeros_like(values) if scale < 1e-12 else (values - values.mean()) / scale
    logits = normalized / float(temperature)
    weights = np.exp(logits - logits.max())
    weights = np.maximum(weights, float(epsilon))
    return weights / weights.sum()

def _prefix_plan(plan: JointConfiguration, prefix: int) -> JointConfiguration:
    bit = (int(prefix),)
    return JointConfiguration(
        actions=tuple(PlannedAction(bit + item.path, item.action) for item in plan.actions),
        leaves=plan.leaves,
        partitions=tuple(
            PartitionSummary(bit + item.path, item.left_bounds, item.right_bounds)
            for item in plan.partitions
        ),
        prior_product=plan.prior_product,
        depth=plan.depth,
    )

def _enumerate(
    points: np.ndarray,
    context_queries: np.ndarray,
    scorer: ActionPriorScorer,
    *,
    depth: int,
    top_k: int | None,
    minimum_fraction: float,
    temperature: float,
    epsilon: float,
    minimum_child_count: int | None,
) -> _Enumeration | None:
    actions = tuple(
        action
        for action in enumerate_actions(points, minimum_fraction)
        if action.valid
        and (
            minimum_child_count is None
            or min(action.left_count, action.right_count) >= int(minimum_child_count)
        )
    )
    if not actions:
        return None
    scores = np.asarray(
        scorer.score_actions(points, context_queries, actions), dtype=np.float64
    )
    if scores.shape != (len(actions),) or not np.isfinite(scores).all():
        raise ValueError("prior scorer must return one finite score per legal action")
    if getattr(scorer, "direction", "higher_is_better") != "higher_is_better":
        raise ValueError("the joint enumerator requires an audited higher-is-better scorer")
    ordered = sorted(
        range(len(actions)), key=lambda index: (-scores[index], actions[index].key)
    )
    if top_k is not None:
        ordered = ordered[: int(top_k)]
    selected_actions = tuple(actions[index] for index in ordered)
    selected_scores = scores[np.asarray(ordered, dtype=np.int64)]
    probabilities = _stable_softmax(
        selected_scores, temperature=temperature, epsilon=epsilon
    )

    feasible = []
    for action, probability in zip(selected_actions, probabilities, strict=True):
        left_positions, right_positions = split_positions(points, action)
        left_points = np.asarray(points[left_positions], dtype=np.float64)
        right_points = np.asarray(points[right_positions], dtype=np.float64)
        left_summary = LeafSummary(len(left_points), _bounds(left_points))
        right_summary = LeafSummary(len(right_points), _bounds(right_points))
        if depth == 1:
            feasible.append((action, float(probability), None, None, (), (), left_summary, right_summary))
            continue
        left = _enumerate(
            left_points,
            context_queries,
            scorer,
            depth=depth - 1,
            top_k=top_k,
            minimum_fraction=minimum_fraction,
            temperature=temperature,
            epsilon=epsilon,
            minimum_child_count=minimum_child_count,
        )
        right = _enumerate(
            right_points,
            context_queries,
            scorer,
            depth=depth - 1,
            top_k=top_k,
            minimum_fraction=minimum_fraction,
            temperature=temperature,
            epsilon=epsilon,
            minimum_child_count=minimum_child_count,
        )
        if left is None or right is None:
            continue
        feasible.append(
            (action, float(probability), left.greedy, right.greedy, left.plans, right.plans, left_summary, right_summary)
        )
    if not feasible:
        return None

    feasible_mass = sum(item[1] for item in feasible)
    plans: list[JointConfiguration] = []
    greedy_candidates: list[tuple[float, JointConfiguration]] = []
    for action, raw_probability, left_greedy, right_greedy, left_plans, right_plans, left_summary, right_summary in feasible:
        action_probability = raw_probability / feasible_mass
        root_partition = PartitionSummary((), left_summary.bounds, right_summary.bounds)
        root_action = PlannedAction((), action)
        if depth == 1:
            plan = JointConfiguration(
                actions=(root_action,),
                leaves=(left_summary, right_summary),
                partitions=(root_partition,),
                prior_product=action_probability,
                depth=1,
            )
            plans.append(plan)
            greedy_candidates.append((action_probability, plan))
            continue
        assert left_greedy is not None and right_greedy is not None
        prefixed_right_plans = tuple(_prefix_plan(plan, 1) for plan in right_plans)
        for left_plan in left_plans:
            prefixed_left = _prefix_plan(left_plan, 0)
            for right_plan, prefixed_right in zip(right_plans, prefixed_right_plans, strict=True):
                plans.append(
                    JointConfiguration(
                        actions=(root_action,) + prefixed_left.actions + prefixed_right.actions,
                        leaves=prefixed_left.leaves + prefixed_right.leaves,
                        partitions=(root_partition,) + prefixed_left.partitions + prefixed_right.partitions,
                        prior_product=(
                            action_probability
                            * left_plan.prior_product
                            * right_plan.prior_product
                        ),
                        depth=depth,
                    )
                )
        left_choice = _prefix_plan(left_greedy, 0)
        right_choice = _prefix_plan(right_greedy, 1)
        greedy_candidates.append(
            (
                action_probability,
                JointConfiguration(
                    actions=(root_action,) + left_choice.actions + right_choice.actions,
                    leaves=left_choice.leaves + right_choice.leaves,
                    partitions=(root_partition,) + left_choice.partitions + right_choice.partitions,
                    prior_product=(
                        action_probability
                        * left_greedy.prior_product
                        * right_greedy.prior_product
                    ),
                    depth=depth,
                ),
            )
        )
    greedy = min(
        greedy_candidates,
        key=lambda item: (-item[0], item[1].root_action.key),
    )[1]
    return _Enumeration(tuple(plans), greedy)

def enumerate_joint_configurations(
    points: np.ndarray,
    context_queries: np.ndarray,
    scorer: ActionPriorScorer,
    *,
    depth: int = 3,
    top_k: int | None = 4,
    minimum_fraction: float = 0.05,
    temperature: float = 1.0,
    epsilon: float = 1e-12,
    maximum_configurations: int = 16_384,
    minimum_child_count: int | None = None,
) -> JointUniverse:
    """Enumerate only feasible conditional action configurations.

    Candidate truncation is based solely on the scorer. No subtree cost is
    available to this function.
    """

    points = np.asarray(points, dtype=np.float64)
    context_queries = np.asarray(context_queries, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0:
        raise ValueError("points must be a non-empty [N,2] array")
    if context_queries.ndim != 2 or context_queries.shape[1] != 4:
        raise ValueError("context queries must be a [Q,4] array")
    if not 1 <= int(depth) <= 3:
        raise ValueError("lookahead depth must be in [1,3]")
    if top_k is not None and int(top_k) < 1:
        raise ValueError("top_k must be positive or None")
    result = _enumerate(
        points,
        context_queries,
        scorer,
        depth=int(depth),
        top_k=top_k,
        minimum_fraction=float(minimum_fraction),
        temperature=float(temperature),
        epsilon=float(epsilon),
        minimum_child_count=minimum_child_count,
    )
    if result is None:
        raise RuntimeError("no feasible full micro-subtree configuration")
    if len(result.plans) > int(maximum_configurations):
        raise RuntimeError(
            f"configuration universe {len(result.plans)} exceeds {maximum_configurations}"
        )
    probabilities = np.asarray(
        [plan.prior_product for plan in result.plans], dtype=np.float64
    )
    probabilities = np.maximum(probabilities, float(epsilon))
    probabilities /= probabilities.sum()
    return JointUniverse(
        configurations=result.plans,
        probabilities=probabilities,
        greedy_configuration=result.greedy,
        depth=int(depth),
        top_k=top_k,
        prior_direction=getattr(scorer, "direction", "unknown"),
    )
