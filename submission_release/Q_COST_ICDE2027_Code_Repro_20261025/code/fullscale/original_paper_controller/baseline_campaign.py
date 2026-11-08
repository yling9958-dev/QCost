"""Bounded sequential baseline attempts; immutable QMF/PASS evidence.

This controller calls the existing formal phase engine. It owns only new
generations under the original result root and an ext4 scratch runtime.
"""
import contextlib
import csv
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid

import support as s
import orchestrate as o
import report
import qmf_only as q
import run
from paper_protocol import DATASET_SPECS, DATASETS, PROTOCOL, HOST_EMERGENCY_RESERVE

FORMAL=s.OUT
ROOT=FORMAL/'baseline_campaign_20260920'
AUDIT=Path('/var/tmp/qmf-baselines-20260920')
RUNTIME=Path('/var/tmp/qmf-bline')
ORIGINAL_RUNTIME=s.RUN
RECEIPT=AUDIT/'acceptance.json'
UNIT='qmf-paper-baselines-20260920'
ORDER=('postgis_gist','lisa','tsunami','lmsfc','bmtree','flood','rtree')
LABELS={key:label for (_,key),label in zip(s.METHODS,report.DISPLAY)}
DISPLAY={key:name for name,key in s.METHODS}
FLOOD=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
HARD_FAILURES={'CORRECTNESS_FAILED','OOM_KILLED','CGROUP_MEMORY_MAX','SWAP_INVALID','TIMEOUT',
    'ALGORITHM_ERROR','MODEL_INCOMPATIBLE','PERSISTENT_TIMEOUT','UNSUPPORTED_PERSISTENCE','UNRECOVERABLE_BUILD_FAILURE'}
VIEW_FIELDS=['Dataset','Method','Points',*s.METRICS,'Correctness','Status','FailureReason']


def verify_receipt():
    value=s.read_json(RECEIPT)
    if value['protocol']!=PROTOCOL or not run.passing_test_xml(Path(value['tests_path'])):
        raise RuntimeError('Frozen baseline campaign protocol/tests invalid')
    for key in ('source_files','runtime_files','evidence_files'):
        for path,digest in value[key].items():
            if s.sha(path)!=digest:raise RuntimeError('Frozen acceptance SHA mismatch: '+path)
    return value


def preserve_originals():
    for name in ('original_formal.json','flood_build.json'):
        for path,entry in s.read_json(AUDIT/name).items():
            p=Path(path)
            if not p.is_file() or p.stat().st_size!=entry['bytes'] or s.sha(p)!=entry['sha256']:
                raise RuntimeError('ORIGINAL_RESULTS_SHA_CHANGED: '+path)


def initial_results():return s.read_json(AUDIT/'initial_results.json')
def pair_root(d,m):return ROOT/m/d
def attempts(d,m):return sorted(pair_root(d,m).glob('attempt-*'))


def historical_failure(d,m):
    return any(r['dataset']==d and r['method']==m and not r['valid'] and
        r['result'].get('Status') not in ('NOT_RUN','INCOMPLETE',None)
        for r in initial_results())


def attempt_budget(d,m):return 1 if historical_failure(d,m) else 2


def valid_root(d,m):
    # Initial scientific PASS was independently validated and is protected by
    # the original SHA manifest. Never ask any runner to finalize it again.
    for r in initial_results():
        if (r['dataset'],r['method'],r['valid'])==(d,m,True):return Path(r['root'])
    for path in attempts(d,m):
        with q.result_context(path):
            if report.valid_method(d,m):return path
    return None


def terminal(d,m):
    p=pair_root(d,m)/'terminal.json'
    return s.read_json(p) if p.exists() else None


def queue():
    return [(d,m) for m in ORDER for d in DATASETS if not valid_root(d,m) and not terminal(d,m)]


def disposition(status,attempt_count):
    if status=='PASS':return 'PASS'
    if status in HARD_FAILURES:return 'FAILED_FINAL'
    return 'SKIPPED_AFTER_REPEATED_FAILURE' if attempt_count>=2 else 'RETRY'


