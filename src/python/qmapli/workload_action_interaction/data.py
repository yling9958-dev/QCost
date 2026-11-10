"""Prepared node-workload-action tensors and sealed oracle labels."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .actions import enumerate_actions
from .oracle import CompiledOracle, aligned_action_arrays
from .queries import QUERY_SPLITS, WORKLOADS, aggregate_hash, isolated_query_splits
from .scalar_features import combined_scalar_features
from .spatial_maps import stacked_maps


@dataclass
class PreparedInteractionData:
    scalar: np.ndarray
    spatial: np.ndarray
    costs: dict[str, np.ndarray]
    raw_metrics: dict[str, np.ndarray]
    valid: np.ndarray
    groups: pd.DataFrame
    query_hashes: pd.DataFrame
    preparation_seconds: float


def _stable_seed(base: int, *parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return (int(base) + int.from_bytes(digest[:4], "little")) % (2**32 - 1)


def prepare_interaction_data(
    nodes,
    *,
    query_count: int,
    weights: dict[str, float],
    ambiguity_fraction: float,
    seed: int,
    progress=None,
) -> PreparedInteractionData:
    started = time.perf_counter()
    scalar_rows = []
    spatial_rows = []
    valid_rows = []
    costs = {split: [] for split in ("oracle", "validation", "test")}
    raw_metrics = {split: [] for split in ("oracle", "validation", "test")}
    group_rows = []
    hash_rows = []
    for node_index, node in enumerate(nodes):
        actions = enumerate_actions(node.points)
        scalar_action_rows = np.stack(
            [combined_scalar_features(node.points, action) for action in actions]
        )
        valid = np.asarray([action.valid for action in actions], dtype=bool)
        compiled = CompiledOracle(node.points)
        for workload in WORKLOADS:
            splits = isolated_query_splits(
                node.bbox,
                workload=workload,
                count=int(query_count),
                seed=_stable_seed(seed, node.node_id, workload),
            )
            spatial_action_rows = np.stack(
                [stacked_maps(node.points, splits["context"], action) for action in actions]
            )
            scalar_rows.append(scalar_action_rows)
            spatial_rows.append(spatial_action_rows)
            valid_rows.append(valid)
            group_index = len(group_rows)
            group_rows.append(
                {
                    "group_index": group_index,
                    "dataset": node.dataset,
                    "distribution_type": node.distribution_type,
                    "root_seed": node.root_seed,
                    "root_id": node.root_id,
                    "node_id": node.node_id,
                    "model_split": node.model_split,
                    "workload": workload,
                    "point_count": len(node.points),
                }
            )
            required_labels = {"test", {"train": "oracle", "validation": "validation", "test": "test"}[node.model_split]}
            for split in ("oracle", "validation", "test"):
                if split in required_labels:
                    result = compiled.evaluate(
                        splits[split],
                        weights=weights,
                        ambiguity_fraction=ambiguity_fraction,
                    )
                    split_costs, split_raw, split_valid = aligned_action_arrays(result, actions)
                    if not np.array_equal(valid, split_valid):
                        raise AssertionError("oracle action validity changed across query splits")
                else:
                    split_costs = np.full(len(actions), np.inf, dtype=np.float32)
                    split_raw = np.full((len(actions), 4), np.nan, dtype=np.float32)
                costs[split].append(split_costs)
                raw_metrics[split].append(split_raw)
            hashes = splits["hashes"]
            overlap = {
                f"{left}_{right}_overlap": len(hashes[left] & hashes[right])
                for left_index, left in enumerate(QUERY_SPLITS)
                for right in QUERY_SPLITS[left_index + 1 :]
            }
            for split in QUERY_SPLITS:
                hash_rows.append(
                    {
                        "node_id": node.node_id,
                        "root_id": node.root_id,
                        "workload": workload,
                        "query_split": split,
                        "query_count": len(splits[split]),
                        "sha256": aggregate_hash(hashes[split]),
                        **overlap,
                    }
                )
        if progress is not None and (node_index + 1) % 25 == 0:
            progress(node_index + 1, len(nodes))
    return PreparedInteractionData(
        scalar=np.asarray(scalar_rows, dtype=np.float32),
        spatial=np.asarray(spatial_rows, dtype=np.float32),
        costs={key: np.asarray(value, dtype=np.float32) for key, value in costs.items()},
        raw_metrics={key: np.asarray(value, dtype=np.float32) for key, value in raw_metrics.items()},
        valid=np.asarray(valid_rows, dtype=bool),
        groups=pd.DataFrame(group_rows),
        query_hashes=pd.DataFrame(hash_rows),
        preparation_seconds=time.perf_counter() - started,
    )
