"""Freeze Phase 2 equivalence and memory evidence; never launch a benchmark."""
import importlib.util,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/paper_eval'))
import support as s
import run
import flood_resume as f
from paper_protocol import MEMORY_HIGH,MEMORY_MAX,MEMORY_SWAP_MAX,HOST_EMERGENCY_RESERVE

def main():
    out=f.AUDIT;analysis=json.loads((out/'compact_scaling.json').read_text())
    tests=out/'TESTS_PRE_ACCEPTANCE_FINAL.xml'
    assert run.passing_test_xml(tests)
    if (out/'acceptance.json').exists():raise RuntimeError('Refuse overwrite Phase 2 receipt')
    spec=importlib.util.spec_from_file_location('protected',out/'protect.py')
    protect=importlib.util.module_from_spec(spec);spec.loader.exec_module(protect)
    assert protect.scan()==json.loads((out/'before.json').read_text())
    prior_path=Path('/var/tmp/qmf-flood-correctness-memfix-20260915/acceptance.json')
    prior=json.loads(prior_path.read_text());current=run.source_manifest();restored=dict(current)
    adapter='src/qmap/cpp/src/baselines/learnedbench_adapters.cpp'
    restored[adapter]=s.sha(out/'phase1_adapters.cpp')
    for name in ['flood_ownership.hpp','flood_compact_lookup.hpp']:
        restored.pop('src/qmap/cpp/src/baselines/'+name)
    assert restored==prior['current_production_source_manifest'],'Unrelated source modification'
    frozen_model=json.loads((out/'FROZEN_LEARNEDBENCH_SHA.json').read_text())
    assert all(s.sha(p)==h for p,h in frozen_model.items())
    original=s.read_json(s.OUT/'00_environment/production_source_before.json')
    expected={line.partition('  ')[2]:line.partition('  ')[0] for line in (s.BASE/'MANIFEST.sha256').read_text().splitlines()}
    actual={str(p.relative_to(s.BASE)):s.sha(p) for p in s.BASE.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256'}
    delta={p:{'before':expected.get(p),'after':actual.get(p)} for p in sorted(set(expected)|set(actual)) if expected.get(p)!=actual.get(p)}
    sources=[s.BASE/p for p in current]+list((ROOT/'scripts/paper_eval').glob('*.py'))+list((ROOT/'scripts/paper_eval').glob('*.cpp'))+list((ROOT/'scripts/paper_eval').glob('*.hpp'))
    runtime=[out/'qmf_postgres_full',out/'session_setup.sql',out/'extension/qmap_benchmark.so',out/'native/lib/libqmap_runtime.so']
    evidence=[tests,out/'compact_scaling.json',out/'before.json',out/'FROZEN_LEARNEDBENCH_SHA.json',prior_path,
        out/'COORDINATE_ROUNDTRIP_ALL_PREFIXES.json']
    for n in (1000000,5000000,10000000,25000000,50000000):
        for version in ('compact','phase1'):
            folder=out/version/str(n)
            evidence += [folder/name for name in ['completed.json','correctness.csv','matches.csv','trace.csv']]
    for n in (1,5):evidence += [out/f'postgres_{n}M'/name for name in ['complete.json','correctness.csv','summary.json']]
    value={'scope':'Flood preload ownership and exact adapter ID lookup; no model changes',
        'safe_for_full_retry':analysis['safe_for_full_retry'],'equivalence_pass':analysis['equivalence_pass'],
        'predicted_181m_peak_mib':analysis['predicted_181m_peak_mib'],
        'memory_policy':[MEMORY_HIGH,MEMORY_MAX,MEMORY_SWAP_MAX,HOST_EMERGENCY_RESERVE],
        'tests_path':str(tests),'source_files':{str(p):s.sha(p) for p in sources},
        'runtime_files':{str(p):s.sha(p) for p in runtime},
        'evidence_files':{**{str(p):s.sha(p) for p in evidence},**frozen_model},
        'original_production_manifest':original,'current_production_source_manifest':current,
        'changed_production_files':delta,'archive_verification_path':str(out/'archive_verification.json'),
        'qmf_core_algorithm_changed':False,'flood_algorithm_changed':False,'flood_model_changed':False,
        'dataset_changed':False,'query_protocol_changed':False,'memory_policy_changed':False,
        'original_results_preserved':True,'full_scale_measured':False}
    (out/'acceptance.json').write_text(json.dumps(value,indent=2)+'\n')
    f.verify_gate(require_safe=False)
    print('SAFE_FOR_FLOOD_CORRECTNESS_RETRY =',value['safe_for_full_retry'])
if __name__=='__main__':main()