def mark_terminal(d,m,status,reason):
    path=pair_root(d,m)/'terminal.json';path.parent.mkdir(parents=True,exist_ok=True)
    # Terminal evidence is append-only; resume never silently reopens a pair.
    with path.open('x') as f:json.dump({'Status':status,'FailureReason':reason,'at':time.time()},f,indent=2)


def clone_receipt(prior,target,d,phase,required=False):
    with q.result_context(prior):
        cp=s.marker(d,phase)
        if not cp.exists():
            if required:raise RuntimeError('UNRECOVERABLE_BUILD_FAILURE: protected Build receipt missing')
            return False
        if not s.valid(d,phase):raise RuntimeError('UNRECOVERABLE_BUILD_FAILURE: completed phase artifact missing; refuse rebuild '+phase)
        shutil.copy2(cp,target/'checkpoints'/d/cp.name)
    return True


def new_attempt(d,m):
    if m not in ORDER:raise RuntimeError('QMF execution forbidden in baseline campaign')
    if valid_root(d,m):raise RuntimeError('PASS reexecution forbidden')
    previous=attempts(d,m)
    if len(previous)>=attempt_budget(d,m):raise RuntimeError('Attempt budget exhausted')
    target=pair_root(d,m)/('attempt-'+time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    cp=target/'checkpoints'/d;cp.mkdir(parents=True)
    (target/'01_dataset_inventory').mkdir()
    shutil.copy2(FORMAL/'01_dataset_inventory'/(d+'.json'),target/'01_dataset_inventory'/(d+'.json'))
    shutil.copytree(FORMAL/'02_queries'/d,target/'02_queries'/d)
    shutil.copy2(FORMAL/'checkpoints'/d/'queries.done',cp/'queries.done')
    prior=previous[-1] if previous else FORMAL
    if not previous and m=='flood' and d==DATASETS[0]:
        # A newer isolated Flood attempt may contain completed correctness/timing.
        import flood_resume
        possible=sorted(p for p in flood_resume.ATTEMPTS.glob('*') if p.is_dir())
        if possible:prior=possible[-1]
    s.atomic_json(target/'provenance.json',{'dataset':d,'method':m,'prior':str(prior),
        'attempt_number':len(previous)+1,'historical_failure_counts_as_normal_attempt':historical_failure(d,m),
        'new_attempt_budget':attempt_budget(d,m),'normal_plus_one_repair_max':2,'QMF_execution_forbidden':True,
        'runtime':str(RUNTIME/'attempts'/target.name)})
    for sub in ('04_correctness','05_performance','03_build'):
        source=prior/sub/d
        if sub=='05_performance':
            if (source/m).exists():shutil.copytree(source/m,target/sub/d/m)
        elif source.exists():
            for p in source.glob(m+'*'):
                if p.is_file():
                    (target/sub/d).mkdir(parents=True,exist_ok=True);shutil.copy2(p,target/sub/d/p.name)
    has_build=clone_receipt(prior,target,d,m+'_build_r0')
    if d==DATASETS[0] and m=='flood' and not has_build:
        clone_receipt(FORMAL,target,d,m+'_build_r0',required=True)
    for phase in [m+'_correctness',*[m+f'_timing_r{i}' for i in range(1,6)]]:
        clone_receipt(prior,target,d,phase)
    perf=target/'05_performance'/d/m
    if not (perf/'query_latency_raw.csv.zst').exists():
        for compressed in perf.glob('latency.r*.csv.zst'):
            raw=compressed.with_suffix('')
            if not raw.exists():
                with raw.open('xb') as f:subprocess.run(['zstd','-q','-dc',str(compressed)],stdout=f,check=True)
    return target


@contextlib.contextmanager
def execution_context(d,m,target):
    if m not in ORDER:raise RuntimeError('QMF execution forbidden')
    work=RUNTIME/'attempts'/target.name;common=RUNTIME/'common'
    common.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    for name in ('build','baselines','extension','learnedbench-patched','repro-source','bmtree-official'):
        link=common/name
        if not link.exists():link.symlink_to(ORIGINAL_RUNTIME/'common'/name,target_is_directory=True)
    binary=work/'qmf_postgres_full'
    if not binary.exists():binary.symlink_to((FLOOD if m=='flood' else ORIGINAL_RUNTIME)/'qmf_postgres_full')
    active=work/'active';active.mkdir(exist_ok=True)
    changes=[(s,'OUT',target),(s,'RUN',work),(o,'OUT',target),(o,'RUN',work),(o,'COMMON',common),
             (o,'ACTIVE',active),(o,'STATE',RUNTIME/'status.json')]
    original=[(mod,key,getattr(mod,key)) for mod,key,_ in changes]
    saved={name:getattr(o,name) for name in ('worker','build_one','cleanup_method','query_command','update')}
    env=dict(o.ENV)
    def forbidden_worker(*args,**kwargs):raise RuntimeError('Frozen normalized/query assets required; no QMF or conversion workers allowed')
    def build(row,method,rep):
        if method!=m or method not in ORDER:raise RuntimeError('Unexpected method build')
        if method=='flood' and d==DATASETS[0]:raise RuntimeError('Protected GeoLife Flood Build reexecution forbidden')
        return saved['build_one'](row,method,rep)
    def query(*args,**kwargs):
        cmd=saved['query_command'](*args,**kwargs)
        if m=='flood':cmd+=['--flood-session-setup',str(FLOOD/'session_setup.sql')]
        return cmd
    last_phase=[None]
    def update(**kwargs):
        # Reference GiST preparation is infrastructure for the selected method,
        # not a concurrently scheduled PostGIS result.
        kwargs['method']=DISPLAY[m]
        saved['update'](**kwargs)
        phase=o.CURRENT.get('phase')
        if phase!=last_phase[0]:
            last_phase[0]=phase
            refresh_safely(print_tables=True)
    try:
        for mod,key,value in changes:setattr(mod,key,value)
        o.ENV.update(PGHOST=str(common/'pg_socket'),QMF_RUNTIME=str(common),
            QMAP_BUILD_ROOT=str(common/'build'),QMAP_BASELINE_WORK=str(common/'baselines'))
        o.worker=forbidden_worker;o.build_one=build;o.cleanup_method=lambda *_:None;o.query_command=query;o.update=update
        s.output_dirs();yield
    finally:
        for name,value in saved.items():setattr(o,name,value)
        o.ENV.clear();o.ENV.update(env)
        for mod,key,value in original:setattr(mod,key,value)


def prepare(row):
    d=row['dataset_id'];work=o.ACTIVE/d;work.mkdir(parents=True,exist_ok=True)
    cached=s.ROOT/'data_cache/full'/d
    meta=s.read_json(cached/'normalized_manifest.json');point=cached/'points_normalized.csv'
    if meta['points']!=row['record_count'] or point.stat().st_size!=meta['bytes'] or s.sha(point)!=meta['sha256']:
        raise RuntimeError('Frozen normalized dataset SHA mismatch')
    (work/'points_normalized.csv').symlink_to(point)
    s.atomic_json(work/'normalized.json',meta)
    s.done(d,'normalize',meta,[point,cached/'normalized_manifest.json'])
    run.query_gate(row)
    q.setup_query_infrastructure()
    loaded=RUNTIME/'prepared.json'
    if loaded.exists():
        value=s.read_json(loaded)
        if value.get('ready') and value['dataset']==d and value['raw_sha256']==row['sha256']:
            prior=Path(value['result_root'])
            for phase in ('load','postgis_reference'):clone_receipt(prior,s.OUT,d,phase)
        else:
            # Invalidate the runtime identity before changing any SQL objects.
            # A failed partial load must never masquerade as the prior dataset.
            s.atomic_json(loaded,{'dataset':d,'ready':False,'raw_sha256':row['sha256']})
            o.sql('DROP VIEW IF EXISTS evaluation; DROP TABLE IF EXISTS points CASCADE; CHECKPOINT;',d+'_release_previous',1800)
    o.prepare_dataset(row)
    s.atomic_json(loaded,{'dataset':d,'ready':True,'raw_sha256':row['sha256'],'result_root':str(s.OUT)})


def stop_owned_postgres():
    command=o.ctl('show',o.PGUNIT,'-p','ExecStart').stdout
    if str(RUNTIME/'common/pg_data') in command:o.ctl('stop',o.PGUNIT,check=True)


def guard_clean():
    import diagnose,repair_geolife
    current=diagnose.ownership(o.SLICE)
    stale=repair_geolife.stale_processes(current)
    if stale:raise RuntimeError('ACTIVE_EXPERIMENT: '+repr(stale))
    o.cgroup_policy.configure(o.SLICE);o.cgroup_policy.validate(o.cgroup_policy.snapshot(o.SLICE))
    if current['host_meminfo']['MemAvailable']<HOST_EMERGENCY_RESERVE:
        raise o.Blocked('HOST_SAFETY_STOP','Preflight host memory below unchanged reserve')


def park_new_runtime_indexes(target):
    """Persist only this controller's new index bytes, retaining runtime paths.

    Copies are verified before the disposable ext4 copy is replaced by a symlink.
    No original index (especially GeoLife Flood) can enter this path.
    """
    work=RUNTIME/'attempts'/target.name
    for p in sorted((work/'active').glob('*/methods/*/rep0/*')):
        if not p.is_file() or p.is_symlink() or p.suffix not in ('.idx','.model'):continue
        output=target/'persistent_indexes'/p.name;output.parent.mkdir(exist_ok=True)
        digest=s.sha(p)
        if not output.exists():shutil.copy2(p,output)
        if s.sha(output)!=digest:raise RuntimeError('New runtime index copy SHA mismatch')
        # Only newly owned, verified duplicate bytes are removed; the same exact
        # pathname still resolves for every existing phase receipt.
        p.unlink();p.symlink_to(output)


def attempt(d,m):
    target=None
    before_attempts=set(attempts(d,m))
    try:
        verify_receipt();preserve_originals();guard_clean()
        target=new_attempt(d,m)
        with execution_context(d,m,target):
            o.update(dataset=d,method=DISPLAY[m],phase='preflight',status='RUNNING',attempt=str(target))
            row=s.read_json(s.OUT/'01_dataset_inventory'/(d+'.json'))
            if s.sha(row['source_path'])!=row['sha256']:raise RuntimeError('Frozen raw dataset SHA mismatch')
            row['mtime_ns']=Path(row['source_path']).stat().st_mtime_ns
            s.atomic_json(s.OUT/'01_dataset_inventory'/(d+'.json'),row)
            prepare(row)
            measured=o.run_method(row,DISPLAY[m],m)
            if measured['Status']=='PASS' and not report.valid_method(d,m):
                raise RuntimeError('PASS lacks complete scientific evidence')
        return measured,target
    except (KeyboardInterrupt,SystemExit):raise
    except Exception as exc:
        if any(w in str(exc) for w in ('SHA','Frozen','ACTIVE_EXPERIMENT','CGROUP_FIX','ORIGINAL_RESULTS')):raise
        status=exc.status if isinstance(exc,o.Blocked) else (
            'UNRECOVERABLE_BUILD_FAILURE' if 'UNRECOVERABLE_BUILD_FAILURE' in str(exc) else 'INFRASTRUCTURE_FAILED')
        measured={'Status':status,'reason':repr(exc),'failed_phase':o.CURRENT.get('phase')}
        if target is None:
            created=sorted(set(attempts(d,m))-before_attempts)
            if created:target=created[-1]
            else:
                pair_root(d,m).mkdir(parents=True,exist_ok=True)
                target=pair_root(d,m)/('attempt-'+time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]);target.mkdir()
        s.atomic_json(target/'exception.json',{'result':measured,'traceback':traceback.format_exc(),'at':time.time()})
        return measured,target
    finally:
        if target is not None:
            stop_owned_postgres()
            park_new_runtime_indexes(target)
        preserve_originals()


