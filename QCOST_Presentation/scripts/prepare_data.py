#!/usr/bin/env python3
"""Freeze read-only, auditable inputs for the editable research presentation."""
from pathlib import Path
import hashlib
import json
import shutil
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent.parent
RESULTS = BASE / 'QMap-LI/paper_icde_qcost_results'
XL = RESULTS / '07_reporting_tables/QCOST_COMPARISON_TABLES.xlsx'
MOT = BASE / 'QMF-Motivation-Figures'
MANIFEST = []
CHECKS = []


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def record(path, role):
    path = Path(path)
    MANIFEST.append({'Path': str(path), 'SHA256': sha(path), 'Bytes': path.stat().st_size,
                     'Mtime_ns': path.stat().st_mtime_ns, 'Role': role})


def test(name, condition, detail=''):
    CHECKS.append({'Check': name, 'Passed': bool(condition), 'Detail': str(detail)})
    if not condition:
        raise AssertionError((name, detail))


record(XL, 'Primary numeric authority; all 24 result worksheets')
book = pd.ExcelFile(XL)
tables = {}
for sheet in book.sheet_names:
    if sheet == 'README':
        continue
    d = pd.read_excel(book, sheet_name=sheet, header=3)
    tables[sheet] = d
    d.to_csv(ROOT / 'data' / (sheet + '.csv'), index=False)
    original = RESULTS / '07_reporting_tables/csv' / (sheet + '.csv')
    record(original, 'CSV counterpart of Excel sheet')
    source = pd.read_csv(original)
    pd.testing.assert_frame_equal(d, source, check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-10)
    test('Excel/CSV一致 ' + sheet, True, len(d))
shutil.copy2(XL, ROOT / 'data/QCOST_COMPARISON_TABLES.xlsx')
for name in ['QCOST_COMPARISON_TABLES_ZH.docx','QCOST_COMPARISON_TABLES_ZH.pdf']:
    record(RESULTS / '07_reporting_tables' / name, 'Supporting table layout and protocol')
record(RESULTS / '00_audit/FINAL_AUDIT_REPORT_ZH.md', 'Scope and interpretation')
record(ROOT.parent / 'uplan_icde25_slides.pdf', '17-page visual reference only')

motivation = {}
for name in ['FIG2_CASE_CANDIDATES','FIG2_PARTITION_LINES','FIG2_SPATIAL_POINTS','FIG2_QUERIES',
             'FIG2_BOUNDS','FIG2_GEOMETRY_VALIDATION','FIG2_COMPARABLE_NODES','FIG2_ALL40_FEASIBILITY',
             'FIG3_PAIRED_NODE_TIMES']:
    path = MOT / 'derived_data' / (name + '.csv')
    record(path, 'Existing real motivation observations')
    motivation[name] = pd.read_csv(path)
    motivation[name].to_csv(ROOT / 'data' / (name + '.csv'), index=False)
    if 'SourceCSV' in motivation[name]:
        for s in motivation[name].SourceCSV.dropna().unique():
            if not any(x['Path'] == s for x in MANIFEST):
                record(s, 'Original CSV referenced by motivation observations')

reference = ROOT / 'assets/reference'
reference.mkdir(exist_ok=True)
figs = [
    MOT / 'revisions/layout_v6_horizontal_20261011/figures/pdf/FIG2_LOCAL_VS_JOINT.pdf',
    MOT / 'revisions/layout_v7_fig3_inset_fix_20261012/figures/pdf/FIG3_CONDITIONAL_COMPLEXITY.pdf',
    MOT / 'revisions/layout_v6_horizontal_20261011/figures/pdf/FIG4_BUDGETED_ROOT_QUALITY.pdf',
    BASE / 'Q-COST-Figures/Fig5/export/paper/FIG5_QCOST_PAPER.pdf',
    BASE / 'Q-COST-Figures/Fig6/export/paper/FIG6_PAPER.pdf']
figs += list(sorted((RESULTS / '03_pdf').glob('fig*.pdf')))
for p in figs:
    if p.exists():
        record(p, 'Existing paper figure; full uncropped copy')
        shutil.copy2(p, reference / p.name)

