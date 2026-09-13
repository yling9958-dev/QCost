"""Checkpointed GeoLife-only repair; no baseline tuning or forward-dataset launch."""
import argparse
import csv
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid
import support as s
import orchestrate as o
import run
import report
import diagnose

D='geolife_2d_4p2G'
ORDER=['qmap_uniform_qmf','flood','rtree']
KEEP=['postgis_gist','lisa','tsunami','lmsfc','bmtree']
RETRY_MIN_AVAILABLE=24*s.GIB
UNIT='qmf-paper-geolife-repair-20260912'
DEBUG=s.OUT/'debug'
WORK=s.RUN/'geolife_repair'

def archive(path,target):
    if path.is_file() and not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target)

def configure():
    o.UNIT=UNIT; o.STATE=WORK/'status.json'; o.COMMON=WORK/'common'
    o.COMMON.mkdir(parents=True,exist_ok=True)
    for name in ['build','baselines','extension','learnedbench-patched','repro-source']:
        target=o.COMMON/name
        if not target.exists(): target.symlink_to(s.RUN/'common'/name,target_is_directory=True)
    o.ENV.update(QMF_RUNTIME=str(o.COMMON),QMAP_BUILD_ROOT=str(o.COMMON/'build'),
                 QMAP_BASELINE_WORK=str(o.COMMON/'baselines'),PGHOST=str(o.COMMON/'pg_socket'))

def protect_valid():
    path=DEBUG/'preserved_valid_evidence.json'
    if not path.exists():
        files=set()
        for runtime in KEEP:
            if not report.valid_method(D,runtime): raise RuntimeError('Previously valid method no longer validates: '+runtime)
            files.update((s.OUT/'checkpoints'/D).glob(runtime+'*.done'))
            files.update((s.OUT/'04_correctness'/D).glob(runtime+'*'))
            files.update((s.OUT/'05_performance'/D/runtime).rglob('*'))
            files.add(s.OUT/'03_build'/D/(runtime+'.json'))
        for row in run.DATASETS: files.update((s.OUT/'02_queries'/row).rglob('*'))
        for name in ['postgis_gist_build_r0','postgis_gist_correctness']:
            cp=s.marker(D,name)
            if not s.valid(D,name): raise RuntimeError('Required PostGIS checkpoint invalid: '+name)
            files.add(cp)
            files.update(Path(e['path']) for e in s.read_json(cp)['files'])
        # Preserve Gowalla's completed phases and partial repetition exactly.
        files.update((s.OUT/'checkpoints'/run.DATASETS[1]).glob('*.done'))
        files.update((s.OUT/'05_performance'/run.DATASETS[1]).rglob('*'))
        entries=[{'path':str(p),'bytes':p.stat().st_size,'sha256':s.sha(p)} for p in sorted(files) if p.is_file()]
        s.atomic_json(path,entries)
    # The original receipt predates PostGIS timing recovery. Add a new receipt;
    # never rewrite the historical protection manifest or any valid method file.
    path=DEBUG/'preserved_five_pass_methods.json'
    if not path.exists():
        files=set()
        for runtime in KEEP:
            if not report.valid_method(D,runtime): raise RuntimeError('Previously valid method no longer validates: '+runtime)
            files.update((s.OUT/'checkpoints'/D).glob(runtime+'*.done'))
            files.update((s.OUT/'04_correctness'/D).glob(runtime+'*'))
            files.update((s.OUT/'05_performance'/D/runtime).rglob('*'))
            files.update((s.OUT/'00_environment').glob(D+'_'+runtime+'_*'))
            files.add(s.OUT/'03_build'/D/(runtime+'.json'))
        s.atomic_json(path,[{'path':str(p),'bytes':p.stat().st_size,'sha256':s.sha(p)}
                            for p in sorted(files) if p.is_file()])
    verify_protected()

def verify_protected():
    for name in ['preserved_valid_evidence.json','preserved_five_pass_methods.json']:
        path=DEBUG/name
        if name=='preserved_five_pass_methods.json' and not path.exists(): continue
        for e in s.read_json(path):
            p=Path(e['path'])
            if not p.is_file() or p.stat().st_size!=e['bytes'] or s.sha(p)!=e['sha256']:
                raise RuntimeError('Preserved evidence changed: '+str(p))

def retry_decision(runtime):
    if report.valid_method(D,runtime): return 'SKIP_VALID'
    cp=s.marker(D,runtime+'_method')
    value=s.read_json(cp).get('payload',{}) if cp.exists() else {}
    if value.get('Status')=='IMPLEMENTATION_LIMIT' and value.get('reason') and \
       (value.get('unrecoverable') is True or value.get('retryable') is False):
        return 'IMPLEMENTATION_LIMIT'
    # An attempt receipt or terminal phase failure is never scientific completion.
    return 'RETRY_ELIGIBLE'

