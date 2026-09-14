"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import hashlib

import heapq

import math

import resource

import time

from dataclasses import dataclass

from pathlib import Path

import numpy as np

from ..benchmark.geolife.qmap_static_format import export_compact_static_index as export_static_index

from ..final_full_scale.database_index import _ExportableIndex, _new_node

from ..indexes.qmap_nai.index import PrefixHybridIndex

from ..workload_action_interaction.actions import enumerate_actions, split_positions

from .configuration import enumerate_joint_configurations

from .cost_oracle import evaluate_subtree_costs

from .prior import FrozenR4Prior

from .search import (
    beam_search,
    prior_best_first,
    uniform_qmf,
    workload_guided_qmf,
)

SEARCH_MODES = frozenset(
    ("wg_qmf", "uniform_qmf", "beam16", "best_first", "greedy", "exact")
)

@dataclass(frozen=True)
class QWBuildConfig:
    max_depth: int = 8
    min_leaf_size: int = 256
    max_leaves: int = 128
    minimum_lookahead_points: int = 4096
    lookahead_depth: int = 3
    top_k: int = 4
    budget_sqrt_factor: float = 2.0
    suffix_strategy: str = "dual_axis_intersection"

def _intersecting_queries(queries: np.ndarray, mbr) -> np.ndarray:
    values = np.asarray(queries, dtype=np.float64)
    mask = (
        (values[:, 2] >= mbr[0])
        & (values[:, 0] <= mbr[2])
        & (values[:, 3] >= mbr[1])
        & (values[:, 1] <= mbr[3])
    )
    return values[mask]

def _greedy_action(points, queries, scorer, *, minimum_child_count: int = 1):
    actions = tuple(
        action
        for action in enumerate_actions(points)
        if action.valid
        and min(action.left_count, action.right_count) >= int(minimum_child_count)
    )
    if not actions:
        return None
    scores = scorer.score_actions(points, queries, actions)
    order = sorted(range(len(actions)), key=lambda index: (-scores[index], actions[index].key))
    return actions[order[0]]

def _stable_seed(context_seed: int, node_id: int, mode: str) -> int:
    value = hashlib.sha256(f"{context_seed}|{node_id}|{mode}".encode("utf-8")).digest()
    return int.from_bytes(value[:8], "little")

