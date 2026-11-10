#!/usr/bin/env python3
"""Run the retained four construction strategies and verify the resulting indexes."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
import pandas as pd
import torch
from qcost_repro.models import sha256
from qcost_repro.index_run import build_native
from qcost_repro.benchmarking import benchmark
from qmapli.wg_qmf.point_io import read_points
from qcost_experiments.comparison.common import CFG, LABELS
from qcost_experiments.comparison.four_strategies import build_index

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['QUICK', 'FULL'], default='QUICK')
    p.add_argument('--points', type=Path, required=True)
    p.add_argument('--queries', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--methods', nargs='+', choices=list(LABELS), default=list(LABELS))
    p.add_argument('--seeds', nargs='+', type=int)
    p.add_argument('--repetitions', type=int)
    a = p.parse_args()
    torch.set_num_threads(1)
    points, ids = read_points(a.points)
    if a.mode == 'FULL' and len(points) != 20000:
        p.error('The Figure 10 controlled protocol requires the original 20,000-point sample')
    protocol = json.loads((ROOT / 'configs/experiment_protocols.json').read_text())
    seeds = a.seeds or ([11] if a.mode == 'QUICK' else protocol['controlled_seeds'])
    repetitions = a.repetitions or (1 if a.mode == 'QUICK' else 5)
    queries = pd.read_csv(a.queries / 'train.csv')[['xmin', 'ymin', 'xmax', 'ymax']].to_numpy(float)
    a.output.mkdir(parents=True, exist_ok=False)
    library = build_native(a.output / 'native')
    (a.output / 'manifest.json').write_text(json.dumps(dict(mode=a.mode, seeds=seeds, config=CFG,
        points_sha256=sha256(a.points), query_sha256=sha256(a.queries / 'train.csv'),
        historical_sample_identity_verified=False, historical_paper_measurements=False), indent=2) + '\n')
    rows = []
    for seed in seeds:
        for method in a.methods:
            output = a.output / f'{method}_{seed}'
            output.mkdir()
            result = build_index((points, ids), queries, method, CFG, seed, output)
            (output / 'build_metrics.json').write_text(json.dumps(result, indent=2) + '\n')
            metrics = benchmark(library, output / 'index.idx', 'qmap_uniform_qmf',
                                points, ids, a.queries, output, repetitions)
            rows.append(dict(strategy=method, seed=seed, build_seconds=result['build_seconds'],
                             leaf_count=result['leaf_count'], lookahead_calls=result['lookahead_calls'], **metrics))
    (a.output / 'strategy_results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(rows, indent=2))

if __name__ == '__main__':
    main()