def retry_queue():
    return [runtime for runtime in ORDER if retry_decision(runtime)=='RETRY_ELIGIBLE']

def correct_taxonomy():
    evidence=s.read_json(DEBUG/'FOUR_METHOD_FAILURE_FORENSICS.json')
    for runtime in ORDER:
        cp=s.marker(D,runtime+'_method')
        if not cp.exists(): continue
        v=s.read_json(cp)
        if v['payload']['Status']=='PASS': continue
        original=DEBUG/'original_attempts'/runtime/cp.name
        archive(cp,original)
        if (DEBUG/'attempts'/runtime/'started.json').exists(): continue
        v['payload'].update(Status=evidence[runtime]['classification'],failed_phase=evidence[runtime]['failed_phase'],
            original_status=s.read_json(original)['payload']['Status'],classification_evidence='debug/FOUR_METHOD_FAILURE_FORENSICS.json')
        s.atomic_json(cp,v)
    old=s.marker(D,'dataset_complete')
    if old.exists():
        archive(old,DEBUG/'original_attempts/dataset_complete.done')
        value=s.read_json(old); value['payload'].update(report.completion(D))
        s.atomic_json(old,value)

def publish():
    row=s.read_json(s.OUT/'01_dataset_inventory'/(D+'.json'))
    files=report.dataset_report(row,0)
    s.done(D,'results_persisted',{'printed':True,**report.completion(D)},files)
    report.aggregate(s.read_json(s.RUN/'inventory.json'))

def stale_processes(current):
    live=[]
    for p in current['processes']:
        if p['pid']==os.getpid(): continue
        try:
            args=Path(f'/proc/{p["pid"]}/cmdline').read_bytes().decode(errors='replace').split('\0')
        except FileNotFoundError: continue
        except PermissionError:
            if p.get('in_experiment'): live.append(p['pid'])
            continue
        names={Path(a).name for a in args if a}
        postgres=p['name'].startswith('postgres') and ('/qmf' in p['cgroup'] or '55445' in args or
                     '--port=55445' in args or '-p55445' in args)
        worker=bool(names & {'qmf_postgres_full','qmap_build_index','build_static_qw_index.py'})
        if postgres or worker or p.get('normalized_mappings') or p.get('in_experiment'):
            live.append(p['pid'])
    for prefix in [['systemctl'],['systemctl','--user']]:
        workers=subprocess.check_output(prefix+['list-units','qmf-paper-worker-*',
                '--state=active,activating,deactivating','--no-legend'],text=True)
        if workers.strip(): live.append(workers.strip())
    # Also catch a PostgreSQL listener outside the experiment cgroup.
    tcp=subprocess.check_output(['ss','-H','-ltn','sport = :55445'],text=True)
    unix=subprocess.check_output(['ss','-H','-lx'],text=True)
    if tcp.strip() or any('.s.PGSQL.55445' in line for line in unix.splitlines()):
        live.append('PostgreSQL port/socket 55445 remains active')
    return live

def clean_preflight(runtime='shared'):
    while True:
        current=diagnose.ownership(o.SLICE)
        live=stale_processes(current)
        if live: raise RuntimeError('Previous benchmark process still active: '+repr(live))
        parent=current['parent']; kernel=parent.get('kernel',{})
        swap=kernel.get('memory.swap.current',0 if not parent.get('path') else None)
        if swap!=0: raise RuntimeError('Experiment swap must be verified zero before retry')
        available=current['host_meminfo']['MemAvailable']
        s.atomic_json(DEBUG/'retry_preflight'/f'{runtime}.json',{
            **current,'minimum_start_memavailable_bytes':RETRY_MIN_AVAILABLE,
            'ready':available>=RETRY_MIN_AVAILABLE})
        if available>=RETRY_MIN_AVAILABLE:
            o.update(dataset=D,method=runtime,phase='retry_ready',status='RUNNING')
            return current
        # Waiting is infrastructure state, never a failed method receipt.
        o.update(dataset=D,method=runtime,phase='waiting_for_host_memory',status='WAITING',
                 MemAvailable=available,required_MemAvailable=RETRY_MIN_AVAILABLE)
        time.sleep(10)

