"""Leakage-controlled development and confirmatory data preparation."""

from __future__ import annotations

import hashlib
from pathlib import Path
import time

import numpy as np
import pandas as pd

from qmapli.workload_action_interaction.actions import enumerate_actions
from qmapli.workload_action_interaction.data import PreparedInteractionData
from qmapli.workload_action_interaction.distributions import synthetic_roots
from qmapli.workload_action_interaction.node_bank import SpatialNode
from qmapli.workload_action_interaction.oracle import CompiledOracle, aligned_action_arrays
from qmapli.workload_action_interaction.queries import QUERY_SPLITS, WORKLOADS, aggregate_hash, isolated_query_splits
from qmapli.workload_action_interaction.scalar_features import combined_scalar_features
from qmapli.workload_action_interaction.spatial_maps import stacked_maps


def _stable_seed(base: int, *parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return (int(base) + int.from_bytes(digest[:4], "little")) % (2**32 - 1)


def synthetic_nodes(config: dict, stage: str) -> list[SpatialNode]:
    data = config["data"]
    seeds = data[f"{stage}_seeds"]
    roots = synthetic_roots(data["distributions"], seeds, data["points_per_root"])
    train_seeds = set(data.get("development_train_seeds", ()))
    validation_seeds = set(data.get("development_validation_seeds", ()))
    nodes = []
    for root in roots:
        if stage == "confirmatory":
            split = "test"
        elif root.root_seed in train_seeds:
            split = "train"
        elif root.root_seed in validation_seeds:
            split = "validation"
        else:
            raise ValueError(f"development root seed {root.root_seed} has no registered split")
        nodes.append(
            SpatialNode(
                dataset=root.dataset,
                distribution_type=root.distribution_type,
                root_seed=root.root_seed,
                root_id=root.root_id,
                node_id=f"{root.root_id}:root",
                points=root.points,
                generation_method="fresh_root",
                model_split=split,
            )
        )
    return nodes


def prepare_fresh_data(nodes, config: dict, *, stage: str, progress=None) -> PreparedInteractionData:
    """Prepare only the label split allowed for each root's role."""

    if stage not in {"development", "confirmatory"}:
        raise ValueError(stage)
    started = time.perf_counter()
    scalar_rows, spatial_rows, valid_rows, group_rows, hash_rows = [], [], [], [], []
    costs = {key: [] for key in ("oracle", "validation", "test")}
    raw_metrics = {key: [] for key in ("oracle", "validation", "test")}
    query_count = int(config["data"]["query_count_per_split_per_workload"])
    weights = config["oracle"]["weights"]
    ambiguity = float(config["oracle"]["ambiguity_fraction"])
    for node_index, node in enumerate(nodes):
        actions = enumerate_actions(node.points)
        scalar_actions = np.stack([combined_scalar_features(node.points, action) for action in actions])
        valid = np.asarray([action.valid for action in actions], dtype=bool)
        compiled = CompiledOracle(node.points)
        allowed_label = {"train": "oracle", "validation": "validation", "test": "test"}[node.model_split]
        for workload in WORKLOADS:
            splits = isolated_query_splits(
                node.bbox,
                workload=workload,
                count=query_count,
                seed=_stable_seed(config["seed"], stage, node.node_id, workload),
            )
            scalar_rows.append(scalar_actions)
            spatial_rows.append(np.stack([stacked_maps(node.points, splits["context"], action) for action in actions]))
            valid_rows.append(valid)
            group_rows.append(
                {
                    "group_index": len(group_rows),
                    "stage": stage,
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
            for split in ("oracle", "validation", "test"):
                if split == allowed_label:
                    evaluated = compiled.evaluate(splits[split], weights=weights, ambiguity_fraction=ambiguity)
                    split_costs, split_raw, split_valid = aligned_action_arrays(evaluated, actions)
                    if not np.array_equal(split_valid, valid):
                        raise AssertionError("action validity changed across query splits")
                else:
                    split_costs = np.full(len(actions), np.inf, dtype=np.float32)
                    split_raw = np.full((len(actions), 4), np.nan, dtype=np.float32)
                costs[split].append(split_costs)
                raw_metrics[split].append(split_raw)
            hashes = splits["hashes"]
            overlaps = {
                f"{left}_{right}_overlap": len(hashes[left] & hashes[right])
                for left_index, left in enumerate(QUERY_SPLITS)
                for right in QUERY_SPLITS[left_index + 1 :]
            }
            for split in QUERY_SPLITS:
                hash_rows.append(
                    {
                        "stage": stage,
                        "node_id": node.node_id,
                        "root_id": node.root_id,
                        "workload": workload,
                        "query_split": split,
                        "query_count": len(splits[split]),
                        "sha256": aggregate_hash(hashes[split]),
                        **overlaps,
                    }
                )
        if progress and (node_index + 1) % 5 == 0:
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


def assert_query_isolation(*frames: pd.DataFrame) -> None:
    hashes: dict[str, set[str]] = {split: set() for split in QUERY_SPLITS}
    for frame in frames:
        for split in QUERY_SPLITS:
            hashes[split].update(frame.loc[frame.query_split == split, "sha256"].astype(str))
        overlap_columns = [column for column in frame if column.endswith("_overlap")]
        if overlap_columns and int(frame[overlap_columns].to_numpy().max(initial=0)) != 0:
            raise AssertionError("query split hash intersection is nonzero")
    # Aggregate hashes are distinct by construction and are audited explicitly.
    for left_index, left in enumerate(QUERY_SPLITS):
        for right in QUERY_SPLITS[left_index + 1 :]:
            if hashes[left] & hashes[right]:
                raise AssertionError(f"aggregate query hash collision: {left}/{right}")
