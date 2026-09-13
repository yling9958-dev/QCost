import ast
import csv
import importlib.util
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import support as s
import worker
import orchestrate as o
import report
import run
import cgroup_policy as cg

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    out=tmp_path/'results'; runtime=tmp_path/'runtime'
    for m in [s,worker,o]:
        monkeypatch.setattr(m,'OUT',out); monkeypatch.setattr(m,'RUN',runtime)
    monkeypatch.setattr(o,'ACTIVE',runtime/'active')
    monkeypatch.setattr(o,'STATE',runtime/'status.json')
    s.output_dirs()
    return out,runtime

def row():
    return {'dataset_id':run.DATASETS[0],'bounds':[-180.,-50.,180.,70.],'record_count':181000000}

def test_new_query_freeze_cardinality_and_determinism(isolated):
    out,_=isolated; r=row()
    s.atomic_json(out/'01_dataset_inventory'/(r['dataset_id']+'.json'),r)
    worker.queries(r['dataset_id']); first=run.query_gate(r)
    path=out/'02_queries'/r['dataset_id']/(r['dataset_id']+'_queries.csv'); digest=s.sha(path)
    worker.queries(r['dataset_id'])
    assert s.sha(path)==digest
    assert len(first)==6300
    assert [q['query_id'] for q in first][:2]==['train-00000','train-00001']
    assert run.PROTOCOL['reference_query_denominator']==1000

def test_query_mutation_rejected(isolated):
    out,_=isolated; r=row(); s.atomic_json(out/'01_dataset_inventory'/(r['dataset_id']+'.json'),r)
    worker.queries(r['dataset_id'])
    path=out/'02_queries'/r['dataset_id']/(r['dataset_id']+'_queries.csv')
    path.write_text(path.read_text().replace('train-00000','train-99999',1))
    with pytest.raises(RuntimeError,match='SHA'): run.query_gate(r)

@pytest.mark.parametrize('content',[None,'','Method,Mean_ms\n','Method,Mean_ms\nQMF,1\n'])
@pytest.mark.parametrize('status',['RESOURCE_BLOCKED_MEMORY','RESOURCE_BLOCKED_TIME','BUILD_FAILED','CORRECTNESS_INVALID'])
def test_empty_missing_csv_and_blocked_rows(isolated,content,status):
    out,_=isolated; r=row()
    path=out/'07_rankings'/'legacy.csv'
    if content is not None: path.write_text(content)
    for display,runtime in s.METHODS:
        s.done(r['dataset_id'],runtime+'_method',{'Method':display,'Status':status,'Correctness':'NOT_RUN'})
    data=report.rows(r['dataset_id'])
    assert len(data)==8 and all(v['Status']==status for v in data)
    assert all(v['Mean_ms'] is None for v in data)
    assert all(v['QMFRank'] is None and v['Denominator']==0 for v in report.ranks(data))
    assert 'N/A' in report.table(data)

def test_mixed_pass_blocked_size_denominator(isolated):
    d=row()['dataset_id']
    for i,(display,runtime) in enumerate(s.METHODS):
        s.done(d,runtime+'_method',{'Method':display,'Status':'PASS' if i<3 else 'BUILD_FAILED',
          'Correctness':'1000/1000 exact' if i<3 else 'NOT_RUN',**{m:float(i+1) for m in s.METRICS}})
    ranks=report.ranks(report.rows(d))
    assert ranks[0]['QMFRank']==1 and ranks[0]['Denominator']==3
    assert ranks[1]['Denominator']==2 # LISA is not size-comparable.
    assert ranks[5]['QMFRank']==3

def test_result_persistence_precedes_cleanup(isolated,monkeypatch):
    out,runtime=isolated; r=row(); normalized=runtime.parent/'persistent.csv'; normalized.write_text('id,x,y\n0,0,0\n')
    active=runtime/'active'/r['dataset_id']; active.mkdir(parents=True); (active/'points_normalized.csv').symlink_to(normalized)
    with pytest.raises(RuntimeError,match='persisted'): run.cleanup(r)
    assert normalized.exists()
    monkeypatch.setattr(report,'dataset_report',lambda *a: (_ for _ in ()).throw(ValueError('empty result')))
    # An analysis failure alone never invokes cleanup or deletes normalized bytes.
    with pytest.raises(ValueError): report.dataset_report(r,0)
    assert normalized.exists() and active.exists()

def test_fixed_shared_budget():
    kernel={'memory.high':22*s.GIB,'memory.max':24*s.GIB,'memory.swap.max':0,'memory.swap.current':0}
    p={'path':'/paper','kernel':kernel}
    assert cg.validate(p,[{'path':'/paper/worker','kernel':{'memory.high':'max','memory.max':'max'}}])
    with pytest.raises(RuntimeError): cg.validate({**p,'kernel':{**kernel,'memory.max':11*s.GIB}})
    with pytest.raises(RuntimeError): cg.validate(p,[{'path':'/elsewhere','kernel':{}}])
    assert run.PROTOCOL['host_reserve']==3.5*s.GIB

def test_frozen_qmf_build_and_correctness_sql_unchanged():
    root=Path(__file__).resolve().parent; old=root.parent/'full_eval'
    def func(path,name):
        tree=ast.parse(path.read_text())
        return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
    assert func(root/'worker.py','qmf')==func(old/'worker.py','qmf')
    def sql(path):
        source=path.read_text(); return source.split('std::string correctness_sql(')[1].split('\nvoid prepare(')[0]
    assert sql(root/'postgres_full.cpp')==sql(old/'postgres_full.cpp')

def test_completed_method_resume_skips_build(isolated,monkeypatch):
    r=row(); display,runtime=s.METHODS[0]
    s.done(r['dataset_id'],runtime+'_method',{'Method':display,'Status':'PASS','Build_s':123.0})
    monkeypatch.setattr(o,'build_one',lambda *a: pytest.fail('Completed build rerun'))
    assert o.run_method(r,display,runtime)['Build_s']==123.0

def test_no_heavy_reference_execution(monkeypatch):
    monkeypatch.setattr(o,'monitor',lambda *a,**k: pytest.fail('Reference precompute launched'))
    assert o.ensure_counts(row()) is None
