"""QMF-only dispatch and immutable-generation tests; no full workers started."""
import json
from pathlib import Path
import pytest
import qmf_only as q
import run
import support as s
import orchestrate as o
from test_retry import retry_env,bytes_under,write_valid_method

@pytest.fixture
def env(retry_env,monkeypatch):
    monkeypatch.setattr(q,'FORMAL',s.OUT)
    monkeypatch.setattr(q,'ROOT',s.OUT/'qmf_only')
    monkeypatch.setattr(q,'RUNTIME',retry_env/'qonly')
    monkeypatch.setattr(q,'ORIGINAL_RUNTIME',s.RUN)
    monkeypatch.setattr(q,'AUDIT',retry_env/'audit')
    for d in q.DATASETS:
        path=s.OUT/'02_queries'/d/'queries.csv';path.parent.mkdir(parents=True);path.write_bytes(b'frozen queries')
        s.atomic_json(s.OUT/'01_dataset_inventory'/(d+'.json'),{'dataset_id':d})
        s.done(d,'queries',files=[path])
    monkeypatch.setattr(q,'valid_root',lambda d:q.FORMAL if d==q.DATASETS[0] else None)
    return retry_env

def test_qmf_only_plan_skips_geolife_and_never_schedules_baselines(env):
    p=q.plan()
    assert [r['dataset'] for r in p]==list(q.DATASETS)
    assert p[0]['action']=='SKIP_VALID'
    assert {r['method'] for r in p}=={'qmap_uniform_qmf'}

def test_qmf_only_geolife_new_attempt_forbidden(env):
    with pytest.raises(RuntimeError,match='GeoLife'):q.new_attempt(q.DATASETS[0])

def test_qmf_only_pass_dataset_never_reexecuted(env,monkeypatch):
    monkeypatch.setattr(q,'valid_root',lambda _:q.FORMAL)
    with pytest.raises(RuntimeError,match='PASS'):q.new_attempt(q.DATASETS[1])

def test_qmf_only_original_failed_receipt_not_reused_or_overwritten(env):
    d=q.DATASETS[1];s.done(d,q.METHOD+'_method',{'Status':'HOST_SAFETY_STOP'})
    before=bytes_under(q.FORMAL)
    target=q.new_attempt(d)
    assert not (target/'checkpoints'/d/(q.METHOD+'_method.done')).exists()
    assert all((q.FORMAL/k).read_bytes()==v for k,v in before.items())
    assert json.loads((target/'provenance.json').read_text())['prior_failure']['payload']['Status']=='HOST_SAFETY_STOP'

def test_qmf_only_reuses_valid_build_checkpoint(env):
    d=q.DATASETS[1];index=env/'index';index.write_bytes(b'index')
    s.done(d,q.METHOD+'_build_r0',{'build_seconds':42,'index_path':str(index)},[index])
    original=s.marker(d,q.METHOD+'_build_r0').read_bytes()
    target=q.new_attempt(d)
    assert (target/'checkpoints'/d/(q.METHOD+'_build_r0.done')).read_bytes()==original

def test_qmf_only_invalid_build_checkpoint_stops_instead_of_rebuilding(env):
    d=q.DATASETS[1];index=env/'index';index.write_bytes(b'index')
    s.done(d,q.METHOD+'_build_r0',{},[index]);index.unlink()
    with pytest.raises(RuntimeError,match='no automatic expensive phase rerun'):q.new_attempt(d)

def test_qmf_only_context_redirects_worker_and_restores_globals(env):
    target=q.new_attempt(q.DATASETS[1]);original=s.OUT
    with q.execution_context(q.DATASETS[1],target):
        assert s.OUT==target and o.OUT==target
        command=o.worker('qmf',q.DATASETS[1],0)
        assert '--target' in command and str(target) in command
        assert '--worker' in command
        with pytest.raises(RuntimeError,match='Unexpected'):o.worker('queries',q.DATASETS[1])
        assert len(str(Path('/var/tmp/qmf-qonly')/q.DATASETS[1]/'common/pg_socket/.s.PGSQL.55445'))<108
    assert s.OUT==original

