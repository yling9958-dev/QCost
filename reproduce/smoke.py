#!/usr/bin/env python3
"""Data-free end-to-end check; all generated files stay in a fresh output directory."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))

import numpy as np
import pandas as pd
import torch
from qmapli.wg_qmf.prior import FrozenR4Prior
from qcost_repro.models import verify_models
from qcost_repro.data import prepare_points, write_queries, COORDINATES
from qcost_repro.training import prepare_training, train_models
from qcost_repro.index_run import build_native, run_index
from qcost_repro.validation import verify_plan
from qcost_experiments.ablation.hybrid_optimizer import optimize
from qcost_experiments.selection.hybrid_optimizer import optimize as selection_optimize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    models = verify_models()
    prepare_training(output / 'training-inputs', smoke=True)
    train_models(output / 'training-inputs/development.npz',
                 output / 'training-inputs/confirmatory.npz', output / 'trained-models',
                 models=['R4'], seeds=[0], epochs=1)
    prepare_points(output / 'points', kind='skewed', count=2048)
    write_queries(output / 'queries', metadata=output / 'points/metadata.json',
                  counts=dict(train=12, validation=4, correctness=6, warmup=3, performance=9))
    library = build_native(output / 'native')
    index_runs = [run_index(output / 'points/points.csv', output / 'queries', output / mode,
                            mode=mode, repetitions=1, native_library=library)
                  for mode in ['uniform_qmf', 'wg_qmf']]
    frame = pd.read_csv(output / 'points/points.csv')
    points = frame[['x', 'y']].to_numpy()
    queries = pd.read_csv(output / 'queries/train.csv')[COORDINATES].to_numpy()
    scorer = FrozenR4Prior(ROOT / 'models/r4.pt')
    variants = dict(Full={}, Random=dict(method='M4'), NoCache=dict(enable_cache=False),
                    NoFeedback=dict(enable_incumbent_feedback=False),
                    Enumeration=dict(direct_enumeration=True))
    costs = {}
    for name, options in variants.items():
        result = optimize(points, queries, scorer, h=2, k=2, seed=11, trace=False, **options)
        legal, cost = verify_plan(result['plan'], points, queries)
        assert legal and result['stats']['proven_optimal']
        assert np.isclose(cost, result['stats']['selected_cost'], rtol=1e-12, atol=1e-9)
        costs[name] = cost
    assert np.allclose(list(costs.values()), costs['Full'], rtol=1e-12, atol=1e-9)
    for name, method, feedback in [('QF', 'M8', True), ('RF', 'M4', True),
                                   ('QN', 'M8', False), ('RN', 'M4', False)]:
        result = selection_optimize(points, queries, scorer, method=method,
            enable_incumbent_feedback=feedback, h=2, k=2, seed=11, diagnostic=True, trace=False)
        legal, cost = verify_plan(result['plan'], points, queries)
        assert legal and result['stats']['proven_optimal']
        assert np.isclose(cost, costs['Full'], rtol=1e-12, atol=1e-9)
    receipt = dict(status='PASS', smoke_only=True, verified_original_models=len(models),
        training='R4, one epoch, isolated generated inputs',
        index_methods=[row['method'] for row in index_runs], ablation_costs=costs,
        selection_variants=['QF', 'RF', 'QN', 'RN'], historical_paper_measurements=False)
    (output / 'SMOKE_RESULT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