def _select_joint_root_action(
    *,
    mode: str,
    points: np.ndarray,
    train_queries: np.ndarray,
    scorer,
    beta_leaf: float,
    beta_point: float,
    node_id: int,
    context_seed: int,
    config: QWBuildConfig,
    trace=None,
) -> tuple[object | None, dict]:
    """Select a joint plan but expose only its root action to the tree builder."""

    if mode not in SEARCH_MODES:
        raise ValueError(f"unknown QW search mode: {mode}")
    if mode == "greedy":
        started = time.perf_counter()
        action = _greedy_action(
            points, train_queries, scorer, minimum_child_count=config.min_leaf_size
        )
        return action, {
            "configuration_count": 1,
            "configuration_generation_seconds": 0.0,
            "oracle_cost_seconds": 0.0,
            "search_seconds": time.perf_counter() - started,
            "threshold_oracle_calls": 0,
            "verification_cost_calls": 1 if action is not None else 0,
            "logical_quantum_operations": 0,
            "selected_cost": np.nan,
            "exact_cost": np.nan,
            "normalized_solution_gap": np.nan,
            "committed_actions": 1 if action is not None else 0,
        }

    prior_before = scorer.score_seconds
    enumeration_started = time.perf_counter()
    if trace is not None:
        trace.emit("before_h3_candidate_generation", node_id=node_id,
                   node_points=len(points), h=config.lookahead_depth, top_k=config.top_k)
    universe = enumerate_joint_configurations(
        points,
        train_queries,
        scorer,
        depth=config.lookahead_depth,
        top_k=config.top_k,
        minimum_fraction=0.05,
        minimum_child_count=config.min_leaf_size,
        temperature=1.0,
        epsilon=1e-12,
        maximum_configurations=16384,
    )
    enumeration_total = time.perf_counter() - enumeration_started
    prior_elapsed = scorer.score_seconds - prior_before
    if trace is not None:
        trace.emit("after_h3_candidate_generation", node_id=node_id,
                   node_points=len(points), configurations=universe.size)
    oracle_started = time.perf_counter()
    if trace is not None:
        trace.emit("during_candidate_evaluation", node_id=node_id,
                   node_points=len(points), configurations=universe.size)
    table = evaluate_subtree_costs(
        universe.configurations,
        train_queries,
        beta_leaf=beta_leaf,
        beta_point=beta_point,
        query_split="train",
    )
    oracle_seconds = time.perf_counter() - oracle_started
    if trace is not None:
        trace.emit("after_candidate_evaluation", node_id=node_id,
                   node_points=len(points), configurations=universe.size)
    budget = max(1, int(math.ceil(config.budget_sqrt_factor * math.sqrt(universe.size))))
    search_started = time.perf_counter()
    if mode == "wg_qmf":
        result = workload_guided_qmf(
            table.costs,
            universe.probabilities,
            budget=budget,
            seed=_stable_seed(context_seed, node_id, mode),
        )
    elif mode == "uniform_qmf":
        result = uniform_qmf(
            table.costs, budget=budget, seed=_stable_seed(context_seed, node_id, mode)
        )
    elif mode == "beam16":
        result = beam_search(table.costs, universe, width=16, budget=budget)
    elif mode == "best_first":
        result = prior_best_first(table.costs, universe.probabilities, budget=budget)
    elif mode == "exact":
        from .search import exhaustive_search

        result = exhaustive_search(table.costs)
    else:  # pragma: no cover - guarded above
        raise AssertionError(mode)
    search_seconds = time.perf_counter() - search_started
    optimum = float(table.costs.min())
    worst = float(table.costs.max())
    scale = max(worst - optimum, 1e-12)
    action = universe.configurations[result.selected_index].root_action
    return action, {
        "configuration_count": universe.size,
        "prior_scoring_seconds": prior_elapsed,
        "configuration_generation_seconds": max(enumeration_total - prior_elapsed, 0.0),
        "oracle_cost_seconds": oracle_seconds,
        "search_seconds": search_seconds,
        "threshold_oracle_calls": result.accounting.threshold_oracle_calls,
        "verification_cost_calls": result.accounting.verification_cost_calls,
        "logical_quantum_operations": result.accounting.total_logical_quantum_operations,
        "selected_cost": result.selected_cost,
        "exact_cost": optimum,
        "normalized_solution_gap": (result.selected_cost - optimum) / scale,
        "committed_actions": 1,
        "joint_plan_actions": len(universe.configurations[result.selected_index].actions),
        "cost_degenerate": table.degenerate,
    }

