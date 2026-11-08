"""Retry admission, attempt generations and protection of scientific PASS results."""
from pathlib import Path
import subprocess
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import repair_geolife as repair
import support as s
import orchestrate as o
import report
import run
from paper_protocol import HOST_EMERGENCY_RESERVE


@pytest.fixture
def retry_env(tmp_path,monkeypatch):
    for module in [s,o]:
        monkeypatch.setattr(module,'OUT',tmp_path/'out')
        monkeypatch.setattr(module,'RUN',tmp_path/'runtime')
    monkeypatch.setattr(o,'ACTIVE',s.RUN/'active')
    monkeypatch.setattr(repair,'WORK',s.RUN/'geolife_repair')
    monkeypatch.setattr(repair,'DEBUG',s.OUT/'debug')
    monkeypatch.setattr(o,'update',lambda **kw:None)
    monkeypatch.setattr(repair,'stop_repair_postgres',lambda:None)
    monkeypatch.setattr(repair,'verify_protected',lambda:None)
    monkeypatch.setattr(run,'verify_source',lambda:None)
    monkeypatch.setattr(repair,'publish',lambda:None)
    s.atomic_json(s.OUT/'01_dataset_inventory'/(repair.D+'.json'),{'dataset_id':repair.D})
    return tmp_path


def terminal(runtime,status='HOST_SAFETY_STOP'):
    s.done(repair.D,runtime+'_method',{'Status':status,'Method':runtime,'Correctness':'NOT_RUN'})


def write_valid_method(runtime):
    """Small byte-backed evidence satisfying the existing scientific validator."""
    d=repair.D
    query=s.OUT/'02_queries'/d/(d+'_queries.csv')
    query.parent.mkdir(parents=True,exist_ok=True)
    query.write_text('query_id,split\n'+''.join(f'p{i},performance\n' for i in range(3000)))
    corr=s.OUT/'04_correctness'/d/(runtime+'.csv')
    corr.parent.mkdir(parents=True,exist_ok=True)
    corr.write_text('query_id,exact,missing,extra\n'+''.join(f'c{i},1,0,0\n' for i in range(1000)))
    s.done(d,runtime+'_correctness',{'exact':1000,'missing':0,'extra':0},[corr])
    raw=s.OUT/'05_performance'/d/runtime/'query_latency_raw.csv.zst'
    raw.parent.mkdir(parents=True,exist_ok=True)
    data='query_id,repetition,latency_ns\n'+''.join(f'p{i},{r},1000000\n' for r in range(5) for i in range(3000))
    subprocess.run(['zstd','-q','-o',str(raw)],input=data.encode(),check=True)
    for rep in range(1,6): s.done(d,f'{runtime}_timing_r{rep}',{'repetition':rep},[raw])
    s.done(d,runtime+'_build_r0',{'build_seconds':1.0})
    build=s.OUT/'03_build'/d/(runtime+'.json'); s.atomic_json(build,[{'build_seconds':1.0}])
    s.done(d,runtime+'_method',{'Method':runtime,'Status':'PASS','Correctness':'1000/1000 exact',
                               **{metric:1.0 for metric in s.METRICS}})
    assert report.valid_method(d,runtime)


def bytes_under(path):
    return {str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file()}


def test_pass_with_valid_correctness_and_timing_is_skipped(retry_env,monkeypatch):
    write_valid_method('qmap_uniform_qmf')
    before=bytes_under(s.OUT)
    monkeypatch.setattr(repair,'clean_preflight',lambda *a:pytest.fail('PASS reached admission'))
    monkeypatch.setattr(o,'run_method',lambda *a:pytest.fail('PASS rerun'))
    assert repair.attempt('qmap_uniform_qmf')=='SKIP_VALID'
    assert bytes_under(s.OUT)==before


def test_pass_label_without_correctness_evidence_is_retry_eligible(retry_env):
    terminal('qmap_uniform_qmf','PASS')
    assert repair.retry_decision('qmap_uniform_qmf')=='RETRY_ELIGIBLE'


