from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import outcomes
import support as s
import report
import orchestrate as o
import run

@pytest.mark.parametrize('phase,reason,events,oomd,swap,expected',[
 ('build','HOST_SAFETY_STOP',{},False,0,'HOST_SAFETY_STOP'),
 ('timing','signal',{'max':0,'oom':0,'oom_kill':0},True,0,'OOM_KILLED'),
 ('build','signal',{'high':782631},True,0,'OOM_KILLED'),
 ('build','allocation failed',{'max':1},False,0,'CGROUP_MEMORY_MAX'),
 ('build','signal',{'oom_kill':1},False,0,'OOM_KILLED'),
 ('timing','failure',{},False,1,'SWAP_INVALID'),
 ('correctness','mismatch',{},False,0,'CORRECTNESS_FAILED'),
 ('warmup','connection lost',{},False,0,'WARMUP_FAILED'),
 ('timing','connection lost',{},False,0,'TIMING_FAILED'),
 ('finalization','empty CSV',{},False,0,'FINALIZATION_FAILED'),
 ('reporting','empty CSV',{},False,0,'REPORTING_FAILED'),
 ('build','bad allocation',{'high':9},False,0,'BUILD_FAILED')])
def test_taxonomy(phase,reason,events,oomd,swap,expected):
    assert outcomes.classify(phase,reason,events,oomd=oomd,swap=swap)==expected

def test_old_cgroup_event_is_not_new_failure():
    assert outcomes.classify('timing','connection lost',{'oom_kill':1,'max':4},
                             {'oom_kill':1,'max':4})=='TIMING_FAILED'

def test_stale_latency_does_not_prove_current_warmup_finished(tmp_path):
    import os
    stale=tmp_path/'latency.r0.csv.part.zst'; stale.write_bytes(b'old')
    os.utime(stale,(10,10))
    command=['harness','--latency-output',str(tmp_path/'latency')]
    assert o.observed_query_phase(command,20)=='warmup'
    current=tmp_path/'latency.r0.csv.part'; current.write_bytes(b'header')
    os.utime(current,(30,30))
    assert o.observed_query_phase(command,20)=='timing'

def test_monitor_phase_is_separate_from_terminal_cause():
    failure=o.Blocked('HOST_SAFETY_STOP','reserve breached','warmup')
    assert failure.phase=='warmup'
    assert failure.status=='HOST_SAFETY_STOP'

def test_read_only_cgroup_polling_does_not_require_sudo():
    import cgroup_policy as cg
    assert cg.manager()==['systemctl']
    assert cg.manager(True)==['sudo','-n','systemctl']

def test_surviving_restore_worker_is_monitored_without_duplicate_launch(tmp_path,monkeypatch):
    import subprocess
    monkeypatch.setattr(o,'OUT',tmp_path/'out'); monkeypatch.setattr(o,'RUN',tmp_path/'run')
    o.RUN.mkdir(); (o.OUT/'00_environment').mkdir(parents=True)
    monkeypatch.setattr(o,'CURRENT',{'phase':'load'})
    monkeypatch.setattr(o,'update',lambda **kw: None)
    monkeypatch.setattr(o,'ctl',lambda *a,**kw: None)
    monkeypatch.setattr(o,'props',lambda unit: {'ActiveState':'inactive','Result':'success','ExecMainStatus':'0'})
    monkeypatch.setattr(o,'memory',lambda: {'available':25*s.GIB,'swap_in':0,'swap_out':0})
    snapshot={'path':'/test','kernel':{'memory.current':0,'memory.peak':0,'memory.swap.current':0,'memory.events':{}}}
    monkeypatch.setattr(o.cgroup_policy,'snapshot',lambda unit: snapshot)
    monkeypatch.setattr(o.cgroup_policy,'validate',lambda *a: True)
    def no_duplicate(cmd,**kw):
        assert 'systemd-run' not in cmd
        return subprocess.CompletedProcess(cmd,0,stdout='',stderr='')
    monkeypatch.setattr(o.subprocess,'run',no_duplicate)
    result=o.monitor([],'fixture_load',adopt_unit='qmf-paper-worker-original')
    assert result['status']=='PASS'

def test_attempted_is_not_scientifically_complete(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'OUT',tmp_path)
    for display,runtime in s.METHODS: s.done('fixture',runtime+'_method',{'Method':display,'Status':'BUILD_FAILED'})
    result=report.completion('fixture')
    assert result=={'methods_attempted':8,'methods_valid':0,'attempted':True,'scientifically_complete':False}