def measured_result(d,m):
    root=valid_root(d,m)
    if root is None:return None
    for row in initial_results():
        if (row['dataset'],row['method'],row['valid'])==(d,m,True):return row['result']
    return s.read_json(root/'checkpoints'/d/(m+'_method.done'))['payload']


def current_state():
    path=RUNTIME/'status.json';state=s.read_json(path) if path.exists() else {}
    active=run.active(UNIT)
    if not active:return {'status':'COMPLETE' if (RUNTIME/'complete.json').exists() else 'IDLE','historical_snapshot':state}
    parent=o.cgroup_policy.snapshot(o.SLICE)
    info=o.props(state.get('active_unit','')) if state.get('active_unit') else {}
    state.update(parent_current=parent,controller_active=active,worker_active=info.get('ActiveState')=='active')
    d=state.get('dataset');m=dict(s.METHODS).get(state.get('method'));folder=Path(state['attempt']) if state.get('attempt') else None
    if d and m and folder:
        corr=folder/'04_correctness'/d/(m+'.csv')
        state['correctness_progress']=sum(1 for _ in corr.open())-1 if corr.exists() else 0
        state['warmup_progress']='completed before latency output; no in-query counter in frozen harness'
        progress=[]
        for rep in range(5):
            for suffix in ('.csv','.csv.part'):
                p=folder/'05_performance'/d/m/f'latency.r{rep}{suffix}'
                if p.exists():progress.append({'repetition':rep+1,'queries':max(0,sum(1 for _ in p.open())-1)})
        state['timing_progress']=progress
    return state