@pytest.mark.parametrize('status',['HOST_SAFETY_STOP','OOM_KILLED','CGROUP_MEMORY_MAX',
 'BUILD_FAILED','CORRECTNESS_FAILED','WARMUP_FAILED','TIMING_FAILED','SWAP_INVALID',
 'FINALIZATION_FAILED','REPORTING_FAILED','TIMEOUT'])
def test_failed_historical_attempt_and_done_do_not_block_new_retry(retry_env,monkeypatch,status):
    runtime='qmap_uniform_qmf'; terminal(runtime,status)
    old=s.marker(repair.D,runtime+'_method').read_bytes()
    legacy=repair.DEBUG/'attempts'/runtime
    s.atomic_json(legacy/'started.json',{'at':1})
    s.atomic_json(legacy/'finished.json',{'result':{'Status':status}})
    legacy_before=bytes_under(legacy)
    # Even an old phase marker cannot skip this failed generation's fresh retry.
    s.done(repair.D,runtime+'_build_r0',{'build_seconds':99})
    old_build=s.marker(repair.D,runtime+'_build_r0').read_bytes()
    calls=[]
    monkeypatch.setattr(repair,'clean_preflight',lambda *a:None)
    def execute(row,display,method):
        calls.append(method)
        assert not s.marker(repair.D,method+'_method').exists()
        assert not s.marker(repair.D,method+'_build_r0').exists()
        terminal(method,status)
        return s.read_json(s.marker(repair.D,method+'_method'))['payload']
    monkeypatch.setattr(o,'run_method',execute)
    repair.attempt(runtime)
    pointer=s.read_json(repair.WORK/'retry_state'/(runtime+'.json'))
    target=Path(pointer['target'])
    assert (target/'prior_results/checkpoints'/repair.D/(runtime+'_method.done')).read_bytes()==old
    assert (target/'prior_results/checkpoints'/repair.D/(runtime+'_build_r0.done')).read_bytes()==old_build
    assert bytes_under(legacy)==legacy_before
    # A newly failed retry stays eligible on the NEXT invocation as well.
    repair.attempt(runtime)
    assert s.read_json(repair.WORK/'retry_state'/(runtime+'.json'))['attempt_id']!=pointer['attempt_id']
    assert calls==[runtime,runtime]


def test_only_three_scheduled_and_five_valid_methods_byte_preserved(retry_env,monkeypatch):
    for runtime in repair.KEEP: write_valid_method(runtime)
    for runtime in repair.ORDER: terminal(runtime)
    protected={str(p):p.read_bytes() for p in s.OUT.rglob('*') if p.is_file() and
               any(runtime in str(p) for runtime in repair.KEEP)}
    assert repair.retry_queue()==['qmap_uniform_qmf','flood','rtree']
    calls=[]
    monkeypatch.setattr(repair,'clean_preflight',lambda *a:None)
    def execute(row,display,runtime):
        calls.append(runtime); terminal(runtime)
        return {'Status':'HOST_SAFETY_STOP'}
    monkeypatch.setattr(o,'run_method',execute)
    for runtime in repair.KEEP: assert repair.attempt(runtime)=='SKIP_VALID'
    for runtime in repair.retry_queue(): repair.attempt(runtime)
    assert calls==['qmap_uniform_qmf','flood','rtree']
    assert all(Path(path).read_bytes()==value for path,value in protected.items())
    assert all(report.valid_method(repair.D,runtime) for runtime in repair.KEEP)


def test_interrupted_current_generation_resumes_its_completed_phase(retry_env,monkeypatch):
    runtime='flood'; terminal(runtime)
    target=repair.retry_attempt(runtime)
    s.done(repair.D,runtime+'_build_r0',{'build_seconds':123})
    completed=s.marker(repair.D,runtime+'_build_r0').read_bytes()
    assert repair.retry_attempt(runtime)==target
    assert s.marker(repair.D,runtime+'_build_r0').read_bytes()==completed


