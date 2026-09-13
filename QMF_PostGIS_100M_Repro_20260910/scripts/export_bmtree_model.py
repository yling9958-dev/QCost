#!/usr/bin/env python3
"""Build a compact GeoLife code export with the locked official BMTree code."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd


LOCKED_REVISION = "230ead0d82489b2f199baf165b0efa5f0c99b8c7"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--train-queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--training-points", type=int, default=2000)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--rollouts", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1)
    return parser.parse_args()


def load_points(path: Path):
    frame = pd.read_csv(
        path,
        usecols=("id", "x", "y"),
        dtype={"id": np.int64, "x": np.float64, "y": np.float64},
    )
    return frame["id"].to_numpy(copy=True), frame[["x", "y"]].to_numpy(copy=True)


def load_queries(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return np.asarray(
            [[float(row[key]) for key in ("xmin", "ymin", "xmax", "ymax")]
             for row in csv.DictReader(handle)],
            dtype=np.float64,
        )


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    sys.path.insert(0, str(args.source.resolve()))
    from bmtree.bmtree_env import BMTEnv
    from int2binary import Int2BinaryTransformer
    from mcts import MCTS
    from utils.metric_compute import ExperimentEnv
    from utils.query import Query

    ids, points = load_points(args.points)
    queries = load_queries(args.train_queries)
    scale = (1 << 16) - 1
    integer_points = np.floor(np.clip(points, 0, 1) * scale).astype(np.int64)
    integer_queries = np.floor(np.clip(queries, 0, 1) * scale).astype(np.int64)
    sample_positions = np.linspace(
        0, len(integer_points) - 1, min(args.training_points, len(integer_points)), dtype=np.int64
    )
    training_points = integer_points[sample_positions].tolist()
    training_queries = [Query(row.tolist()) for row in integer_queries]
    transformer = Int2BinaryTransformer([scale, scale])
    environment = BMTEnv(
        training_points,
        training_queries,
        [16, 16],
        None,
        transformer,
        2,
        args.depth,
    )
    environment.generate_tree_zorder(1)
    metric = ExperimentEnv(training_points, environment.tree, module_name="bmtree", pagesize=64, core_num=1)
    metric.order_generate()
    base_cost = metric.fast_compute_scan_range(training_queries)
    environment.reset()
    metric.change_module(environment.tree, module_name="bmtree")
    metric.order_generate()
    search = MCTS(base_cost, environment.tree, max_depth=args.depth, split_depth=max(1, args.depth - 1))
    rollout_costs = []
    for _depth in range(args.depth):
        for _ in range(args.rollouts):
            _path, cost = search.do_rollout(environment.tree, metric, training_queries)
            rollout_costs.append(float(cost))
        actions, _reward = search.choose(environment.tree)
        environment.tree.multi_action(actions)
    action_stream = environment.tree.get_all_states()[0]
    schedule = "".join(action_stream[index] for index in range(0, len(action_stream), 2)) or "10"
    codes = [environment.tree.output(point.tolist()) for point in integer_points]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        handle.write("version 1\n")
        handle.write(f"schedule {schedule}\n")
        handle.write(f"codes {len(codes)}\n")
        for identifier, code in zip(ids, codes, strict=True):
            handle.write(f"{int(identifier)} {int(code)}\n")
    metadata = {
        "source_revision": LOCKED_REVISION,
        "implementation": "official Tree/BMTEnv/MCTS",
        "training_points": len(training_points),
        "training_queries": len(training_queries),
        "depth": args.depth,
        "rollouts_per_depth": args.rollouts,
        "seed": args.seed,
        "base_scan_range": float(base_cost),
        "rollout_costs": rollout_costs,
        "action_stream": action_stream,
        "schedule_prefix": schedule,
        "point_count": len(codes),
    }
    args.metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
