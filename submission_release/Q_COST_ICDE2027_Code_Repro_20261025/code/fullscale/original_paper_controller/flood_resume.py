"""Flood-only correctness resume with immutable original build/result evidence."""
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
from paper_protocol import DATASETS, HOST_EMERGENCY_RESERVE, MEMORY_HIGH, MEMORY_MAX, MEMORY_SWAP_MAX

DATASET=DATASETS[0]
FORMAL=s.OUT
RUNTIME=s.RUN
AUDIT=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
ATTEMPTS=s.ROOT/'results/flood_correctness_memfix_phase2_20260915/attempts'
UNIT='qmf-paper-flood-correctness-20260915'

@contextlib.contextmanager
def preflight_stage(name):
    started=time.monotonic()
    print(f'{time.strftime("%Y-%m-%dT%H:%M:%S%z")} PREFLIGHT_STAGE = {name}',flush=True)
    try:
        yield
    except BaseException as exc:
        print(f'{time.strftime("%Y-%m-%dT%H:%M:%S%z")} PREFLIGHT_FAILED = {name} '
              f'elapsed_s={time.monotonic()-started:.6f} exception={exc!r}',file=sys.stderr,flush=True)
        traceback.print_exc(file=sys.stderr)
        raise

def runtime_path(target):
    # UNIX socket paths must remain below sockaddr_un's 108-byte limit.
    return Path('/var/tmp')/('qmf-flood-p2-'+target.name[-16:])

def validate_build():
    checkpoint=FORMAL/'checkpoints'/DATASET/'flood_build_r0.done'
    record=s.read_json(checkpoint); values=record['payload']
    index=Path(values['index_path']); build_csv=index.parent/'build.csv'
    with build_csv.open() as f: build=next(csv.DictReader(f))
    if values['build_seconds'] != int(build['total_ns'])/1e9:
        raise RuntimeError('Flood Build time differs from protected build.csv')
    if values['serialized_bytes']!=index.stat().st_size or s.sha(index)!=values['index_sha256']:
        raise RuntimeError('Flood Build artifact SHA mismatch; rebuilding is forbidden')
    for entry in record['files']:
        p=Path(entry['path'])
        if p.stat().st_size!=entry['bytes'] or s.sha(p)!=entry['sha256']:
            raise RuntimeError('Flood Build checkpoint is invalid; rebuilding is forbidden')
    return record

def verify_gate(require_safe=True):
    # A new, separately audited controller receipt preserves the Phase 2 receipt.
    amendment=AUDIT/'acceptance_resume_preflight_20260915.json'
    gate=s.read_json(amendment if amendment.exists() else AUDIT/'acceptance.json')
    if require_safe and gate.get('safe_for_full_retry') is not True:
        raise RuntimeError('Flood correctness equivalence/profile gate not accepted')
    if gate.get('equivalence_pass') is not True:
        raise RuntimeError('Flood equivalence evidence missing')
    if require_safe and not 0 < gate['predicted_181m_peak_mib'] <= 18*1024:
        raise RuntimeError('Flood predicted memory exceeds predeclared retry threshold')
    import run
    if not run.passing_test_xml(Path(gate['tests_path'])):
        raise RuntimeError('Flood regression tests not passing')
    if gate['memory_policy']!=[MEMORY_HIGH,MEMORY_MAX,MEMORY_SWAP_MAX,HOST_EMERGENCY_RESERVE]:
        raise RuntimeError('Frozen memory policy changed')
    for key in ('source_files','runtime_files','evidence_files'):
        for path,digest in gate[key].items():
            if s.sha(path)!=digest: raise RuntimeError('Flood acceptance SHA changed: '+path)
    with preflight_stage('validate_build'):
        validate_build()
    return gate

def protected_files():
    files=sorted(p for p in FORMAL.rglob('*') if p.is_file())
    record=validate_build(); index=Path(record['payload']['index_path'])
    files += [index,index.parent/'build.csv']
    return {str(p):{'bytes':p.stat().st_size,'sha256':s.sha(p)} for p in files}

def verify_protected(expected):
    current=protected_files()
    if current!=expected: raise RuntimeError('ORIGINAL_RESULTS_PRESERVED = NO; refuse continuation')