def stop_repair_postgres():
    if o.props(o.PGUNIT).get('ActiveState') not in ('active','activating','deactivating'): return
    command=o.ctl('show',o.PGUNIT,'-p','ExecStart').stdout
    if str(WORK/'common/pg_data') not in command:
        raise RuntimeError('Refuse to stop PostgreSQL owned by another benchmark')
    o.ctl('stop',o.PGUNIT,check=True)

def adopt_restoration_load():
    """Reattach to this repair's surviving COPY; never launch a second SQL load."""
    state=s.read_json(o.STATE) if o.STATE.exists() else {}
    unit=state.get('active_unit','')
    if state.get('dataset')!=D or state.get('phase')!='load' or not unit: return False
    if o.props(unit).get('ActiveState')!='active': return False
    worker=o.ctl('show',unit,'-p','ExecStart').stdout
    pg=o.ctl('show',o.PGUNIT,'-p','ExecStart').stdout
    if str(WORK/'common/pg_data') not in pg or str(s.RUN/'load.sql') not in worker:
        raise RuntimeError('Surviving worker is not this repair database load')
    archive(o.STATE,DEBUG/'load_controller_handoff.json')
    archive(s.OUT/'00_environment'/(D+'_load_resources.csv'),DEBUG/'load_resources_before_handoff.csv')
    o.update(dataset=D,method='shared',phase='load',status='RUNNING')
    o.monitor([],D+'_load',14400,adopt_unit=unit)
    o.sql('CREATE OR REPLACE VIEW evaluation AS SELECT id,x,y,x AS lon,y AS lat,geom FROM points; ANALYZE points;',D+'_analyze',1800)
    count=int(o.scalar('SELECT count(*) FROM points'))
    if count!=181000000: raise RuntimeError('Restored GeoLife point count mismatch')
    s.done(D,'load',{'points':count,'id_mapping':'source ordinal from identity START 0','adopted_restore_worker':unit})
    return True

def prepare_runtime():
    o.cgroup_policy.configure(o.SLICE)
    parent=o.cgroup_policy.snapshot(o.SLICE); o.cgroup_policy.validate(parent)
    if parent['path'].startswith('/user.slice/'):
        raise RuntimeError('Repair experiment still under desktop pressure ancestor')
    o.update(dataset=D,method='shared',phase='normalized_sha_verification',status='RUNNING')
    run.normalized(s.read_json(s.OUT/'01_dataset_inventory'/(D+'.json')))
    o.setup()
    parent=o.cgroup_policy.snapshot(o.SLICE)
    o.cgroup_policy.validate(parent,[o.cgroup_policy.snapshot(o.PGUNIT)])
    s.atomic_json(DEBUG/'effective_repair_cgroup.json',{'parent':parent,'postgres':o.cgroup_policy.snapshot(o.PGUNIT),
       'scope':'system-owned experiment slice; worker UID unchanged; outside user@1000 desktop PSI policy',
       'limits_changed':False,'query_protocol_changed':False})
    ready=DEBUG/'runtime_restored.json'
    if ready.exists():
        if o.scalar("SELECT to_regclass('points_gist') IS NOT NULL")!='t': raise RuntimeError('Restored index missing')
        receipt=s.read_json(ready)
        observed=int(o.scalar("SELECT pg_relation_size('points_gist')"))
        if observed!=receipt['restored_gist_bytes']: raise RuntimeError('Restored GiST changed since restoration receipt')
        if o.scalar("SELECT indisvalid AND indisready FROM pg_index WHERE indexrelid='points_gist'::regclass")!='t':
            raise RuntimeError('Restored GiST is not valid and ready')
        if o.scalar("SELECT min(id)::text || ',' || max(id)::text FROM points")!='0,180999999':
            raise RuntimeError('Restored full GeoLife identity bounds differ')
        if s.read_json(s.marker(D,'load'))['payload']['points']!=181000000:
            raise RuntimeError('Restored full point count differs')
        definition=o.scalar("SELECT pg_get_indexdef('points_gist'::regclass)")
        if 'USING gist (geom)' not in definition: raise RuntimeError('Restored index definition differs')
        s.atomic_json(DEBUG/'restored_runtime_acceptance.json',{'at':time.time(),'points':181000000,
            'id_bounds':[0,180999999],'index_valid_ready':True,'index_definition':definition,
            'observed_index_bytes':observed,'original_index_bytes':receipt['original_gist_bytes'],
            'build_measurement_reused_s':receipt['original_build_s_preserved'],
            'correctness_checkpoint_reused':'same frozen data, IDs, queries, PostgreSQL/PostGIS and exact query semantics',
            'size_policy':'Actual restored query-ready size; original size retained as historical measurement',
            'layout_note':'PostgreSQL 14.24 gistchoose uses random equal-penalty tie breaking; byte-size identity is not guaranteed'})
        shutil.copy2(DEBUG/'original_attempts/postgis_reference.done',s.marker(D,'postgis_reference'))
        return
    row=s.read_json(s.OUT/'01_dataset_inventory'/(D+'.json'))
    for name in ['postgis_reference','load']:
        archive(s.marker(D,name),DEBUG/'original_attempts'/(name+'.done'))
    o.prepare_dataset(row)
    size=int(o.scalar("SELECT pg_relation_size('points_gist')"))
    build=s.read_json(s.marker(D,'postgis_gist_build_r0'))['payload']
    # The original physical index was dropped, so the recovery representation must
    # be rebuilt. Its restoration cost is separate from the frozen measured build.
    s.atomic_json(ready,{'at':time.time(),'restored_points':row['record_count'],'restored_gist_bytes':size,
        'original_gist_bytes':build['serialized_bytes'],'original_build_s_preserved':build['build_seconds'],
        'restoration_reference':s.read_json(s.marker(D,'postgis_reference')),
        'original_deleted_by':'GeoLife cleanup DROP TABLE at 2026-09-12 04:44:06; completed measurement retained',
        'representation_note':'Deterministic same source/ID map and original CREATE INDEX/ANALYZE SQL; restored bytes recorded independently'})
    # Physical GiST layout can differ because PostgreSQL randomizes insertion ties.
    # Resume validates the recorded restored representation rather than demanding
    # the unavailable old physical layout.
    # Preserve original setup receipt too, after the restoration receipt is durable.
    shutil.copy2(DEBUG/'original_attempts/postgis_reference.done',s.marker(D,'postgis_reference'))

