"""QMF-only sequential campaign using the frozen paper phase engine.

All generations live below the one formal result root. Original evidence is
read-only; a new generation may clone valid phase checkpoints but never replace
the old generation. No baseline method is scheduled.
"""
import argparse
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
import uuid

import support as s
import orchestrate as o
import report
import worker
from paper_protocol import DATASET_SPECS, DATASETS, PROTOCOL, HOST_EMERGENCY_RESERVE

FORMAL=s.OUT
ORIGINAL_RUNTIME=s.RUN
ROOT=FORMAL/'qmf_only_20260919'
RUNTIME=Path('/var/tmp/qmf-qonly')
AUDIT=Path('/var/tmp/qmf-only-20260919')
RECEIPT=AUDIT/'acceptance_pg_version.json'
UNIT='qmf-paper-qmf-only-20260919'
METHOD='qmap_uniform_qmf'


def verify_receipt():
    import run
    value=s.read_json(RECEIPT)
    if not run.passing_test_xml(Path(value['tests_path'])):raise RuntimeError('QMF-only tests invalid')
    if value['protocol']!=PROTOCOL:raise RuntimeError('Frozen protocol changed')
    for kind in ('source_files','runtime_files','evidence_files'):
        for path,digest in value[kind].items():
            if s.sha(path)!=digest:raise RuntimeError('QMF-only SHA changed: '+path)
    return value


def preserve_originals():
    for path,entry in s.read_json(AUDIT/'before_formal.json').items():
        p=Path(path)
        if not p.is_file() or p.stat().st_size!=entry['bytes'] or s.sha(p)!=entry['sha256']:
            raise RuntimeError('OLD_RESULTS_SHA_CHANGED: '+path)


@contextlib.contextmanager
def result_context(path):
    previous=s.OUT
    try:
        s.OUT=path
        yield
    finally:s.OUT=previous


def valid_root(dataset):
    with result_context(FORMAL):
        if report.valid_method(dataset,METHOD):return FORMAL
    folder=ROOT/dataset
    for path in sorted(folder.glob('attempt-*')):
        with result_context(path):
            if report.valid_method(dataset,METHOD):return path
    return None


def plan():
    return [{'dataset':d,'method':METHOD,'action':'SKIP_VALID' if valid_root(d) else 'RUN_OR_RESUME'}
            for d in DATASETS]


def clean_admission():
    import diagnose
    import repair_geolife
    state=diagnose.ownership(o.SLICE)
    stale=repair_geolife.stale_processes(state)
    if stale:raise RuntimeError('Active benchmark/PG/worker: '+repr(stale))
    # Use the existing formal monitor's admission threshold. MemoryMax is a
    # shared ceiling, not a requirement that 24 GiB must initially be free.
    while state['host_meminfo']['MemAvailable']<HOST_EMERGENCY_RESERVE:
        print('Waiting for the frozen host emergency reserve before QMF',flush=True)
        time.sleep(10)
        state=diagnose.ownership(o.SLICE)
        if repair_geolife.stale_processes(state):raise RuntimeError('Benchmark appeared during admission wait')
    o.cgroup_policy.configure(o.SLICE)
    o.cgroup_policy.validate(o.cgroup_policy.snapshot(o.SLICE))
    return state