def new_attempt():
    """Copy only validated phase receipts; originals never move or change."""
    record=validate_build()
    target=ATTEMPTS/(time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex)
    target.mkdir(parents=True)
    previous=sorted(p for p in ATTEMPTS.iterdir() if p.is_dir() and p!=target)
    for directory in ('01_dataset_inventory','02_queries'):
        source=FORMAL/directory
        if directory=='02_queries':
            shutil.copytree(source/DATASET,target/directory/DATASET)
        else:
            (target/directory).mkdir()
            shutil.copy2(source/(DATASET+'.json'),target/directory/(DATASET+'.json'))
    cp=target/'checkpoints'/DATASET;cp.mkdir(parents=True)
    shutil.copy2(FORMAL/'checkpoints'/DATASET/'flood_build_r0.done',cp/'flood_build_r0.done')
    # A failed method receipt does not invalidate an exact correctness phase or
    # a completed timing repetition. Clone its new-generation artifacts only.
    if previous:
        prior=previous[-1]
        for directory in ('04_correctness','05_performance'):
            if (prior/directory).exists():shutil.copytree(prior/directory,target/directory)
        for path in (prior/'checkpoints'/DATASET).glob('flood_*.done'):
            if path.name in ('flood_build_r0.done','flood_method.done'):continue
            value=s.read_json(path)
            if all(Path(e['path']).is_file() and s.sha(e['path'])==e['sha256'] for e in value['files']):
                shutil.copy2(path,cp/path.name)
        # The phase engine compresses completed repetitions on interruption.
        # Restore only new-attempt working copies for its existing finalizer;
        # retain the prior CSV/ZST and checkpoint bytes without modification.
        perf=target/'05_performance'/DATASET/'flood'
        if not (perf/'query_latency_raw.csv.zst').exists():
            for compressed in perf.glob('latency.r*.csv.zst'):
                raw=compressed.with_suffix('')
                if not raw.exists():
                    with raw.open('xb') as handle:
                        subprocess.run(['zstd','-q','-dc',str(compressed)],stdout=handle,check=True)
    s.atomic_json(target/'provenance.json',{'protected_build_checkpoint':str(FORMAL/'checkpoints'/DATASET/'flood_build_r0.done'),
        'build_sha256':record['payload']['index_sha256'],'build_seconds':record['payload']['build_seconds'],
        'previous_attempt':str(previous[-1]) if previous else None,'method':'flood','resume_phase':'correctness',
        'old_results_read_only':True})
    return target

@contextlib.contextmanager
def isolated_output(target):
    """Reuse the existing scientific phase engine, redirect every output path."""
    import repair_geolife
    runtime=runtime_path(target);common=runtime/'common'
    common.mkdir(parents=True)
    # Attempt evidence lives on exFAT, which cannot store symbolic links.
    # Only the actual ext4 runtime uses symlinks; no consumer needs a backlink.
    with (target/'runtime_path.json').open('x') as handle:
        json.dump({'runtime_path':str(runtime)},handle)
        handle.write('\n')
    (common/'pg_data').symlink_to(RUNTIME/'geolife_repair/common/pg_data',target_is_directory=True)
    (common/'pg_socket').mkdir()
    (runtime/'qmf_postgres_full').symlink_to(AUDIT/'qmf_postgres_full')
    active=runtime/'active';(active/DATASET).mkdir(parents=True)
    changes=[(s,'OUT',target),(s,'RUN',runtime),(o,'OUT',target),(o,'RUN',runtime),
             (o,'COMMON',common),(o,'ACTIVE',active),(o,'STATE',runtime/'status.json'),
             (repair_geolife,'DEBUG',target/'debug')]
    old=[(m,k,getattr(m,k)) for m,k,_ in changes]
    env=dict(o.ENV); original_query=o.query_command; original_build=o.build_one
    def forbidden(*args,**kwargs):raise RuntimeError('Flood Build reexecution forbidden')
    def query(*args,**kwargs):
        command=original_query(*args,**kwargs)
        command+=['--flood-session-setup',str(AUDIT/'session_setup.sql')]
        if args[2]=='correctness':command+=['--memory-trace',str(target/'FLOOD_CORRECTNESS_MEMORY_TRACE.csv')]
        return command
    try:
        for m,k,v in changes:setattr(m,k,v)
        o.ENV['PGHOST']=str(common/'pg_socket')
        o.build_one=forbidden;o.query_command=query
        s.output_dirs()
        yield
    finally:
        o.build_one=original_build;o.query_command=original_query
        o.ENV.clear();o.ENV.update(env)
        for m,k,v in old:setattr(m,k,v)