def retry_attempt(runtime):
    """New generation after a failed attempt; resume an interrupted current one.

    Historical .done/finished receipts remain evidence, never skip authority.
    A persisted move plan also makes interruption during supersession resumable.
    """
    pointer=WORK/'retry_state'/(runtime+'.json')
    state=s.read_json(pointer) if pointer.exists() else {}
    cp=s.marker(D,runtime+'_method')
    if state.get('phase')=='superseding':
        pass  # Finish the exact previously persisted move plan first.
    elif state.get('phase')=='running' and not cp.exists() and not (Path(state['target'])/'finished.json').exists():
        return Path(state['target'])  # No terminal outcome: resume this generation's phases.
    else:
        attempt_id=time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex
        target=DEBUG/'retry_attempts'/runtime/attempt_id
        sources=set((s.OUT/'checkpoints'/D).glob(runtime+'*.done'))
        sources.update((s.OUT/'00_environment').glob(D+'_'+runtime+'_*'))
        sources.update((s.OUT/'04_correctness'/D).glob(runtime+'*'))
        sources.add(s.OUT/'03_build'/D/(runtime+'.json'))
        sources.add(s.OUT/'05_performance'/D/runtime)
        if runtime=='qmap_uniform_qmf': sources.add(s.OUT/'06_qmf_diagnostics'/D)
        moves=[]
        for p in sorted(sources):
            if p.exists() or p.is_symlink():
                moves.append({'source':str(p),'target':str(target/'prior_results'/p.relative_to(s.OUT))})
        runtime_sources=[o.ACTIVE/D/'methods'/runtime,o.ACTIVE/D/'indexes'/(runtime+'.idx')]
        runtime_sources+=list((s.RUN/'logs').glob(D+'_'+runtime+'_*'))
        for p in runtime_sources:
            if p.exists() or p.is_symlink():
                moves.append({'source':str(p),'target':str(WORK/'retry_history'/runtime/attempt_id/p.relative_to(s.RUN))})
        previous=s.read_json(cp) if cp.exists() else None
        legacy=DEBUG/'attempts'/runtime
        receipt={'at':time.time(),'attempt_id':attempt_id,'runtime':runtime,
                 'formal_build_timeout_s':run.PROTOCOL['timeouts_s']['build'],
                 'previous_result':previous,'previous_generation':state,
                 'superseded_legacy_receipts':{str(p):s.sha(p) for p in legacy.glob('*.json') if p.is_file()},
                 'phase_policy':'Fresh retry after failed terminal attempt; resume valid phases only within this generation',
                 'moves':moves}
        s.atomic_json(target/'superseded.json',receipt)
        state={'phase':'superseding','attempt_id':attempt_id,'target':str(target),'moves':moves}
        s.atomic_json(pointer,state)
    target=Path(state['target'])
    for move in state['moves']:
        source=Path(move['source']); dest=Path(move['target'])
        src_exists=source.exists() or source.is_symlink()
        dst_exists=dest.exists() or dest.is_symlink()
        if src_exists and not dst_exists:
            dest.parent.mkdir(parents=True,exist_ok=True)
            os.rename(source,dest)  # Same filesystem; retain original evidence bytes, never delete.
        elif src_exists or not dst_exists:
            raise RuntimeError('Ambiguous retry evidence supersession: '+str(source))
    s.atomic_json(target/'started.json',{'at':time.time(),'attempt_id':state['attempt_id'],
                                        'formal_build_timeout_s':run.PROTOCOL['timeouts_s']['build'],
                                        'runtime':runtime,'previous_evidence_preserved':True})
    s.atomic_json(pointer,{**state,'phase':'running'})
    return target