query = tables['T03_system_query']
speedup = []
for ds in ['GeoLife','Gowalla','NYC Taxi','Skewed 2D']:
    g = query[query['数据集'] == ds].set_index('方法')
    speedup.append({'Dataset': ds, 'Q-COST_ms': g.loc['Q-COST','Mean(ms)'],
        'BMTree_ms': g.loc['BMTree','Mean(ms)'],
        'Speedup': g.loc['BMTree','Mean(ms)'] / g.loc['Q-COST','Mean(ms)']})
pd.DataFrame(speedup).to_csv(ROOT / 'data/speedups.csv', index=False)
test('四个加速比一位小数', [round(x['Speedup'],1) for x in speedup] == [34.1,37.6,220.8,10.3])
official = tables['T13_official_budget'].set_index('方法')
q = official.loc['CPU Analytic QMF']; r = official.loc['Random Search']
case = motivation['FIG2_CASE_CANDIDATES']
local = case[case.Rank == 0].iloc[0]; joint = case.loc[case.CostH3.idxmin()]
scalars = {
    'speedup_min': min(x['Speedup'] for x in speedup), 'speedup_max': max(x['Speedup'] for x in speedup),
    'configuration_gain_pp': q['配置最优率(%)'] - r['配置最优率(%)'],
    'root_gain_pp': q['根最优率(%)'] - r['根最优率(%)'],
    'root_regret_reduction_pct': (1-q['Root Regret']/r['Root Regret'])*100,
    'qmf_config_hit_pct': q['配置最优率(%)'], 'qmf_root_hit_pct': q['根最优率(%)'],
    'local_case_cost': float(local.CostH3), 'joint_case_cost': float(joint.CostH3),
    'local_case_configuration': int(local.Configuration), 'joint_case_configuration': int(joint.Configuration),
    'case_cost_reduction_pct': 100*(1-joint.CostH3/local.CostH3),
    'gate_max_abs_error_pp': float(tables['T16_gate_validation'].AbsError_pp.max()),
    'HK34_cost_reduction_pct': float(tables['T17_sensitivity'].query('H==3 and K==4').Improvement_pct.iloc[0]),
    'presentation_date': '2026年10月16日', 'author': '[待填写]', 'affiliation': '[待填写]'}
test('最优概率', round(scalars['qmf_config_hit_pct'],2)==65.42 and round(scalars['qmf_root_hit_pct'],2)==95.08)
test('实际GeoLife案例', round(local.CostH3,2)==1813.09 and round(joint.CostH3,2)==1503.44)
test('14条H3划分线合法', motivation['FIG2_GEOMETRY_VALIDATION'].GeometryMatched.all())
f=motivation['FIG2_ALL40_FEASIBILITY']
test('可行性三类', len(f)==40 and f.H3Feasible.sum()==21 and (f.H3Feasible & f.OptimalRoot.eq(False)).sum()==7)
test('43最优成本配对', len(motivation['FIG3_PAIRED_NODE_TIMES'])==43 and motivation['FIG3_PAIRED_NODE_TIMES'].OptimalCostMatched.all())
(ROOT / 'data/verified_highlights.json').write_text(json.dumps(scalars,ensure_ascii=False,indent=2))

# Protect the sources used by the preceding results audit as well.
prior = pd.read_csv(RESULTS / '00_audit/source_sha256.csv')
protected=[]
for row in prior.to_dict('records'):
    actual = sha(row['path'])
    protected.append({'Path':row['path'],'Expected':row['sha256'],'Actual':actual,'Unchanged':actual==row['sha256']})
test('此前177项来源SHA', all(r['Unchanged'] for r in protected),len(protected))
pd.DataFrame(protected).to_csv(ROOT/'validation/prior_integrity.csv',index=False)
pd.DataFrame(MANIFEST).drop_duplicates('Path').to_csv(ROOT/'validation/input_manifest.csv',index=False)
pd.DataFrame(CHECKS).to_csv(ROOT/'validation/data_checks.csv',index=False)
print(json.dumps({'tables':len(tables),'checked_sources':len(protected),'inputs':len(MANIFEST),'highlights':scalars},ensure_ascii=False,indent=2))
