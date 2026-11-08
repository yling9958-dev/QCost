"""No production execution: bounded baseline scheduling and evidence ownership."""
import json
from pathlib import Path
import pytest
import baseline_campaign as b
import support as s
import orchestrate as o
from test_retry import retry_env,bytes_under


@pytest.fixture
def env(retry_env,monkeypatch):
    monkeypatch.setattr(b,'FORMAL',s.OUT)
    monkeypatch.setattr(b,'ROOT',s.OUT/'baseline_campaign')
    monkeypatch.setattr(b,'AUDIT',retry_env/'audit')
    monkeypatch.setattr(b,'RUNTIME',retry_env/'runtime_baseline')
    monkeypatch.setattr(b,'ORIGINAL_RUNTIME',s.RUN)
    b.AUDIT.mkdir()
    rows=[]
    for d in b.DATASETS:
        source=retry_env/(d+'.csv');source.write_bytes(b'x,y\n0,0\n')
        s.atomic_json(s.OUT/'01_dataset_inventory'/(d+'.json'),{'dataset_id':d,'source_path':str(source),'sha256':s.sha(source)})
        path=s.OUT/'02_queries'/d/'query.csv';path.parent.mkdir(parents=True);path.write_bytes(b'frozen query')
        s.done(d,'queries',files=[path])
        for _,m in s.METHODS:
            rows.append({'dataset':d,'method':m,'root':str(s.OUT),'valid':m=='qmap_uniform_qmf',
                'result':{'Status':'PASS' if m=='qmap_uniform_qmf' else 'NOT_RUN','Correctness':'1000/1000 exact',
                          **{k:1.0 for k in s.METRICS}}})
    s.atomic_json(b.AUDIT/'initial_results.json',rows)
    return retry_env


def test_baseline_order_and_qmf_permanent_skip(env):
    tasks=b.queue()
    assert len(tasks)==28
    assert tasks[:4]==[(d,'postgis_gist') for d in b.DATASETS]
    assert all(m!='qmap_uniform_qmf' for d,m in tasks)
    with pytest.raises(RuntimeError,match='QMF execution forbidden'):b.new_attempt(b.DATASETS[0],'qmap_uniform_qmf')


def test_baseline_pass_never_reexecuted(env):
    values=b.initial_results();values[1]['valid']=True
    s.atomic_json(b.AUDIT/'initial_results.json',values)
    with pytest.raises(RuntimeError,match='PASS reexecution'):b.new_attempt(b.DATASETS[0],'postgis_gist')
    assert (b.DATASETS[0],'postgis_gist') not in b.queue()


def test_baseline_max_normal_plus_one_repair(env):
    d=b.DATASETS[1];m='lisa'
    for _ in range(2):b.new_attempt(d,m)
    with pytest.raises(RuntimeError,match='budget'):b.new_attempt(d,m)
    assert b.disposition('HOST_SAFETY_STOP',1)=='RETRY'
    assert b.disposition('HOST_SAFETY_STOP',2)=='SKIPPED_AFTER_REPEATED_FAILURE'


def test_historical_failure_leaves_exactly_one_repair(env):
    values=b.initial_results()
    for r in values:
        if r['method']=='rtree' and r['dataset']==b.DATASETS[0]:r['result']['Status']='HOST_SAFETY_STOP'
    s.atomic_json(b.AUDIT/'initial_results.json',values)
    assert b.attempt_budget(b.DATASETS[0],'rtree')==1
    b.new_attempt(b.DATASETS[0],'rtree')
    with pytest.raises(RuntimeError,match='budget'):b.new_attempt(b.DATASETS[0],'rtree')


@pytest.mark.parametrize('status',sorted(b.HARD_FAILURES))
def test_baseline_hard_failures_do_not_retry(status):
    assert b.disposition(status,1)=='FAILED_FINAL'


def test_flood_existing_build_preserved_and_reused(env,monkeypatch):
    d=b.DATASETS[0];index=env/'flood.idx';index.write_bytes(b'protected index')
    s.done(d,'flood_build_r0',{'build_seconds':112.318935022,'index_path':str(index)},[index])
    before=bytes_under(s.OUT)
    import flood_resume
    monkeypatch.setattr(flood_resume,'ATTEMPTS',env/'no_historical_attempts')
    target=b.new_attempt(d,'flood')
    assert (target/'checkpoints'/d/'flood_build_r0.done').read_bytes()==s.marker(d,'flood_build_r0').read_bytes()
    assert all((b.FORMAL/k).read_bytes()==v for k,v in before.items())
    with b.execution_context(d,'flood',target):
        with pytest.raises(RuntimeError,match='reexecution forbidden'):o.build_one({},'flood',0)
        with pytest.raises(RuntimeError,match='no QMF'):o.worker('qmf',d,0)


def test_missing_successful_build_never_silently_rebuilds(env):
    d=b.DATASETS[1];index=env/'lisa.idx';index.write_bytes(b'index')
    s.done(d,'lisa_build_r0',{},[index]);index.unlink()
    with pytest.raises(RuntimeError,match='refuse rebuild'):b.new_attempt(d,'lisa')
    assert len(b.attempts(d,'lisa'))==1