def test_interrupted_supersession_finishes_persisted_plan(retry_env,monkeypatch):
    runtime='flood'; terminal(runtime)
    s.done(repair.D,runtime+'_build_r0',{'build_seconds':123})
    rename=repair.os.rename; calls=[]
    def interrupted(source,dest):
        calls.append(str(source))
        if len(calls)==2: raise KeyboardInterrupt('simulated interruption')
        rename(source,dest)
    monkeypatch.setattr(repair.os,'rename',interrupted)
    with pytest.raises(KeyboardInterrupt): repair.retry_attempt(runtime)
    state=s.read_json(repair.WORK/'retry_state'/(runtime+'.json'))
    assert state['phase']=='superseding'
    monkeypatch.setattr(repair.os,'rename',rename)
    assert repair.retry_attempt(runtime)==Path(state['target'])
    assert s.read_json(repair.WORK/'retry_state'/(runtime+'.json'))['phase']=='running'
    assert not s.marker(repair.D,runtime+'_method').exists()


def test_explicit_unrecoverable_limit_is_required_to_exclude_failed_method(retry_env):
    terminal('flood','IMPLEMENTATION_LIMIT')
    assert repair.retry_decision('flood')=='RETRY_ELIGIBLE'
    s.done(repair.D,'flood_method',{'Status':'IMPLEMENTATION_LIMIT','reason':'unsupported representation',
                                   'unrecoverable':True})
    assert repair.retry_decision('flood')=='IMPLEMENTATION_LIMIT'
    assert repair.retry_queue()==['qmap_uniform_qmf','rtree']


def host(available=24*s.GIB,swap=0):
    return {'host_meminfo':{'MemAvailable':available},'processes':[],
            'parent':{'path':'/qmf.slice/qmf-paper.slice','kernel':{'memory.swap.current':swap}}}


def test_low_memory_waits_without_marking_failure_then_admits_at_host_reserve(retry_env,monkeypatch):
    terminal('flood'); cp=s.marker(repair.D,'flood_method'); previous=cp.read_bytes()
    reserve=HOST_EMERGENCY_RESERVE
    samples=iter([host(reserve-1),host(reserve)])
    monkeypatch.setattr(repair.diagnose,'ownership',lambda *a:next(samples))
    monkeypatch.setattr(repair,'stale_processes',lambda current:[])
    sleeps=[]; states=[]
    monkeypatch.setattr(repair.time,'sleep',lambda seconds:sleeps.append(seconds))
    monkeypatch.setattr(o,'update',lambda **kw:states.append(kw))
    assert repair.clean_preflight('flood')['host_meminfo']['MemAvailable']==reserve
    assert sleeps==[10]
    assert states[0]['status']=='WAITING' and states[0]['phase']=='waiting_for_host_memory'
    assert states[-1]['phase']=='retry_ready'
    assert cp.read_bytes()==previous
    assert not (repair.WORK/'retry_state/flood.json').exists()
    assert HOST_EMERGENCY_RESERVE==3.5*s.GIB
    assert (o.cgroup_policy.MEMORY_HIGH,o.cgroup_policy.MEMORY_MAX,o.cgroup_policy.SWAP_MAX)==(22*s.GIB,24*s.GIB,0)


@pytest.mark.parametrize('swap,live',[(1,[]),(0,['worker']),(None,[])])
def test_dirty_environment_prevents_admission_without_method_failure(retry_env,monkeypatch,swap,live):
    terminal('rtree'); before=s.marker(repair.D,'rtree_method').read_bytes()
    monkeypatch.setattr(repair.diagnose,'ownership',lambda *a:host(swap=swap))
    monkeypatch.setattr(repair,'stale_processes',lambda current:live)
    monkeypatch.setattr(repair.time,'sleep',lambda *a:pytest.fail('Dirty environment must be resolved'))
    with pytest.raises(RuntimeError): repair.clean_preflight('rtree')
    assert s.marker(repair.D,'rtree_method').read_bytes()==before


def test_55445_listener_outside_experiment_is_detected(retry_env,monkeypatch):
    monkeypatch.setattr(repair.subprocess,'check_output',lambda cmd,**kw:
                        'u_str LISTEN /tmp/.s.PGSQL.55445' if cmd[:2]==['ss','-H'] and '-lx' in cmd else '')
    assert repair.stale_processes(host())==['PostgreSQL port/socket 55445 remains active']