def test_qmf_only_public_dispatch_uses_official_token(monkeypatch):
    calls=[];monkeypatch.setattr(q,'start',lambda:calls.append('QMF-only'))
    run.qmf_only_dispatch('start','QMF')
    assert calls==['QMF-only']
    with pytest.raises(ValueError):run.qmf_only_dispatch('start','Flood')

@pytest.mark.parametrize('version,postgis,valid',[('140024','3.2.0',True),('140025','3.2.0',False),('140024','3.3.0',False)])
def test_qmf_only_exact_pg_numeric_version(monkeypatch,version,postgis,valid):
    values={'SHOW server_version_num':version,'SELECT PostGIS_Lib_Version()':postgis,
            'SHOW server_version':'14.24 (Ubuntu 14.24-0ubuntu0.22.04.1)'}
    monkeypatch.setattr(o,'scalar',lambda key:values[key])
    if valid:q.verify_pg_version()
    else:
        with pytest.raises(RuntimeError,match='version mismatch'):q.verify_pg_version()

def test_qmf_only_dry_run_never_launches(env,monkeypatch,capsys):
    monkeypatch.setattr(q,'start',lambda:pytest.fail('dry-run started service'))
    run.qmf_only_dispatch('start','QMF',True)
    result=json.loads(capsys.readouterr().out)
    assert result['will_start_service'] is False

def test_qmf_only_stop_on_failure_before_next_dataset(env,monkeypatch):
    from contextlib import nullcontext
    q.RUNTIME.mkdir();q.ORIGINAL_RUNTIME.mkdir(exist_ok=True)
    calls=[]
    monkeypatch.setattr(q,'verify_receipt',lambda:None)
    monkeypatch.setattr(q,'preserve_originals',lambda:None)
    monkeypatch.setattr(run,'verify_protocol',lambda:None)
    monkeypatch.setattr(q,'publish_summary',lambda:1)
    monkeypatch.setattr(q,'clean_admission',lambda:None)
    monkeypatch.setattr(q.shutil,'disk_usage',lambda _:type('D',(),{'free':100*s.GIB})())
    target=q.new_attempt(q.DATASETS[1])
    monkeypatch.setattr(q,'new_attempt',lambda d:(calls.append(d) or target))
    monkeypatch.setattr(q,'execution_context',lambda *_:nullcontext())
    row={'record_count':1,'source_path':str(env/'raw'),'sha256':None}
    Path(row['source_path']).write_bytes(b'raw');row['sha256']=s.sha(row['source_path'])
    s.atomic_json(s.OUT/'01_dataset_inventory'/(q.DATASETS[1]+'.json'),row)
    monkeypatch.setattr(run,'query_gate',lambda _:None)
    monkeypatch.setattr(q,'prepare',lambda _:None)
    monkeypatch.setattr(o,'run_method',lambda row,display,runtime:{'Status':'CORRECTNESS_FAILED'})
    monkeypatch.setattr(q,'stop_owned_postgres',lambda _:None)
    monkeypatch.setattr(q.signal,'signal',lambda *_:None)
    with pytest.raises(RuntimeError,match='CORRECTNESS_FAILED'):q.foreground()
    assert calls==[q.DATASETS[1]]

def test_qmf_only_full_completion_stops_without_methods(env,monkeypatch):
    q.RUNTIME.mkdir();q.ORIGINAL_RUNTIME.mkdir(exist_ok=True)
    monkeypatch.setattr(q,'valid_root',lambda _:q.FORMAL)
    monkeypatch.setattr(q,'verify_receipt',lambda:None)
    monkeypatch.setattr(q,'preserve_originals',lambda:None)
    monkeypatch.setattr(run,'verify_protocol',lambda:None)
    monkeypatch.setattr(q,'publish_summary',lambda:4)
    monkeypatch.setattr(q,'new_attempt',lambda _:pytest.fail('PASS rerun'))
    monkeypatch.setattr(q.signal,'signal',lambda *_:None)
    q.foreground()
    assert s.read_json(q.RUNTIME/'exit.json')['QMF_DATASETS_VALID']==4
    assert s.read_json(q.RUNTIME/'exit.json')['baselines_started'] is False