def test_recovery_copies_only_selected_method_evidence(env):
    d=b.DATASETS[1];source=s.OUT/'04_correctness'/d
    source.mkdir(parents=True)
    (source/'lisa.csv').write_bytes(b'lisa')
    (source/'qmap_uniform_qmf.csv').write_bytes(b'QMF preserved')
    (source/'tsunami.csv').write_bytes(b'tsunami preserved')
    target=b.new_attempt(d,'lisa')
    assert (target/'04_correctness'/d/'lisa.csv').exists()
    assert not (target/'04_correctness'/d/'qmap_uniform_qmf.csv').exists()
    assert not (target/'04_correctness'/d/'tsunami.csv').exists()


def test_terminal_pair_not_reopened_and_next_scheduled(env):
    d=b.DATASETS[1];b.mark_terminal(d,'postgis_gist','FAILED_FINAL','OOM_KILLED')
    assert (d,'postgis_gist') not in b.queue()
    assert (b.DATASETS[2],'postgis_gist') in b.queue()
    with pytest.raises(FileExistsError):b.mark_terminal(d,'postgis_gist','PASS','forbidden')


def test_reporting_error_never_starts_or_aborts_measurements(env,monkeypatch):
    monkeypatch.setattr(b,'render',lambda *_:(_ for _ in ()).throw(ValueError('fixture report')))
    assert b.refresh_safely() is None
    assert 'REPORTING_FAILED' in (b.ROOT/'reporting_errors.log').read_text()


def test_failed_metrics_na_and_qmf_readonly(env,monkeypatch):
    qmf=b.FORMAL/'QMF_INDEX_4_DATASETS_7_METRICS.csv';qmf.write_bytes(b'opaque original\r\n')
    monkeypatch.setattr(b,'current_state',lambda:{'status':'IDLE'})
    b.mark_terminal(b.DATASETS[0],'rtree','SKIPPED_AFTER_REPEATED_FAILURE','HOST_SAFETY_STOP')
    rows=b.render()
    r=next(r for r in rows if r['Method']=='Boost R*-tree' and r['Dataset']=='GeoLife')
    assert all(r[k] is None for k in s.METRICS)
    assert r['Status']=='SKIPPED_AFTER_REPEATED_FAILURE'
    assert qmf.read_bytes()==b'opaque original\r\n'


def test_baseline_runtime_index_parking_preserves_sha_and_receipt_path(env):
    target=b.new_attempt(b.DATASETS[1],'lisa')
    p=b.RUNTIME/'attempts'/target.name/'active'/b.DATASETS[1]/'methods/lisa/rep0/lisa.idx'
    p.parent.mkdir(parents=True);p.write_bytes(b'index byte exact')
    digest=s.sha(p)
    b.park_new_runtime_indexes(target)
    assert p.is_symlink() and s.sha(p)==digest
    assert (target/'persistent_indexes/lisa.idx').read_bytes()==b'index byte exact'


def test_baseline_nonselected_method_cannot_build(env):
    target=b.new_attempt(b.DATASETS[1],'lisa')
    with b.execution_context(b.DATASETS[1],'lisa',target):
        with pytest.raises(RuntimeError,match='Unexpected method'):o.build_one({},'bmtree',0)


def test_failed_dataset_load_invalidates_previous_sql_identity(env,monkeypatch):
    d=b.DATASETS[1];target=b.new_attempt(d,'lisa')
    cached=env/'cache_root/data_cache/full'/d;cached.mkdir(parents=True)
    point=cached/'points_normalized.csv';point.write_bytes(b'id,x,y\n0,0,0\n')
    s.atomic_json(cached/'normalized_manifest.json',{'points':1,'bytes':point.stat().st_size,'sha256':s.sha(point)})
    monkeypatch.setattr(s,'ROOT',env/'cache_root')
    monkeypatch.setattr(b.run,'query_gate',lambda _:None)
    monkeypatch.setattr(b.q,'setup_query_infrastructure',lambda:None)
    monkeypatch.setattr(o,'sql',lambda *_:None)
    def partial(_):raise RuntimeError('fixture partial SQL load')
    monkeypatch.setattr(o,'prepare_dataset',partial)
    b.RUNTIME.mkdir()
    s.atomic_json(b.RUNTIME/'prepared.json',{'ready':True,'dataset':b.DATASETS[0],'raw_sha256':'old','result_root':'old'})
    with b.execution_context(d,'lisa',target):
        with pytest.raises(RuntimeError,match='partial'):b.prepare({'dataset_id':d,'record_count':1,'sha256':'new'})
    assert s.read_json(b.RUNTIME/'prepared.json')['ready'] is False


def test_baseline_preservation_covers_all_four_qmf_results(env):
    values=b.initial_results()
    files=[]
    for r in values:
        if r['method']=='qmap_uniform_qmf':
            p=b.FORMAL/'qmf'/r['dataset'];p.parent.mkdir(exist_ok=True);p.write_bytes(b'QMF PASS opaque')
            files.append(p)
    s.atomic_json(b.AUDIT/'original_formal.json',{str(p):{'bytes':p.stat().st_size,'sha256':s.sha(p)} for p in files})
    s.atomic_json(b.AUDIT/'flood_build.json',{})
    b.preserve_originals()
    files[-1].write_bytes(b'changed')
    with pytest.raises(RuntimeError,match='ORIGINAL_RESULTS_SHA_CHANGED'):b.preserve_originals()