def perform(target):
    with contextlib.ExitStack() as stack:
        with preflight_stage('runtime_setup'):
            stack.enter_context(isolated_output(target))
        row=s.read_json(s.OUT/'01_dataset_inventory'/(DATASET+'.json'))
        o.update(dataset=DATASET,method='Flood',phase='correctness')
        with preflight_stage('correctness'):
            result=o.run_method(row,'Flood','flood')
        if result['Status']=='PASS' and not report.valid_method(DATASET,'flood'):
            raise RuntimeError('Flood result did not pass the existing scientific validator')
        return result

def foreground():
    import diagnose
    import repair_geolife
    with preflight_stage('verify_gate'):
        gate=verify_gate()
    with (RUNTIME/'campaign.lock').open('a') as lock:
        with preflight_stage('lock'):
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # The SQL server and workers remain inside the existing shared budget.
        while True:
            with preflight_stage('ownership'):
                state=diagnose.ownership(o.SLICE)
            with preflight_stage('stale_processes'):
                if repair_geolife.stale_processes(state):raise RuntimeError('Stale benchmark process; refuse retry')
            with preflight_stage('cgroup_policy'):
                o.cgroup_policy.validate(state['parent'])
            required=int(gate['predicted_181m_peak_mib']*1024**2)+HOST_EMERGENCY_RESERVE
            if state['host_meminfo']['MemAvailable']>=required:break
            with preflight_stage('memory_wait'):
                print('Waiting for predicted Flood working set plus unchanged host reserve',flush=True)
                time.sleep(10)
        with preflight_stage('protected_files'):
            before=protected_files()
        with preflight_stage('latest_pass_attempt'):
            completed=latest_pass_attempt()
        if completed is not None:
            report.publish_flood_attempt(FORMAL,completed,DATASET)
            return
        with preflight_stage('new_attempt'):
            target=new_attempt()
        s.atomic_json(target/'original_files.json',before)
        def interrupted(signum,frame):raise KeyboardInterrupt('Signal '+str(signum))
        signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
        try:
            result=perform(target)
        finally:
            # Only our dedicated PostgreSQL may be stopped; never touch another
            # controller/server. Existing build and original logs are preserved.
            command=o.ctl('show',o.PGUNIT,'-p','ExecStart').stdout
            if str(runtime_path(target)/'common/pg_data') in command:o.ctl('stop',o.PGUNIT,check=True)
            verify_protected(before)
        s.atomic_json(target/'completed.json',result)
        if result['Status']=='PASS':report.publish_flood_attempt(FORMAL,target,DATASET)
        print(json.dumps({'attempt':str(target),'result':result},indent=2),flush=True)

def start():
    if report.valid_method(DATASET,'flood'):
        print('Flood is already scientifically PASS; no phases scheduled');return
    verify_gate()
    if o.props(UNIT).get('ActiveState') in ('active','activating','deactivating'):
        print('Flood correctness service already active');return
    # --collect prevents a previously selected service command from being reused.
    ATTEMPTS.mkdir(parents=True,exist_ok=True)
    log=ATTEMPTS/(time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex+'.log')
    print('FLOOD_RESUME_LOG = '+str(log),flush=True)
    subprocess.run(['systemd-run','--user','--collect','--unit='+UNIT,
        '--property=TimeoutStopSec=60','--property=StandardOutput=append:'+str(log),
        '--property=StandardError=append:'+str(log),'--setenv=PYTHONDONTWRITEBYTECODE=1',
        '--setenv=OPENBLAS_NUM_THREADS=1','--setenv=OMP_NUM_THREADS=1',
        sys.executable,'-B',str(Path(__file__).resolve()),'--foreground'],check=True)

def latest_pass_attempt():
    if not ATTEMPTS.exists():return None
    previous=s.OUT
    try:
        for path in sorted(ATTEMPTS.iterdir(),reverse=True):
            if not path.is_dir():continue
            s.OUT=path
            if report.valid_method(DATASET,'flood'):return path
    finally:s.OUT=previous
    return None

if __name__=='__main__':
    if sys.argv[1:]!=['--foreground']:raise SystemExit('Use scripts/run_paper_benchmark.sh --repair GeoLife --method Flood')
    foreground()
