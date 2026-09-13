"""Formal build timeout wiring, amendment gates and evidence-preserving retry."""
import ast
import copy
import inspect
from pathlib import Path
import subprocess
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import support as s
import run
import orchestrate as o
import repair_geolife as repair
from phase_timeouts import TIMEOUTS_S
from test_retry import retry_env, write_valid_method, terminal, bytes_under


def test_single_source_shared_by_campaign_and_repair():
    assert run.PROTOCOL['timeouts_s'] is TIMEOUTS_S
    assert o.TIMEOUTS_S is TIMEOUTS_S
    assert repair.run.PROTOCOL['timeouts_s'] is TIMEOUTS_S
    assert TIMEOUTS_S=={'build':43200,'correctness':43200,'timing':43200}
    assert inspect.signature(o.monitor).parameters['timeout'].default==14400
    assert inspect.signature(o.sql).parameters['timeout'].default==14400


@pytest.mark.parametrize('runtime',[m for _,m in s.METHODS])
def test_every_method_build_reaches_monitor_with_same_limit(retry_env,monkeypatch,runtime):
    monkeypatch.setattr(o,'COMMON',s.RUN/'common')
    (o.COMMON/'bmtree-official').mkdir(parents=True)
    calls=[]
    class Reached(Exception): pass
    def capture(command,label,timeout=14400,**kwargs):
        calls.append((label,timeout,kwargs.get('elapsed_before',0)))
        if 'bmtree_model' in label: return {'elapsed_seconds':123,'peak_rss_kib':1}
        raise Reached
    monkeypatch.setattr(o,'monitor',capture)
    with pytest.raises(Reached): o.build_one({'dataset_id':repair.D},runtime,1 if runtime=='postgis_gist' else 0)
    assert calls and all(v[1]==43200 for v in calls)
    if runtime=='bmtree': assert len(calls)==2 and calls[-1][2]==123
    else: assert calls[-1][2]==0


def test_postgis_reference_is_formal_build_and_uses_shared_limit(retry_env,monkeypatch):
    source=s.RUN/'source.csv'; source.parent.mkdir(parents=True,exist_ok=True); source.write_text('x,y\n')
    row={'dataset_id':repair.D,'source_path':str(source),'raw_bytes':source.stat().st_size,
         'mtime_ns':source.stat().st_mtime_ns}
    monkeypatch.setattr(o,'valid',lambda d,phase,*args:phase!='postgis_reference')
    monkeypatch.setattr(o,'ensure_pg',lambda:None)
    monkeypatch.setattr(o,'scalar',lambda sql:'1234' if 'pg_relation_size' in sql else '1')
    calls=[]
    def monitor(command,label,timeout=14400,**kwargs):
        calls.append((label,timeout)); return {'elapsed_seconds':17,'peak_rss_kib':9}
    monkeypatch.setattr(o,'monitor',monitor)
    o.prepare_dataset(row)
    assert calls==[(repair.D+'_reference_gist',43200)]
    result=o.build_one(row,'postgis_gist',0)
    assert result['build_seconds']==17
    assert len(calls)==1  # Receipt reuse never rebuilds a valid GiST.


@pytest.mark.parametrize('prior_seconds',[0,100])
def test_monitor_does_not_stop_at_four_hours_and_records_twelve_hour_timeout(retry_env,monkeypatch,prior_seconds):
    (s.OUT/'00_environment').mkdir(parents=True)
    s.RUN.mkdir(parents=True)
    monkeypatch.setattr(o,'CURRENT',{'phase':'build'})
    monkeypatch.setattr(o,'ctl',lambda *a,**kw:None)
    monkeypatch.setattr(o,'props',lambda unit:{'ActiveState':'active','Result':'success','ExecMainStatus':'0'})
    monkeypatch.setattr(o,'memory',lambda:{'available':25*s.GIB,'swap_in':0,'swap_out':0})
    snapshot={'path':'/test','kernel':{'memory.current':0,'memory.peak':0,'memory.swap.current':0,'memory.events':{}}}
    monkeypatch.setattr(o.cgroup_policy,'snapshot',lambda *a:snapshot)
    monkeypatch.setattr(o.cgroup_policy,'validate',lambda *a:True)
    monkeypatch.setattr(repair.diagnose,'ownership',lambda *a:{'fixture':True})
    clock=iter([0,14401,43201-prior_seconds,43202,43203])
    monkeypatch.setattr(o.time,'monotonic',lambda:next(clock))
    sleeps=[]; monkeypatch.setattr(o.time,'sleep',lambda n:sleeps.append(n))
    def no_launch(cmd,**kw):
        assert 'systemd-run' not in cmd
        return subprocess.CompletedProcess(cmd,0,stdout='',stderr='')
    monkeypatch.setattr(o.subprocess,'run',no_launch)
    with pytest.raises(o.Blocked,match='Predeclared phase timeout 43200s') as error:
        o.monitor([],'test_formal_build',TIMEOUTS_S['build'],adopt_unit='fixture',elapsed_before=prior_seconds)
    assert error.value.status=='BUILD_FAILED'
    assert sleeps==[.1]  # First sample at 14401s did not stop; second crossed total 43200s.
    receipt=s.read_json(s.OUT/'00_environment/test_formal_build_stop_receipt.json')
    assert receipt['reason']=='Predeclared phase timeout 43200s'