def test_current_build_process_outside_cgroup_is_detected(retry_env,monkeypatch):
    monkeypatch.setattr(repair.subprocess,'check_output',lambda *a,**kw:'')
    read=Path.read_bytes
    monkeypatch.setattr(Path,'read_bytes',lambda p: b'/bin/qmap_build_index\0--method\0flood\0' if str(p)=='/proc/999999/cmdline' else read(p))
    current=host(); current['processes']=[{'pid':999999,'name':'qmap_build_inde','cgroup':'/outside'}]
    assert repair.stale_processes(current)==[999999]


def test_admission_happens_before_evidence_supersession_and_each_execution(retry_env,monkeypatch):
    for runtime in repair.ORDER: terminal(runtime)
    events=[]; original=repair.retry_attempt
    monkeypatch.setattr(repair,'clean_preflight',lambda runtime:events.append(('admit',runtime)))
    def supersede(runtime):
        events.append(('supersede',runtime)); return original(runtime)
    monkeypatch.setattr(repair,'retry_attempt',supersede)
    def execute(row,display,runtime):
        events.append(('execute',runtime)); terminal(runtime); return {'Status':'HOST_SAFETY_STOP'}
    monkeypatch.setattr(o,'run_method',execute)
    for runtime in repair.retry_queue(): repair.attempt(runtime)
    assert events==[(action,runtime) for runtime in repair.ORDER for action in ['admit','supersede','admit','execute']]


def test_foreign_postgres_is_never_stopped(retry_env,monkeypatch):
    # Load the real function hidden by the fixture without invoking its CLI.
    import importlib.util
    spec=importlib.util.spec_from_file_location('repair_stop_test',Path(repair.__file__))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module,'WORK',repair.WORK)
    monkeypatch.setattr(o,'props',lambda unit:{'ActiveState':'active'})
    calls=[]
    def ctl(*args,**kw):
        calls.append(args)
        return subprocess.CompletedProcess(args,0,stdout='ExecStart=postgres -D /another/pg_data',stderr='')
    monkeypatch.setattr(o,'ctl',ctl)
    with pytest.raises(RuntimeError,match='another benchmark'): module.stop_repair_postgres()
    assert all(args[0]!='stop' for args in calls)


@pytest.mark.parametrize('runtime',repair.ORDER)
def test_real_method_controller_reaches_build_despite_old_failed_markers(retry_env,monkeypatch,runtime):
    terminal(runtime)
    s.done(repair.D,runtime+'_build_r0',{'build_seconds':999})
    s.atomic_json(repair.DEBUG/'attempts'/runtime/'finished.json',{'result':{'Status':'HOST_SAFETY_STOP'}})
    point=s.RUN/'raw.csv'; point.parent.mkdir(parents=True,exist_ok=True); point.write_text('x,y\n1,2\n')
    query=s.OUT/'02_queries'/repair.D/(repair.D+'_queries.csv')
    query.parent.mkdir(parents=True,exist_ok=True); query.write_text('query_id,split\n')
    s.atomic_json(query.parent/'query_manifest.json',{'query_sha256':s.sha(query)})
    s.atomic_json(s.OUT/'01_dataset_inventory'/(repair.D+'.json'),{
        'dataset_id':repair.D,'source_path':str(point),'raw_bytes':point.stat().st_size,
        'mtime_ns':point.stat().st_mtime_ns})
    monkeypatch.setattr(repair,'clean_preflight',lambda *a:None)
    monkeypatch.setattr(o,'ensure_pg',lambda:None)
    monkeypatch.setattr(o,'props',lambda unit:{'ActiveState':'inactive'})
    calls=[]
    def build(row,method,rep):
        calls.append((method,rep))
        raise o.Blocked('HOST_SAFETY_STOP','fixture stop after reaching actual build dispatch','build')
    monkeypatch.setattr(o,'build_one',build)
    result=repair.attempt(runtime)
    assert calls==[(runtime,0)]
    assert result['Status']=='HOST_SAFETY_STOP'
    assert repair.retry_decision(runtime)=='RETRY_ELIGIBLE'