def render(print_tables=False):
    state=current_state();all_rows=[];matrix=[];qrows=[];newest=[]
    active_pair=(state.get('dataset'),dict(s.METHODS).get(state.get('method'))) if state.get('controller_active') else None
    for display,m in s.METHODS:
        cells=[]
        for d,name,n,_ in DATASET_SPECS:
            r=measured_result(d,m);t=terminal(d,m)
            if r:status='PASS';reason=''
            elif active_pair==(d,m):status='RUNNING';reason=''
            elif t:status=t['Status'];reason=t['FailureReason']
            else:
                failed=next((v['result'] for v in initial_results() if (v['dataset'],v['method'])==(d,m)),{})
                status='FAILED' if failed.get('Status') not in ('NOT_RUN','INCOMPLETE',None) else 'NOT_RUN'
                reason=failed.get('reason','') if status=='FAILED' else ''
            row={'Dataset':name,'Method':LABELS[m],'Points':n,**{k:r.get(k) if r else None for k in s.METRICS},
                 'Correctness':r['Correctness'] if r else 'NOT_RUN','Status':status,'FailureReason':reason}
            all_rows.append(row)
            if m=='qmap_uniform_qmf':qrows.append(row)
            cells.append('SKIPPED' if status=='SKIPPED_AFTER_REPEATED_FAILURE' else 'FAILED' if status=='FAILED_FINAL' else status)
        matrix.append([LABELS[m],*cells,str(cells.count('PASS'))+'/4'])
    def table(headers,rows):
        return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('| '+' | '.join(report.fmt(v).replace('\n',' ') for v in row)+' |\n' for row in rows)
    qfields=['Dataset','Points',*s.METRICS,'Correctness','Status']
    qt=table(qfields,[[r[k] for k in qfields] for r in qrows]);mt=table(['Method','GeoLife','Gowalla','NYC Taxi','Skewed 2D','Valid'],matrix)
    lt=table(VIEW_FIELDS,[[r[k] for k in VIEW_FIELDS] for r in all_rows])
    todo=queue();count=sum(r['Status']=='PASS' for r in all_rows)
    text='# QMF-INDEX: 4 DATASETS × 7 METRICS\n\n'+qt+'\nQMF VALID = 4/4\n\n# BASELINE PROGRESS\n\n'+mt+f'\nVALID RESULTS = {count}/32\n\n# Formal measured results and explicit unavailable cells\n\n'+lt
    text+='\n# Current experiment\n\n```json\n'+json.dumps(state,indent=2)+'\n```\n'
    text+='\n# Skipped / failed\n\n'+table(['Dataset','Method','Status','Reason'],[[r['Dataset'],r['Method'],r['Status'],r['FailureReason']] for r in all_rows if r['Status'] in ('FAILED','FAILED_FINAL','SKIPPED_AFTER_REPEATED_FAILURE')])
    text+='\nNEXT = '+(str(todo[0]) if todo else 'NONE — terminal campaign')+'\n'
    s.atomic_csv(FORMAL/'ALL_METHODS_4_DATASETS_7_METRICS.csv',all_rows,VIEW_FIELDS)
    report.text(FORMAL/'BENCHMARK_PROGRESS.md',text)
    if print_tables:print(qt+'\n'+mt+f'\nVALID RESULTS = {count}/32\nNEXT = '+str(todo[0] if todo else None),flush=True)
    return all_rows


