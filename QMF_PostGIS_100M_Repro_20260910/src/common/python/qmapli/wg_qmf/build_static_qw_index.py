"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import argparse

import csv

import json

from pathlib import Path

import numpy as np

from .point_io import read_points

from .index import QWBuildConfig, build_qw_static_index

def _queries(path: Path) -> np.ndarray:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = [
            [float(row[key]) for key in ("xmin", "ymin", "xmax", "ymax")]
            for row in csv.DictReader(handle)
        ]
    return np.asarray(rows, dtype=np.float64)

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(("wg_qmf", "uniform_qmf", "beam16", "best_first", "greedy")), required=True)
    parser.add_argument("--r4-checkpoint", type=Path, required=True)
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--train-queries", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--context-seed", type=int, required=True)
    parser.add_argument("--beta-leaf", type=float, required=True)
    parser.add_argument("--beta-point", type=float, required=True)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--min-leaf-size", type=int, default=256)
    parser.add_argument("--max-leaves", type=int, default=128)
    parser.add_argument("--budget-factor", type=float, default=2.0)
    args = parser.parse_args(argv)
    points, identifiers = read_points(args.points)
    metadata = build_qw_static_index(
        mode=args.mode,
        r4_checkpoint=args.r4_checkpoint,
        points=points,
        ids=identifiers,
        train_queries=_queries(args.train_queries),
        output_path=args.index,
        context_seed=args.context_seed,
        beta_leaf=args.beta_leaf,
        beta_point=args.beta_point,
        build_config=QWBuildConfig(
            max_depth=args.max_depth,
            min_leaf_size=args.min_leaf_size,
            max_leaves=args.max_leaves,
            budget_sqrt_factor=args.budget_factor,
        ),
    )
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0

if __name__ == '__main__':
    import sys
    from ..repro import install_tree_audit
    install_tree_audit(Path(sys.argv[sys.argv.index('--index')+1]).parent/'tree_decision_manifest.csv')
    raise SystemExit(main())