def attempt(runtime):
    decision=retry_decision(runtime)
    if decision!='RETRY_ELIGIBLE': return decision
    if runtime not in ORDER: raise RuntimeError('Method outside the GeoLife retry queue: '+runtime)
    clean_preflight(runtime)
    target=retry_attempt(runtime)
    row=s.read_json(s.OUT/'01_dataset_inventory'/(D+'.json'))
    display=next(name for name,r in s.METHODS if r==runtime)
    # Supersession may itself take time; recheck immediately before execution.
    clean_preflight(runtime)
    try:
        result=o.run_method(row,display,runtime)
        s.atomic_json(target/'finished.json',{'at':time.time(),'result':result,
            'scientifically_valid':report.valid_method(D,runtime)})
        pointer=WORK/'retry_state'/(runtime+'.json')
        s.atomic_json(pointer,{**s.read_json(pointer),'phase':'finished'})
    finally:
        # The next method's admission check must see no prior PostgreSQL/server state.
        stop_repair_postgres()
    verify_protected(); run.verify_source(); publish()
    return result

def foreground():
    WORK.mkdir(exist_ok=True)
    lock=(s.RUN/'campaign.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    configure()
    def interrupted(signum,frame): raise KeyboardInterrupt('Signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    try:
        run.verify_protocol(); run.verify_source(); protect_valid()
        queue=retry_queue()
        s.atomic_json(DEBUG/'retry_queue.json',{'at':time.time(),'queue':queue,
            'preserved':KEEP,'minimum_start_memavailable_bytes':RETRY_MIN_AVAILABLE})
        if queue:
            adopted=adopt_restoration_load()
            o.update(dataset=D,method='shared',phase='repair_preflight',status='RUNNING')
            if not adopted: clean_preflight()
            prepare_runtime()
            stop_repair_postgres()
            for runtime in queue: attempt(runtime)
        verify_protected(); run.verify_source(); publish()
        state=report.completion(D)
        s.atomic_json(DEBUG/'repair_result.json',{'at':time.time(),**state})
        o.update(status='COMPLETE' if state['scientifically_complete'] else 'REPAIR_INCOMPLETE',phase='repair_attempts_finished')
    except BaseException as e:
        o.update(status='INTERRUPTED',error=repr(e))
        s.atomic_json(DEBUG/'repair_interruption.json',{'at':time.time(),'error':repr(e)})
        raise
    finally:
        # Closing the repair server preserves both datasets' disk representations.
        stop_repair_postgres()

def start():
    if run.active(UNIT): print('Repair service already active'); return
    if run.active(run.UNIT): raise RuntimeError('Forward campaign must be paused before GeoLife repair')
    s.output_dirs(); DEBUG.mkdir(exist_ok=True)
    run.verify_protocol(); run.verify_source(); protect_valid()
    if 'LoadState=loaded' in o.ctl('show',UNIT,'-p','LoadState').stdout:
        if str(Path(__file__).resolve()) not in o.ctl('show',UNIT,'-p','ExecStart').stdout:
            raise RuntimeError('Existing repair unit has an unexpected command')
        # Starting a failed unit is supported directly. Resetting it first can
        # garbage-collect a transient unit between inspection and start.
        result=o.ctl('start',UNIT)
        if result.returncode==0: return
        if result.returncode!=5: raise RuntimeError(result.stderr)
    subprocess.run(['systemd-run','--user','--unit',UNIT,'--property=TimeoutStopSec=60',
       '--property=StandardOutput=append:'+str(DEBUG/'repair.log'),'--property=StandardError=append:'+str(DEBUG/'repair.log'),
       '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=OPENBLAS_NUM_THREADS=1','--setenv=OMP_NUM_THREADS=1',
       sys.executable,'-B',str(Path(__file__).resolve()),'--foreground'],check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--foreground',action='store_true'); args=p.parse_args()
    foreground() if args.foreground else start()
