#!/usr/bin/env python3
"""Fresh search, optimizer-efficiency and H/K runs using preserved research implementations."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
import numpy as np
import torch
from qmapli.wg_qmf.prior import FrozenR4Prior
from qmapli.wg_qmf.configuration import enumerate_joint_configurations
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs
from qcost_experiments.comparison.standalone_search import uniform_qmf, beam_search, _classical_result
from qcost_experiments.comparison.formal_beam import make_trie, beam
from qcost_experiments.comparison.comparison_adapter import run as optimizer_run
from qcost_repro import recursive_exact as exact
from qcost_repro.models import sha256
from qcost_repro.validation import verify_plan

def inputs(args):
    if args.mode == 'QUICK' and args.inputs_root is None:
        rng = np.random.default_rng(20260910)
        points = rng.random((4096, 2))
        centers = rng.random((12, 2))
        queries = np.c_[np.maximum(centers - .12, 0), np.minimum(centers + .12, 1)]
        yield dict(Node_ID='synthetic_quick', Dataset='synthetic', Cohort='QUICK'), points, queries
        return
    if args.inputs_root is None:
        raise ValueError('FULL requires --inputs-root with the original NODE_ID/input.npz files')
    rows = json.loads((ROOT / 'configs/NODE_MANIFEST.json').read_text())
    rows = [r for r in rows if r['Cohort'] == args.cohort and (not args.node or r['Node_ID'] in args.node)]
    if not rows:
        raise ValueError('No matching nodes')
    if args.limit_nodes:
        rows = rows[:args.limit_nodes]
    for row in rows:
        source = args.inputs_root / row['Input_File']
        if not source.is_file():
            raise FileNotFoundError(f'Missing frozen external node: {source}')
        if sha256(source) != row['Input_SHA256']:
            raise ValueError(f'Frozen node hash mismatch: {source}')
        with np.load(source, allow_pickle=False) as z:
            yield row, z['points'], z['queries']

def search(points, queries, scorer, seeds, budgets):
    started = time.perf_counter()
    universe = enumerate_joint_configurations(points, queries, scorer, depth=3, top_k=4,
        minimum_fraction=.05, minimum_child_count=256, maximum_configurations=16384)
    table = evaluate_subtree_costs(universe.configurations, queries,
                                   beta_leaf=exact.BL, beta_point=exact.BP)
    preparation = time.perf_counter() - started
    costs = table.costs
    started = time.perf_counter()
    trie = make_trie(universe)
    trie_seconds = time.perf_counter() - started
    labels = [(str(requested), min(requested, len(costs))) for requested in budgets]
    labels.append(('2sqrtN', min(int(math.ceil(2 * math.sqrt(len(costs)))), len(costs))))
    started = time.perf_counter()
    solver = exact.RecursiveExact(queries, scorer)
    solution = solver.solve(points, h=3)
    assert solution is not None
    recursive_plan = exact.reconstruct(solution, h=3)
    recursive_seconds = time.perf_counter() - started
    def signature(plan):
        return tuple((tuple(step.path), step.action.axis, float(step.action.threshold).hex()) for step in plan.actions)
    signatures = {signature(plan): i for i, plan in enumerate(universe.configurations)}
    recursive_index = signatures[signature(recursive_plan)]
    rows = []
    for budget in sorted({effective for requested, effective in labels}):
        for method in ['Analytic QMF', 'Random Search', 'Beam Search', 'Recursive Exact']:
            for seed in ([-1] if method in ['Beam Search','Recursive Exact'] else seeds):
                started = time.perf_counter()
                partial_expansions = 0
                if method == 'Analytic QMF':
                    result = uniform_qmf(costs, budget=budget, seed=seed)
                elif method == 'Random Search':
                    order = np.random.default_rng(seed).choice(len(costs), min(budget, len(costs)), replace=False)
                    result = _classical_result(method, costs, order, budget)
                elif method == 'Beam Search':
                    index, verifications, partial_expansions = beam(trie, costs, budget)
                    result = _classical_result(method, costs, [index], 1)
                else:
                    result = _classical_result(method, costs, [recursive_index], 1)
                elapsed = time.perf_counter() - started
                if method == 'Recursive Exact':
                    elapsed = recursive_seconds
                selected = universe.configurations[result.selected_index]
                # Evaluation and reference extraction take place after selection.
                legal, value = verify_plan(selected, points, queries)
                assert legal and np.isclose(value, result.selected_cost, rtol=1e-12)
                optimum = float(costs.min())
                root_best = min(float(c) for c, plan in zip(costs, universe.configurations)
                                if plan.root_action.key == selected.root_action.key and
                                plan.root_action.threshold == selected.root_action.threshold)
                tolerance = 8 * abs(np.spacing(optimum))
                for requested, effective in labels:
                    if effective != budget:
                        continue
                    rows.append(dict(method=method, budget=budget, budget_label=requested, seed=seed, H=3, K=4,
                    configurations=universe.size, selected_cost=value, optimal_cost=optimum,
                    optimal_configuration=bool(abs(value-optimum) <= tolerance),
                    optimal_root=bool(abs(root_best-optimum) <= tolerance), root_regret=max(0., root_best-optimum),
                    preparation_seconds=0. if method == 'Recursive Exact' else preparation, selection_seconds=elapsed,
                    verified_candidates=verifications if method == 'Beam Search' else len(result.evaluated_indices),
                    beam_partial_expansions=partial_expansions, beam_trie_seconds=trie_seconds,
                    equal_effective_budget_reused=sum(e == budget for _, e in labels) > 1,
                    abstract_threshold_calls=result.accounting.threshold_oracle_calls,
                    budget_scope='QMF: abstract threshold + verification; Random: distinct reads; Beam: width/reads; Recursive: uncapped direct reference',
                    validation='PASS'))
    return rows

def efficiency(points, queries, scorer, seed):
    rows = []
    for method in ['EXACT', 'QMF', 'M3', 'M8', 'C_STATE_OFF', 'C_TERM_OFF', 'C_CONFIG_OFF']:
        result = optimizer_run(points, queries, scorer, method, seed=seed, h=3, k=4, trace=False)
        if result['plan'] is not None:
            legal, value = verify_plan(result['plan'], points, queries)
            assert legal and np.isclose(value, result['stats']['selected_cost'], rtol=1e-12)
        else:
            legal, value = False, None
        rows.append(dict(method=method, seed=seed, H=3, K=4, cost=value,
                         validation='PASS' if legal else 'INFEASIBLE', stats=result['stats']))
    return rows

def sensitivity(points, queries, scorer, depths, widths, primary_repeats, other_repeats):
    rows = []
    old_k = exact.K
    try:
        for h in depths:
            for k in widths:
                exact.K = k
                for repeat in range(primary_repeats if h == 3 else other_repeats):
                    solver = exact.RecursiveExact(queries, scorer)
                    started = time.perf_counter()
                    solution = solver.solve(points, h=h)
                    elapsed = time.perf_counter() - started
                    cost = None
                    if solution is not None:
                        legal, cost = verify_plan(exact.reconstruct(solution, h=h), points, queries)
                        assert legal and np.isclose(cost, solution.cost, rtol=1e-12)
                    rows.append(dict(method='Recursive Exact', H=h, K=k, repetition=repeat,
                                     cost=cost, optimization_seconds=elapsed,
                                     configurations=solution.count if solution else 0,
                                     validation='PASS' if solution else 'INFEASIBLE', **solver.stats()))
    finally:
        exact.K = old_k
    return rows

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', choices=['search', 'efficiency', 'sensitivity'], required=True)
    p.add_argument('--mode', choices=['QUICK', 'FULL'], default='QUICK')
    p.add_argument('--inputs-root', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cohort', choices=['Original', 'Validation'], default='Original')
    p.add_argument('--node', action='append')
    p.add_argument('--limit-nodes', type=int)
    p.add_argument('--limit-seeds', type=int)
    a = p.parse_args()
    for limit in [a.limit_nodes, a.limit_seeds]:
        if limit is not None and limit < 1:
            p.error('limits must be positive')
    torch.set_num_threads(1 if a.mode == 'QUICK' else 4)
    protocol = json.loads((ROOT / 'configs/experiment_protocols.json').read_text())
    seeds = json.loads((ROOT / 'configs/seeds.json').read_text())
    seeds = seeds[:a.limit_seeds] if a.limit_seeds else (seeds[:1] if a.mode == 'QUICK' else seeds)
    a.output.mkdir(parents=True, exist_ok=False)
    model = FrozenR4Prior(ROOT / 'models/r4.pt')
    summary = []
    for node, points, queries in inputs(a):
        if a.task == 'search':
            rows = search(points, queries, model, seeds, protocol['search_budgets'])
        elif a.task == 'efficiency':
            rows = []
            for seed in seeds:
                rows.extend(efficiency(points, queries, model, seed))
        else:
            rows = sensitivity(points, queries, model, protocol['hk_depths'], protocol['hk_widths'],
                               1 if a.mode == 'QUICK' else protocol['hk_repetitions'],
                               protocol['hk_other_repetitions'])
        for r in rows:
            r.update(node=node['Node_ID'], dataset=node['Dataset'])
        (a.output / (node['Node_ID'] + '.json')).write_text(json.dumps(rows, indent=2) + '\n')
        summary.append(dict(node=node['Node_ID'], rows=len(rows), completed=True))
    manifest = dict(status='COMPLETE', task=a.task, mode=a.mode, nodes=summary, seeds=seeds,
        partial=bool(a.limit_nodes or a.limit_seeds or a.node or a.mode == 'QUICK'),
        historical_paper_measurements=False, model_sha256=sha256(ROOT / 'models/r4.pt'),
        threads=torch.get_num_threads(),
        timing_scope='Fresh portable whole-pipeline/selection timing; never replaces historical phase sums',
        beam='Deterministic; repeated seeds are repeated measurements, not independent random decisions')
    (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
