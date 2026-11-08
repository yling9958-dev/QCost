"""Freeze reviewable evidence; never start a benchmark or modify formal results."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/paper_eval'))
import support as s
import run
import flood_resume as f
from paper_protocol import MEMORY_HIGH,MEMORY_MAX,MEMORY_SWAP_MAX,HOST_EMERGENCY_RESERVE

def main():
    a=f.AUDIT
    if (a/'acceptance.json').exists():raise RuntimeError('Refuse overwrite accepted evidence')
    analysis=json.loads((a/'profile_analysis.json').read_text())
    pg=json.loads((a/'postgres_1M/complete.json').read_text())
    assert pg['status']=='PASS' and pg['queries']==1000
    tests=a/'tests_pre_acceptance_final.xml'
    assert run.passing_test_xml(tests)
    spec=importlib.util.spec_from_file_location('flood_protect',a/'protect.py')
    protect=importlib.util.module_from_spec(spec);spec.loader.exec_module(protect)
    assert protect.scan()==json.loads((a/'before.json').read_text())
    current=run.source_manifest()
    prior=json.loads((ROOT/'results/qmf_build_audit_cleanup_20260914/QMF_MEMORY_IMPLEMENTATION_SOURCE_20260914.json').read_text())
    restored=dict(current)
    adapter='src/qmap/cpp/src/baselines/learnedbench_adapters.cpp'
    restored[adapter]=s.sha(a/'learnedbench_adapters_before.cpp')
    assert restored==prior['current_production_source_manifest'],'Unrelated production change'
    original=json.loads((s.OUT/'00_environment/production_source_before.json').read_text())
    expected={}
    for line in (s.BASE/'MANIFEST.sha256').read_text().splitlines():
        sha,_,path=line.partition('  ');expected[path]=sha
    actual={str(p.relative_to(s.BASE)):s.sha(p) for p in s.BASE.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256'}
    changed={p:{'before':expected.get(p),'after':actual.get(p)} for p in sorted(set(expected)|set(actual)) if expected.get(p)!=actual.get(p)}
    runtime=[a/'qmf_postgres_full',a/'extension/qmap_benchmark.so',a/'native/lib/libqmap_runtime.so',a/'session_setup.sql']
    evidence=[tests,a/'before.json',a/'ORIGINAL_RESULTS_SHA256_20260915.txt',a/'profile_analysis.json',
              a/'postgres_1M/complete.json',a/'postgres_1M/summary.json',a/'postgres_1M/correctness.csv']
    evidence += list((a/'profiles').glob('*/*/completed.json'))+list((a/'profiles').glob('*/*/correctness.csv'))
    sources=list((ROOT/'scripts/paper_eval').glob('*.py'))+list((ROOT/'scripts/paper_eval').glob('*.cpp'))+list((ROOT/'scripts/paper_eval').glob('*.hpp'))
    sources += [s.BASE/p for p in current]
    value={'scope':'Flood query-output memory and immutable-build correctness resume only',
        'safe_for_full_retry':analysis['memory_gate_pass'],'predicted_181m_peak_mib':analysis['predicted_181m_peak_mib'],
        'equivalence_pass':analysis['equivalence_pass'],'original_results_preserved':True,
        'memory_policy':[MEMORY_HIGH,MEMORY_MAX,MEMORY_SWAP_MAX,HOST_EMERGENCY_RESERVE],
        'tests_path':str(tests),'source_files':{str(p):s.sha(p) for p in sources},
        'runtime_files':{str(p):s.sha(p) for p in runtime},'evidence_files':{str(p):s.sha(p) for p in evidence},
        'original_production_manifest':original,'current_production_source_manifest':current,
        'changed_production_files':changed,'archive_verification_path':str(a/'archive_verification.json'),
        'qmf_core_algorithm_changed':False,'flood_algorithm_changed':False,
        'dataset_changed':False,'query_protocol_changed':False,'memory_policy_changed':False}
    (a/'acceptance.json').write_text(json.dumps(value,indent=2)+'\n')
    f.verify_gate(require_safe=False)
    print('SAFE_FOR_FLOOD_CORRECTNESS_RETRY = '+str(value['safe_for_full_retry']))
if __name__=='__main__':main()