def new_attempt(dataset):
    if dataset==DATASETS[0]:raise RuntimeError('GeoLife QMF execution forbidden')
    if valid_root(dataset):raise RuntimeError('Scientifically PASS QMF execution forbidden')
    folder=ROOT/dataset
    previous=sorted(folder.glob('attempt-*'))
    target=folder/('attempt-'+time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    for sub in ('01_dataset_inventory','02_queries','checkpoints'):(target/sub/dataset).mkdir(parents=True,exist_ok=True)
    shutil.copy2(FORMAL/'01_dataset_inventory'/(dataset+'.json'),target/'01_dataset_inventory'/(dataset+'.json'))
    shutil.copytree(FORMAL/'02_queries'/dataset,target/'02_queries'/dataset,dirs_exist_ok=True)
    shutil.copy2(FORMAL/'checkpoints'/dataset/'queries.done',target/'checkpoints'/dataset/'queries.done')
    cp=target/'checkpoints'/dataset
    # Current formal failures remain untouched; their successful phase receipts
    # can be reused only if their referenced artifacts still verify exactly.
    prior=previous[-1] if previous else FORMAL
    for sub in ('04_correctness','05_performance','06_qmf_diagnostics'):
        source=prior/sub/dataset
        if source.exists():shutil.copytree(source,target/sub/dataset)
    with result_context(prior):
        for phase in [METHOD+'_build_r0',METHOD+'_correctness',*[METHOD+f'_timing_r{i}' for i in range(1,6)]]:
            if s.valid(dataset,phase):shutil.copy2(s.marker(dataset,phase),cp/(phase+'.done'))
            elif s.marker(dataset,phase).exists():
                raise RuntimeError('Checkpoint artifact missing/corrupt; no automatic expensive phase rerun: '+phase)
    # Per-repetition compression on an interruption is expanded only in this
    # new generation. Original raw/compressed timing and receipts stay intact.
    perf=target/'05_performance'/dataset/METHOD
    if not (perf/'query_latency_raw.csv.zst').exists():
        for compressed in perf.glob('latency.r*.csv.zst'):
            with compressed.with_suffix('').open('xb') as handle:
                subprocess.run(['zstd','-q','-dc',str(compressed)],stdout=handle,check=True)
    s.atomic_json(target/'provenance.json',{'dataset':dataset,'method':METHOD,'previous':str(prior),
        'runtime':str(RUNTIME/dataset),'original_evidence_immutable':True,'reason':'User-authorized QMF-only sequential campaign',
        'prior_failure':s.read_json(prior/'checkpoints'/dataset/(METHOD+'_method.done')) if (prior/'checkpoints'/dataset/(METHOD+'_method.done')).exists() else None})
    return target


@contextlib.contextmanager
def execution_context(dataset,target):
    import run
    if dataset not in DATASETS[1:]:raise RuntimeError('GeoLife QMF execution forbidden')
    runtime=RUNTIME/dataset
    common=runtime/'common';common.mkdir(parents=True,exist_ok=True)
    for name in ('build','baselines','extension','learnedbench-patched','repro-source'):
        p=common/name
        if not p.exists():p.symlink_to(ORIGINAL_RUNTIME/'common'/name,target_is_directory=True)
    binary=runtime/'qmf_postgres_full'
    if not binary.exists():binary.symlink_to(ORIGINAL_RUNTIME/'qmf_postgres_full')
    active=runtime/'active';active.mkdir(exist_ok=True)
    env=dict(o.ENV)
    changes=[(s,'OUT',target),(s,'RUN',runtime),(o,'OUT',target),(o,'RUN',runtime),
        (o,'COMMON',common),(o,'ACTIVE',active),(o,'STATE',RUNTIME/'status.json'),
        (worker,'OUT',target),(worker,'RUN',runtime)]
    original=[(module,key,getattr(module,key)) for module,key,_ in changes]
    original_worker=o.worker;original_cleanup=o.cleanup_method
    try:
        for module,key,value in changes:setattr(module,key,value)
        o.ENV.update(PGHOST=str(common/'pg_socket'),QMF_RUNTIME=str(common),QMAP_BUILD_ROOT=str(common/'build'),QMAP_BASELINE_WORK=str(common/'baselines'))
        def command(phase,dataset=None,rep=None):
            if phase not in ('normalize','qmf'):raise RuntimeError('Unexpected QMF-only worker phase: '+phase)
            return [sys.executable,'-B',str(Path(__file__).resolve()),'--worker',phase,'--dataset',dataset,'--target',str(target),'--rep',str(rep or 0)]
        o.worker=command
        # Keep the new index available for exact resume and SHA validation. Method
        # clients still exit normally; only owned runtime cleanup is postponed.
        o.cleanup_method=lambda *args:None
        s.output_dirs()
        yield
    finally:
        o.worker=original_worker;o.cleanup_method=original_cleanup
        o.ENV.clear();o.ENV.update(env)
        for module,key,value in original:setattr(module,key,value)


def verify_pg_version():
    # server_version may append a distributor string; the numeric setting
    # unambiguously identifies exactly 14.24 without accepting newer versions.
    if o.scalar('SHOW server_version_num')!='140024' or o.scalar('SELECT PostGIS_Lib_Version()')!='3.2.0':
        raise RuntimeError('Frozen PostgreSQL/PostGIS version mismatch')


def setup_query_infrastructure():
    # Shared exact-reference SQL infrastructure, not a baseline method run.
    pg=o.COMMON/'pg_data';(o.COMMON/'pg_socket').mkdir(exist_ok=True)
    if not (pg/'PG_VERSION').exists():
        o.monitor([o.PGBIN/'initdb','-D',pg,'--auth-local=trust','--auth-host=scram-sha-256',
                   '--encoding=UTF8','--locale=C.UTF-8'],'initdb',600)
        shutil.copy2(s.BASE/'config/postgres.conf.repro',pg/'repro.conf')
        with (pg/'postgresql.conf').open('a') as f:f.write("\ninclude = 'repro.conf'\n")
    o.ensure_pg()
    if o.scalar("SELECT count(*) FROM pg_database WHERE datname='qmf_full'",'postgres')=='0':
        subprocess.run(['createdb','qmf_full'],env={**o.ENV,'PGDATABASE':'postgres'},check=True)
    o.sql('CREATE EXTENSION IF NOT EXISTS postgis','postgis_extension',600)
    verify_pg_version()
    if o.scalar("SELECT count(*) FROM pg_proc WHERE proname='qmap_range_count'")=='0':
        sql=(s.BASE/'src/postgres/qmap_benchmark--1.0.sql').read_text().replace('MODULE_PATHNAME',str(o.COMMON/'extension/qmap_benchmark'))
        path=s.RUN/'install_extension.sql';path.write_text(sql)
        o.monitor(['psql','-X','-v','ON_ERROR_STOP=1','-f',path],'install_extension',600)


def prepare(row):
    import run
    run.normalized(row)
    setup_query_infrastructure()
    # The original setup creates a GiST for trusted SQL truth. No PostGIS method
    # correctness/timing/ranking is run or published in this campaign.
    o.prepare_dataset(row)


def result(dataset):
    root=valid_root(dataset)
    if not root:return None
    cp=root/'checkpoints'/dataset/(METHOD+'_method.done')
    build=root/'checkpoints'/dataset/(METHOD+'_build_r0.done')
    value=s.read_json(cp)['payload']
    return {**value,'Build_SHA256':s.sha(build),'Index_SHA256':s.read_json(build)['payload']['index_sha256'],'result_root':str(root)}


def publish_summary():
    rows=[];lines=['# QMF cross-dataset results','',
        'Three real-world datasets and one controlled skewed synthetic dataset. No baseline ranking is computed.',
        '', '| Dataset | Points | Build s | Size MiB | Mean ms | P95 ms | P99 ms | QPS | Peak MiB | Correctness | Status |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|']
    for d,name,points,_ in DATASET_SPECS:
        r=result(d)
        entry={'Dataset':name,'Points':points,**{k:r.get(k) if r else None for k in s.METRICS},
               'Correctness':r['Correctness'] if r else 'NOT_RUN','Status':r['Status'] if r else 'NOT_RUN'}
        rows.append(entry);lines.append('| '+' | '.join(report.fmt(v) for v in entry.values())+' |')
    count=sum(r['Status']=='PASS' for r in rows)
    lines+=['',f'QMF_DATASETS_VALID = {count}/4',
        'Build, query and memory values are measured by the unchanged formal phase engine; unavailable values are not estimated.',
        'A complete distribution comparison requires all four datasets to PASS. Skewed 2D is synthetic.',
        'NEXT_PHASE = '+('run baselines method-by-method; this campaign stops here' if count==4 else 'complete QMF or stop and debug any failure'), '']
    if count==4:
        for key in s.METRICS:
            low=min(rows,key=lambda r:r[key]);high=max(rows,key=lambda r:r[key])
            lines.append(f'{key}: minimum {low[key]:.9g} ({low["Dataset"]}); maximum {high[key]:.9g} ({high["Dataset"]}).')
        synthetic=rows[3]
        for key in ('Build_s','Mean_ms','P95_ms','P99_ms','PeakMemory_MiB'):
            real=sum(r[key] for r in rows[:3])/3
            lines.append(f'Skewed 2D {key} / real-world three-dataset arithmetic mean = {synthetic[key]/real:.6g}.')
        lines+=['All four frozen datasets completed exact correctness. These ratios describe observed distribution/scale differences; they do not establish a causal or asymptotic claim.',
                'No baseline was scheduled and no cross-method superiority or ranking is inferred.']
    # The old root QMF_CROSS_DATASET_SUMMARY.md remains an immutable historical
    # snapshot. The current QMF-only view is nested in the same formal root.
    s.atomic_csv(FORMAL/'QMF_INDEX_4_DATASETS_7_METRICS.csv',rows)
    report.text(ROOT/'QMF_CROSS_DATASET_SUMMARY.md','\n'.join(lines))
    return count


def stop_owned_postgres(dataset):
    expected=str(RUNTIME/dataset/'common/pg_data')
    command=o.ctl('show',o.PGUNIT,'-p','ExecStart').stdout
    if expected in command:o.ctl('stop',o.PGUNIT,check=True)


def cleanup_completed(dataset,target):
    if not valid_root(dataset):raise RuntimeError('No QMF PASS; cleanup forbidden')
    stop_owned_postgres(dataset)
    import diagnose,repair_geolife
    state=diagnose.ownership(o.SLICE)
    if repair_geolife.stale_processes(state):raise RuntimeError('Worker/PG/mmap remains at dataset boundary')
    if state['parent']['kernel'].get('memory.swap.current',0)!=0:raise RuntimeError('Experiment swap nonzero')
    # Only the new campaign's disposable PostgreSQL cluster is removed. Its
    # shared reference build receipt is retained; no historical runtime touched.
    pg=RUNTIME/dataset/'common/pg_data'
    if pg.exists() and not pg.is_symlink():shutil.rmtree(pg)
    s.atomic_json(target/'cleanup.json',{'postgres_stopped':True,'worker_stopped':True,'swap':0,
        'only_new_pg_runtime_removed':str(pg),'persistent_normalized_and_index_preserved':True})


def foreground():
    import run
    RUNTIME.mkdir(parents=True,exist_ok=True)
    with (ORIGINAL_RUNTIME/'campaign.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        verify_receipt();preserve_originals();run.verify_protocol()
        if valid_root(DATASETS[0])!=FORMAL:raise RuntimeError('GeoLife retained PASS gate failed')
        def interrupted(signum,frame):raise KeyboardInterrupt('Signal '+str(signum))
        signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
        try:
            publish_summary()
            for dataset in DATASETS[1:]:
                if valid_root(dataset):
                    completed=valid_root(dataset)
                    if completed!=FORMAL and not (completed/'cleanup.json').exists():
                        cleanup_completed(dataset,completed)
                    print(dataset+' QMF SKIP_VALID',flush=True);continue
                verify_receipt();preserve_originals();clean_admission()
                if shutil.disk_usage(RUNTIME).free<48*s.GIB:raise RuntimeError('Insufficient runtime disk: require 48GiB free')
                target=new_attempt(dataset)
                with execution_context(dataset,target):
                    o.update(dataset=dataset,method='QMF',phase='preparation',status='RUNNING',attempt=str(target))
                    row=s.read_json(s.OUT/'01_dataset_inventory'/(dataset+'.json'))
                    if s.sha(row['source_path'])!=row['sha256']:raise RuntimeError('RAW_SOURCE_MISMATCH')
                    row['mtime_ns']=Path(row['source_path']).stat().st_mtime_ns
                    s.atomic_json(s.OUT/'01_dataset_inventory'/(dataset+'.json'),row)
                    run.query_gate(row)
                    try:
                        prepare(row)
                        measured=o.run_method(row,'QMF',METHOD)
                    finally:stop_owned_postgres(dataset)
                preserve_originals()
                if measured['Status']!='PASS' or not valid_root(dataset):
                    raise RuntimeError(dataset+' QMF '+measured['Status']+': '+measured.get('reason',''))
                print(json.dumps({'Dataset':dataset,'Points':row['record_count'],**result(dataset),
                    'QMF_ALGORITHM_CHANGED':False,'QUERY_PROTOCOL_CHANGED':False,'MEMORY_POLICY_CHANGED':False},indent=2),flush=True)
                publish_summary();cleanup_completed(dataset,target);preserve_originals()
            if publish_summary()!=4:raise RuntimeError('Incomplete QMF campaign')
            s.atomic_json(RUNTIME/'exit.json',{'status':'COMPLETE','QMF_DATASETS_VALID':4,'baselines_started':False})
        except BaseException as exc:
            s.atomic_json(RUNTIME/'exit.json',{'status':'STOP_AND_DEBUG','error':repr(exc),'at':time.time()})
            raise


def start():
    import run
    verify_receipt();preserve_originals()
    if run.active(UNIT):status();return
    import diagnose,repair_geolife
    if repair_geolife.stale_processes(diagnose.ownership(o.SLICE)):raise RuntimeError('Benchmark still active')
    ROOT.mkdir(parents=True,exist_ok=True)
    logfile=ROOT/('campaign-'+time.strftime('%Y%m%dT%H%M%S')+'.log')
    subprocess.run(['systemd-run','--user','--collect','--unit='+UNIT,'--property=TimeoutStopSec=60',
        '--property=StandardOutput=append:'+str(logfile),'--property=StandardError=append:'+str(logfile),
        '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=OPENBLAS_NUM_THREADS=1','--setenv=OMP_NUM_THREADS=1',
        sys.executable,'-B',str(Path(__file__).with_name('run.py')),'--foreground','--method','QMF'],check=True)
    print('QMF-only log: '+str(logfile),flush=True)


def status():
    print(json.dumps({'plan':plan(),'state':s.read_json(RUNTIME/'status.json') if (RUNTIME/'status.json').exists() else {},
        'exit':s.read_json(RUNTIME/'exit.json') if (RUNTIME/'exit.json').exists() else {},
        'QMF_DATASETS_VALID':sum(valid_root(d) is not None for d in DATASETS)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=['qmf','normalize'],required=True)
    parser.add_argument('--dataset',choices=DATASETS[1:],required=True);parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--rep',type=int,default=0);args=parser.parse_args()
    if not args.target.resolve().is_relative_to(ROOT.resolve()):raise RuntimeError('Worker result target outside formal QMF campaign')
    with execution_context(args.dataset,args.target):
        if args.worker=='qmf':worker.qmf(args.dataset,args.rep)
        else:worker.normalize(args.dataset)