def refresh_safely(print_tables=False):
    try:return render(print_tables)
    except Exception:
        ROOT.mkdir(parents=True,exist_ok=True)
        with (ROOT/'reporting_errors.log').open('a') as f:f.write(time.strftime('%FT%T%z')+' REPORTING_FAILED\n'+traceback.format_exc())
        return None


def foreground():
    RUNTIME.mkdir(parents=True,exist_ok=True);ROOT.mkdir(parents=True,exist_ok=True)
    with (ORIGINAL_RUNTIME/'campaign.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        verify_receipt();preserve_originals();run.verify_protocol()
        def interrupted(signum,frame):raise KeyboardInterrupt('Controller interrupted '+str(signum))
        signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
        refresh_safely(True)
        for m in ORDER:
            for d in DATASETS:
                if valid_root(d,m):print(d+' '+m+' SKIP_VALID',flush=True);continue
                if terminal(d,m):continue
                if len(attempts(d,m))>=attempt_budget(d,m):
                    mark_terminal(d,m,'SKIPPED_AFTER_REPEATED_FAILURE','Normal plus one recovery budget exhausted, including historical/interrupted attempts');continue
                while len(attempts(d,m))<attempt_budget(d,m):
                    measured,target=attempt(d,m)
                    with (target/'attempt_outcome.json').open('x') as f:json.dump(measured,f,indent=2)
                    decision=disposition(measured['Status'],len(attempts(d,m))+int(historical_failure(d,m)))
                    if decision=='PASS':
                        print('NEW_RESULT_PASS\n'+json.dumps({'Dataset':d,'Method':LABELS[m],**measured},indent=2),flush=True)
                        preserve_originals();refresh_safely(True);break
                    reason=measured.get('reason','')
                    diagnosis={'status':measured['Status'],'reason':reason,'decision':decision,
                        'attempt_count':len(attempts(d,m)),'repair':'same frozen phase engine, clean worker/PG restart, valid completed phases only'}
                    s.atomic_json(target/'bounded_diagnosis.json',diagnosis)
                    print(json.dumps(diagnosis,indent=2),flush=True)
                    if decision!='RETRY':mark_terminal(d,m,decision,measured['Status']+': '+reason)
                    refresh_safely(True)
                    if decision!='RETRY':break
                    time.sleep(10)
        preserve_originals()
        if queue():raise RuntimeError('Baseline queue is not terminal')
        s.atomic_json(RUNTIME/'complete.json',{'at':time.time(),'all_pairs_terminal':True,'QMF_rerun':False})
        # Final reporting retries are independent of measurements; never rerun a
        # benchmark solely because a report failed.
        for retry in range(3):
            if refresh_safely(True) is not None:return
            time.sleep(10)
        raise RuntimeError('REPORTING_FAILED: terminal evidence preserved; regenerate reports only')


def start():
    verify_receipt();preserve_originals()
    if run.active(UNIT):render(True);return
    import diagnose,repair_geolife
    if repair_geolife.stale_processes(diagnose.ownership(o.SLICE)):raise RuntimeError('Existing benchmark worker; monitor only')
    ROOT.mkdir(parents=True,exist_ok=True)
    log=ROOT/('campaign-'+time.strftime('%Y%m%dT%H%M%S')+'.log')
    subprocess.run(['systemd-run','--user','--collect','--unit='+UNIT,'--property=TimeoutStopSec=60',
        '--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log),
        '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=OPENBLAS_NUM_THREADS=1','--setenv=OMP_NUM_THREADS=1',
        sys.executable,'-B',str(Path(__file__).with_name('run.py')),'--baselines','--foreground'],check=True)
    print('BASELINE_CAMPAIGN_LOG = '+str(log),flush=True)


def dispatch(action,dry_run=False):
    if dry_run:print(json.dumps({'order':ORDER,'remaining':queue(),'QMF_rerun':False,'max_attempts':2,'will_start_service':False},indent=2))
    elif action=='status':render(True)
    elif action=='foreground':foreground()
    else:start()