def test_retry_preserves_attempted_count_and_completed_postgis_phases(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'OUT',tmp_path)
    dataset='geolife_2d_4p2G'
    for display,runtime in s.METHODS:
        s.atomic_json(tmp_path/'debug/original_attempts'/runtime/(runtime+'_method.done'),{'payload':{'Status':'BUILD_FAILED'}})
    s.done(dataset,'postgis_gist_build_r0',{'build_seconds':1389.09,'serialized_bytes':10347552768,'peak_rss_kib':222136})
    s.done(dataset,'postgis_gist_correctness',{'exact':1000,'missing':0,'extra':0})
    assert report.completion(dataset)['methods_attempted']==8
    row=report.rows(dataset)[1]
    assert row['Build_s']==1389.09
    assert row['Correctness']=='1000/1000 exact'
    assert row['Status']=='INCOMPLETE'
    assert row['Mean_ms'] is None

def test_resume_does_not_reset_valid_count_to_four(tmp_path,monkeypatch):
    import repair_geolife as repair
    monkeypatch.setattr(s,'OUT',tmp_path); monkeypatch.setattr(repair,'DEBUG',tmp_path/'debug')
    s.atomic_json(repair.DEBUG/'FOUR_METHOD_FAILURE_FORENSICS.json',{})
    s.done(repair.D,'dataset_complete',{'methods_valid':4})
    monkeypatch.setattr(report,'completion',lambda d: {'methods_attempted':8,'methods_valid':5,'attempted':True,'scientifically_complete':False})
    repair.correct_taxonomy()
    assert s.read_json(s.marker(repair.D,'dataset_complete'))['payload']['methods_valid']==5

def test_restored_gist_layout_variation_does_not_repeat_build(tmp_path,monkeypatch):
    import repair_geolife as repair
    monkeypatch.setattr(s,'OUT',tmp_path); monkeypatch.setattr(repair,'DEBUG',tmp_path/'debug')
    s.atomic_json(tmp_path/'01_dataset_inventory'/(repair.D+'.json'),{'record_count':181000000})
    s.atomic_json(repair.DEBUG/'runtime_restored.json',{'restored_gist_bytes':10240180224,
        'original_gist_bytes':10347552768,'original_build_s_preserved':1389.09})
    s.atomic_json(repair.DEBUG/'original_attempts/postgis_reference.done',{'payload':{'elapsed_seconds':1389.09}})
    s.done(repair.D,'load',{'points':181000000})
    monkeypatch.setattr(o,'update',lambda **kw: None)
    monkeypatch.setattr(o.cgroup_policy,'configure',lambda *a: None)
    monkeypatch.setattr(o.cgroup_policy,'snapshot',lambda *a: {'path':'/test'})
    monkeypatch.setattr(o.cgroup_policy,'validate',lambda *a: True)
    monkeypatch.setattr(run,'normalized',lambda *a: None)
    monkeypatch.setattr(o,'setup',lambda: None)
    monkeypatch.setattr(o,'prepare_dataset',lambda *a: pytest.fail('Valid restored GiST rebuilt'))
    responses={"SELECT to_regclass('points_gist') IS NOT NULL":'t',
        "SELECT pg_relation_size('points_gist')":'10240180224',
        "SELECT indisvalid AND indisready FROM pg_index WHERE indexrelid='points_gist'::regclass":'t',
        "SELECT min(id)::text || ',' || max(id)::text FROM points":'0,180999999',
        "SELECT pg_get_indexdef('points_gist'::regclass)":'CREATE INDEX points_gist ON public.points USING gist (geom)'}
    monkeypatch.setattr(o,'scalar',lambda sql: responses[sql])
    repair.prepare_runtime()
    value=s.read_json(repair.DEBUG/'restored_runtime_acceptance.json')
    assert value['observed_index_bytes']==10240180224
    assert value['build_measurement_reused_s']==1389.09

def test_incomplete_dataset_database_preserved(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'OUT',tmp_path)
    s.done('fixture','results_persisted',{})
    monkeypatch.setattr(o,'sql',lambda *a: pytest.fail('Incomplete database dropped'))
    with pytest.raises(RuntimeError,match='scientifically incomplete'): run.cleanup({'dataset_id':'fixture'})

def test_failed_method_runtime_survives(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'OUT',tmp_path/'out'); monkeypatch.setattr(o,'OUT',s.OUT)
    monkeypatch.setattr(o,'ACTIVE',tmp_path/'active')
    path=o.ACTIVE/'fixture/methods/flood'; path.mkdir(parents=True)
    (path/'flood.idx').write_bytes(b'index')
    s.done('fixture','flood_method',{'Status':'HOST_SAFETY_STOP'})
    o.cleanup_method('fixture','flood')
    assert (path/'flood.idx').read_bytes()==b'index'
