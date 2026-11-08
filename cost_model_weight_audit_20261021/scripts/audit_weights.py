"""Read-only audit of frozen cost weights and already materialized cost tables.

No optimizer, model, simulator, database query, or index builder is invoked.
Only derived audit files beneath this script's parent output directory are written.
"""
from pathlib import Path
import ast
import csv
import hashlib
import json
import sys
import time

import numpy as np
import pandas as pd

BASE = Path('/media/lingyaqi/Lenovo F510')
PROJECT = BASE / 'QMap-LI'
STUDY = BASE / 'QMF-Motivation-Study'
PHASES = BASE / 'Q-COST-QMF-Necessity-Study'
OUT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def constants(path):
    result = {}
    for statement in ast.parse(path.read_text()).body:
        if isinstance(statement, ast.Assign):
            for name in statement.targets:
                if isinstance(name, ast.Name) and name.id in ('BL', 'BP'):
                    result[name.id] = ast.literal_eval(statement.value)
    return result


def main():
    started = time.perf_counter()
    protocol = PROJECT / 'experiments/fair_gist_comparison/configs/protocol.json'
    calibration = PROJECT / 'outputs/wg_qmf_qwindex_20260830/cost_calibration.csv'
    observations = Path('/home/lingyaqi/.cache/qmap-li-posix/wg-qmf-qwindex-20260830/native_cost_calibration_observations.csv')
    node_dirs = sorted(p.parent for p in (STUDY / 'results/nodes').glob('*/costs.npz'))
    assert len(node_dirs) == 43
    sources = [protocol, calibration, observations,
        PROJECT / 'python/qmapli/wg_qmf/calibration.py',
        PROJECT / 'python/qmapli/wg_qmf/runner.py',
        PROJECT / 'python/qmapli/wg_qmf/report.py',
        PROJECT / 'cpp/src/benchmark/subtree_calibration.cpp',
        PROJECT / 'configs/wg_qmf_preconfirm.yaml',
        PROJECT / 'experiments/fair_gist_comparison/scripts/build_index.py',
        PROJECT / 'experiments/fair_gist_comparison/src/builders/recursive_exact.py',
        PHASES / 'phase1_audit_20261019/01_qmf_implementation_audit.md',
        PHASES / 'phase4_complementarity_analysis/src/trajectory_metrics.py',
        BASE / 'QMF/QMF_PostGIS_100M_Repro_20260910/config/qmf_frozen_config.yaml',
        BASE / 'QMF/QMF_PostGIS_100M_Repro_20260910/src/common/python/qmapli/wg_qmf/cost_oracle.py',
        STUDY / 'experiments/node_worker.py',
        STUDY / 'experiments/search_worker.py']
    vendor = PROJECT / 'experiments/fair_gist_comparison/vendor/python/qmapli/wg_qmf'
    sources += [vendor / name for name in ['cost_oracle.py', 'cached_oracle.py', 'search.py']]
    engines = [PHASES / f'{phase}/src/conditional_state.py' for phase in
               ['phase2_hybrid_optimizer', 'phase3_hybrid_comparison', 'phase4_complementarity_analysis']]
    sources += engines
    for folder in node_dirs:
        sources += [folder / name for name in ['costs.npz', 'summary.json', 'configurations.csv']]
    before = {str(p): sha(p) for p in sources}
    (OUT / 'data/source_sha256_before.json').write_text(json.dumps(before, indent=2))
    cfg = json.loads(protocol.read_text())
    alpha, beta = cfg['beta_leaf'], cfg['beta_point']
    assert all(constants(p) == {'BL': alpha, 'BP': beta} for p in engines)
    with calibration.open(newline='') as f:
        cal = next(csv.DictReader(f))
    assert float(cal['beta_leaf']) == alpha and float(cal['beta_point']) == beta
    obs = pd.read_csv(observations, float_precision='round_trip')
    prediction = float(cal['beta0']) + alpha * obs.visited_leaves.to_numpy() + beta * obs.refined_points.to_numpy()
    y = obs.latency_ns.to_numpy()
    r2 = 1 - np.sum((y - prediction) ** 2) / np.sum((y - y.mean()) ** 2)
    mae = np.mean(np.abs(y - prediction))
    assert len(obs) == int(cal['observations'])
    assert np.isclose(r2, float(cal['r2']), rtol=1e-12, atol=1e-12)
    assert np.isclose(mae, float(cal['mae']), rtol=1e-12, atol=1e-12)
    rows, root_rows = [], []
    for folder in node_dirs:
        meta = json.loads((folder / 'summary.json').read_text())
        q = int(meta['Queries'])
        cohort = 'validation3' if folder.name.startswith('repro_') else 'main40'
        with np.load(folder / 'costs.npz', allow_pickle=False) as z:
            costs, leaves, scans = [z[k].copy() for k in ['costs', 'leaf', 'scan']]
        catalog = pd.read_csv(folder / 'configurations.csv', usecols=['Configuration', 'RootAction'])
        assert np.array_equal(catalog.Configuration.to_numpy(), np.arange(len(costs)))
        root = catalog.RootAction.to_numpy()
        rebuilt = alpha * leaves + beta * scans
        assert np.array_equal(costs, rebuilt), folder.name
        hits_i = np.rint(leaves * q).astype(np.int64)
        scans_i = np.rint(scans * q).astype(np.int64)
        count_round_error = max(float(np.max(np.abs(leaves*q-hits_i))), float(np.max(np.abs(scans*q-scans_i))))
        assert count_round_error < 1e-3
        assert np.all(hits_i <= 8*q) and np.all(scans_i >= 256*hits_i)
        weighted_idx, scan_idx = int(np.argmin(costs)), int(np.argmin(scans_i))
        order = np.argsort(costs, kind='stable')
        inversions = int(np.sum(np.diff(scans_i[order]) < 0))
        assert inversions == 0
        pure = beta * scans
        strict_original = costs == costs.min()
        scan_opt = scans_i == scans_i.min()
        legacy_tol = 8 * abs(float(np.spacing(costs.min())))
        tolerant_original = costs <= costs.min() + legacy_tol
        original_roots = set(root[strict_original])
        tolerant_roots = set(root[tolerant_original])
        scan_roots = set(root[scan_opt])
        grouped = pd.DataFrame({'scan': scans_i, 'hits': hits_i, 'cost': costs}).groupby('scan')
        vary_hits = grouped.hits.nunique()
        varying_cost_groups = int((grouped.cost.nunique() > 1).sum())
        pure_order = np.argsort(scans_i, kind='stable')
        max_share = float(np.max(np.divide(alpha*leaves, pure, out=np.zeros_like(pure), where=pure>0)))
        rows.append(dict(node=folder.name, dataset=meta['Dataset'], node_id=meta['NodeID'], cohort=cohort,
            queries=q, configurations=len(costs), alpha=alpha, beta=beta,
            exact_cost_array_match=True, max_integer_recovery_error=count_round_error,
            weighted_argmin_configuration=weighted_idx, scan_only_argmin_configuration=scan_idx,
            same_first_argmin_configuration=weighted_idx == scan_idx,
            weighted_argmin_root=root[weighted_idx], scan_only_argmin_root=root[scan_idx],
            same_first_argmin_root=root[weighted_idx] == root[scan_idx],
            weighted_optimum_achieves_minimum_scans=bool(scan_opt[weighted_idx]),
            strict_optimum_configurations=int(strict_original.sum()), scan_min_configurations=int(scan_opt.sum()),
            strict_optimum_set_unchanged=bool(np.array_equal(strict_original, scan_opt)),
            legacy_tolerant_optimum_set_unchanged=bool(np.array_equal(tolerant_original, scan_opt)),
            strict_root_set_unchanged=original_roots == scan_roots,
            legacy_tolerant_root_set_unchanged=tolerant_roots == scan_roots,
            strict_optimal_roots=json.dumps(sorted(original_roots)), scan_min_roots=json.dumps(sorted(scan_roots)),
            lower_scans_rank_reversals=inversions,
            equal_scan_groups_with_distinct_leaf_counts=int((vary_hits>1).sum()),
            equal_scan_groups_with_distinct_float_costs=varying_cost_groups,
            stable_order_changed=bool(not np.array_equal(order, pure_order)),
            stable_order_changed_positions=int(np.sum(order != pure_order)),
            scan_min_leaf_count_range=int(np.ptp(hits_i[scan_opt])),
            leaf_term_max=float(np.max(alpha*leaves)), leaf_over_scan_max=max_share,
            zero_float_effect_configurations=int(np.sum(costs == pure)),
            max_cost_change_removing_leaf=float(np.max(costs-pure)),
            weighted_optimum_cost=float(costs.min()), scan_only_optimum_cost=float(pure.min()),
            source=str(folder / 'costs.npz')))
        for action in sorted(set(root)):
            mask = root == action
            root_rows.append(dict(node=folder.name, cohort=cohort, root_action=action,
                configurations=int(mask.sum()), original_best_cost=float(costs[mask].min()),
                scan_only_best_cost=float(pure[mask].min()), minimum_total_scan_count=int(scans_i[mask].min()),
                original_strict_root_optimal=action in original_roots,
                original_legacy_tolerant_root_optimal=action in tolerant_roots,
                scan_only_root_optimal=action in scan_roots))
    node_frame = pd.DataFrame(rows)
    node_frame.to_csv(OUT / 'data/node_weight_ablation.csv', index=False)
    pd.DataFrame(root_rows).to_csv(OUT / 'data/root_weight_ablation.csv', index=False)
    aggregate = []
    for cohort in ['main40', 'validation3', 'all43']:
        d = node_frame if cohort == 'all43' else node_frame[node_frame.cohort == cohort]
        entry = dict(cohort=cohort, nodes=len(d), configurations=int(d.configurations.sum()),
            queries_min=int(d.queries.min()), queries_max=int(d.queries.max()),
            max_leaf_over_scan=float(d.leaf_over_scan_max.max()),
            max_leaf_term=float(d.leaf_term_max.max()),
            configurations_where_leaf_rounds_away=int(d.zero_float_effect_configurations.sum()),
            equal_scan_groups_with_distinct_leaf_counts=int(d.equal_scan_groups_with_distinct_leaf_counts.sum()),
            equal_scan_groups_with_distinct_float_costs=int(d.equal_scan_groups_with_distinct_float_costs.sum()),
            stable_order_changed_nodes=int(d.stable_order_changed.sum()),
            stable_order_changed_positions=int(d.stable_order_changed_positions.sum()))
        for col in ['same_first_argmin_configuration', 'same_first_argmin_root',
                    'weighted_optimum_achieves_minimum_scans', 'strict_optimum_set_unchanged',
                    'legacy_tolerant_optimum_set_unchanged', 'strict_root_set_unchanged',
                    'legacy_tolerant_root_set_unchanged']:
            entry[col + '_nodes'] = int(d[col].sum())
        aggregate.append(entry)
    summary = dict(alpha=alpha, beta=beta, fitted_units='latency_ns per raw work count',
        alpha_over_beta=alpha/beta, H3_leaf_bound=8*alpha,
        single_total_scan_gap_Q1000=beta/1000,
        scan_gap_over_leaf_bound_Q1000=(beta/1000)/(8*alpha),
        leaf_over_scan_bound_min256=alpha/(256*beta),
        calibration=dict(observations=len(obs), beta0=float(cal['beta0']), r2=float(r2), mae_ns=float(mae),
                         source=str(calibration), observation_source=str(observations)),
        cohorts=aggregate, elapsed_seconds=time.perf_counter()-started,
        operation='Offline arithmetic and ranking of frozen cost tables; no search/build/query/model fitting executed',
        python=sys.version, numpy=np.__version__, pandas=pd.__version__)
    after = {str(p): sha(p) for p in sources}
    changed = [str(p) for p in sources if before[str(p)] != after[str(p)]]
    assert not changed, changed
    summary['source_integrity'] = dict(protected_files=len(sources), changed=changed)
    summary['script_sha256'] = sha(Path(__file__))
    (OUT / 'data/audit_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (OUT / 'data/source_sha256_after.json').write_text(json.dumps(after, indent=2))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