def build_qw_static_index(
    *,
    mode: str,
    r4_checkpoint: Path,
    points: np.ndarray,
    ids: np.ndarray,
    train_queries: np.ndarray,
    output_path: Path,
    context_seed: int,
    beta_leaf: float,
    beta_point: float,
    build_config: QWBuildConfig | None = None,
    trace=None,
) -> dict[str, object]:
    config = build_config or QWBuildConfig()
    points = np.asarray(points, dtype=np.float64)
    ids = np.asarray(ids, dtype=np.int64)
    train_queries = np.asarray(train_queries, dtype=np.float64)
    if mode not in SEARCH_MODES:
        raise ValueError(mode)
    if len(points) != len(ids) or not len(points):
        raise ValueError("points and IDs must be non-empty and aligned")
    if train_queries.ndim != 2 or train_queries.shape[1] != 4 or not len(train_queries):
        raise ValueError("train queries must be [N,4]")

    started = time.perf_counter()
    scorer = FrozenR4Prior(Path(r4_checkpoint))
    # The root membership is the identity range by definition. Materializing
    # np.arange(N) here adds a full int64 dataset copy during the peak H3 phase;
    # root split positions already are the required global indices.
    root = _new_node(
        points, np.empty(0, dtype=np.int64), 0, 0, 0, local_points=points
    )
    if trace is not None:
        trace.emit("root_initialization", node_id=0, node_depth=0,
                   node_points=len(points), planned_max_nodes=2 * config.max_leaves - 1,
                   points_bytes=points.nbytes, ids_bytes=ids.nbytes,
                   root_indices_bytes=root.point_indices.nbytes)
    queue = [(-len(points), root.node_id, root)]
    next_id = 1
    leaf_count = 1
    selected_actions: dict[str, int] = {}
    metrics = {
        "lookahead_nodes": 0,
        "fallback_nodes": 0,
        "configuration_count": 0,
        "configuration_generation_seconds": 0.0,
        "oracle_cost_seconds": 0.0,
        "quantum_search_simulator_seconds": 0.0,
        "threshold_oracle_calls": 0,
        "verification_cost_calls": 0,
        "logical_quantum_operations": 0,
        "normalized_solution_gaps": [],
    }
    processed_nodes = 0
    while queue and leaf_count < config.max_leaves:
        _priority, _identifier, node = heapq.heappop(queue)
        processed_nodes += 1
        identity_root = node is root
        node_point_count = len(points) if identity_root else len(node.point_indices)
        if node.depth >= config.max_depth or node_point_count < 2 * config.min_leaf_size:
            continue
        local = points if identity_root else points[node.point_indices]
        if trace is not None:
            trace.emit("recursive_build_milestone", node_id=node.node_id,
                       node_depth=node.depth, node_points=len(local),
                       completed_nodes=processed_nodes,
                       planned_max_nodes=2 * config.max_leaves - 1,
                       local_is_view=identity_root, leaf_count=leaf_count)
        local_queries = _intersecting_queries(train_queries, node.mbr)
        if not len(local_queries):
            del local
            continue
        try:
            if len(local) >= config.minimum_lookahead_points and mode != "greedy":
                action, detail = _select_joint_root_action(
                    mode=mode,
                    points=local,
                    train_queries=local_queries,
                    scorer=scorer,
                    beta_leaf=beta_leaf,
                    beta_point=beta_point,
                    node_id=node.node_id,
                    context_seed=context_seed,
                    config=config,
                    trace=trace,
                )
                metrics["lookahead_nodes"] += 1
                metrics["configuration_count"] += int(detail["configuration_count"])
                metrics["configuration_generation_seconds"] += float(
                    detail["configuration_generation_seconds"]
                )
                metrics["oracle_cost_seconds"] += float(detail["oracle_cost_seconds"])
                metrics["quantum_search_simulator_seconds"] += float(detail["search_seconds"])
                metrics["threshold_oracle_calls"] += int(detail["threshold_oracle_calls"])
                metrics["verification_cost_calls"] += int(detail["verification_cost_calls"])
                metrics["logical_quantum_operations"] += int(detail["logical_quantum_operations"])
                metrics["normalized_solution_gaps"].append(detail["normalized_solution_gap"])
            else:
                action = _greedy_action(
                    local,
                    local_queries,
                    scorer,
                    minimum_child_count=config.min_leaf_size,
                )
                metrics["fallback_nodes"] += 1
        except (RuntimeError, ValueError, MemoryError):
            action = _greedy_action(
                local,
                local_queries,
                scorer,
                minimum_child_count=config.min_leaf_size,
            )
            metrics["fallback_nodes"] += 1
        if action is None:
            del local
            continue
        left_local, right_local = split_positions(local, action)
        if min(len(left_local), len(right_local)) < config.min_leaf_size:
            del local, left_local, right_local
            continue
        if identity_root:
            left_indices, right_indices = left_local, right_local
        else:
            left_indices = node.point_indices[left_local]
            right_indices = node.point_indices[right_local]
        node.split_action = action
        node.threshold = action.threshold
        node.children = [
            _new_node(points, left_indices, node.depth + 1, int(node.prefix_code) << 1, next_id),
            _new_node(points, right_indices, node.depth + 1, (int(node.prefix_code) << 1) | 1, next_id + 1),
        ]
        next_id += 2
        leaf_count += 1
        selected_actions[action.key] = selected_actions.get(action.key, 0) + 1
        for child in node.children:
            heapq.heappush(queue, (-len(child.point_indices), child.node_id, child))
        if trace is not None:
            trace.emit("after_split_decision", node_id=node.node_id,
                       node_depth=node.depth, node_points=len(local),
                       completed_nodes=processed_nodes,
                       planned_max_nodes=2 * config.max_leaves - 1,
                       action=action.key, threshold=float(action.threshold).hex(),
                       left_count=len(left_indices), right_count=len(right_indices),
                       identity_root_reuse=identity_root)
        node.point_indices = np.empty(0, dtype=np.int64)
        del local, left_local, right_local, left_indices, right_indices

    # A deliberately unsplit root still represents every point. Defer the
    # identity membership until layout so it never overlaps H3 evaluation.
    if root.is_leaf and root.point_indices.size == 0:
        root.point_indices = np.arange(len(points), dtype=np.int64)

    stack = [root]
    sibling_overlap = []
    while stack:
        node = stack.pop()
        if node.is_leaf:
            node.suffix_strategy = config.suffix_strategy
            continue
        left, right = node.children
        ix = max(0.0, min(left.mbr[2], right.mbr[2]) - max(left.mbr[0], right.mbr[0]))
        iy = max(0.0, min(left.mbr[3], right.mbr[3]) - max(left.mbr[1], right.mbr[1]))
        parent_area = max((node.mbr[2] - node.mbr[0]) * (node.mbr[3] - node.mbr[1]), 1e-15)
        sibling_overlap.append(ix * iy / parent_area)
        stack.extend(node.children)
    layout_started = time.perf_counter()
    if trace is not None:
        trace.emit("before_layout", completed_nodes=processed_nodes,
                   planned_max_nodes=2 * config.max_leaves - 1, leaf_count=leaf_count)
    query_index = PrefixHybridIndex().build(points, ids, root, static_export=True, trace=trace)
    layout_seconds = time.perf_counter() - layout_started
    serialization_started = time.perf_counter()
    if trace is not None:
        trace.emit("before_serialization", point_count=len(query_index.points),
                   point_bytes=query_index.points.nbytes, id_bytes=query_index.ids.nbytes)
    serialized_bytes = export_static_index(_ExportableIndex(query_index), output_path)
    serialization_seconds = time.perf_counter() - serialization_started
    if trace is not None:
        trace.emit("after_serialization", serialized_bytes=serialized_bytes)
    leaves = np.asarray([
        node.storage_end - node.storage_start for node in query_index.leaves
    ], dtype=np.int64)
    gaps = np.asarray(metrics.pop("normalized_solution_gaps"), dtype=np.float64)
    return {
        "method": mode,
        "point_count": len(points),
        "node_count": len(query_index.nodes),
        "leaf_count": len(query_index.leaves),
        "tree_depth": max(node.depth for node in query_index.nodes),
        "leaf_size_min": int(leaves.min()),
        "leaf_size_mean": float(leaves.mean()),
        "leaf_size_p95": float(np.quantile(leaves, 0.95)),
        "leaf_size_max": int(leaves.max()),
        "mean_sibling_bbox_overlap": float(np.mean(sibling_overlap)) if sibling_overlap else 0.0,
        "prior_scoring_seconds": scorer.score_seconds,
        **metrics,
        "mean_normalized_solution_gap": float(gaps.mean()) if len(gaps) else np.nan,
        "oracle_calls_per_lookahead_node": (
            metrics["threshold_oracle_calls"] / max(metrics["lookahead_nodes"], 1)
        ),
        "layout_seconds": layout_seconds,
        "serialization_seconds": serialization_seconds,
        "index_build_seconds": time.perf_counter() - started,
        "serialized_bytes": serialized_bytes,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "selected_actions": selected_actions,
        "online_quantum_search": False,
        "online_python_controller": False,
        "committed_joint_actions_per_replan": 1,
        "minimum_lookahead_points": config.minimum_lookahead_points,
        "budget_sqrt_factor": config.budget_sqrt_factor,
        "suffix_strategy": config.suffix_strategy,
        "leaf_membership_sha256": query_index.leaf_membership_sha256,
    }