def test_only_expected_protocol_field_can_be_amended(retry_env):
    original=copy.deepcopy(run.PROTOCOL); original['timeouts_s']['build']=14400
    path=s.OUT/'00_environment/protocol.json'; s.atomic_json(path,original)
    before=path.read_bytes()
    with pytest.raises(RuntimeError): run.verify_protocol()
    audit={'old_build_timeout_s':14400,'new_build_timeout_s':43200,
           'original_protocol_sha256':s.sha(path),'effective_protocol':run.PROTOCOL}
    amendment=path.parent/'BUILD_TIMEOUT_PROTOCOL_AMENDMENT_20260913.json'
    s.atomic_json(amendment,audit)
    run.verify_protocol(); assert path.read_bytes()==before
    corrupt=copy.deepcopy(original); corrupt['performance']=2999
    s.atomic_json(path,corrupt)
    audit['original_protocol_sha256']=s.sha(path); s.atomic_json(amendment,audit)
    with pytest.raises(RuntimeError): run.verify_protocol()


def test_old_qmf_timeout_is_retry_eligible_and_preserved_in_new_attempt(retry_env,monkeypatch):
    s.done(repair.D,'qmap_uniform_qmf_method',{'Status':'BUILD_FAILED',
        'reason':'Predeclared phase timeout 14400s','Correctness':'NOT_RUN'})
    old=s.marker(repair.D,'qmap_uniform_qmf_method').read_bytes()
    for runtime in ['flood','rtree']: terminal(runtime)
    for runtime in repair.KEEP: write_valid_method(runtime)
    protected={p:b for p,b in bytes_under(s.OUT).items() if any(m in p for m in repair.KEEP)}
    assert repair.retry_queue()==['qmap_uniform_qmf','flood','rtree']
    monkeypatch.setattr(repair,'clean_preflight',lambda *a:pytest.fail('Valid method reached preflight'))
    for runtime in repair.KEEP: assert repair.attempt(runtime)=='SKIP_VALID'
    assert all((s.OUT/p).read_bytes()==b for p,b in protected.items())
    target=repair.retry_attempt('qmap_uniform_qmf')
    assert (target/'prior_results/checkpoints'/repair.D/'qmap_uniform_qmf_method.done').read_bytes()==old
    assert s.read_json(target/'started.json')['formal_build_timeout_s']==43200
    assert s.read_json(target/'superseded.json')['formal_build_timeout_s']==43200


def test_non_build_infrastructure_limits_unchanged():
    # Inspect real call sites: no mechanical replacement of infrastructure limits.
    for source in [o,run,repair]:
        tree=ast.parse(Path(source.__file__).read_text())
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call) or len(node.args)<3: continue
            text=ast.unparse(node.args[1])
            if any(tag in text for tag in ["'_normalize'","'_load'"]):
                assert isinstance(node.args[2],ast.Constant) and node.args[2].value==14400


def test_modules_import_without_starting_services(monkeypatch):
    import importlib.util
    def forbidden(*a,**kw): pytest.fail('Import started external work')
    monkeypatch.setattr(subprocess,'run',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    for module in [run,repair]:
        spec=importlib.util.spec_from_file_location('import_only_'+module.__name__,module.__file__)
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
