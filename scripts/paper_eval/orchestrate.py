"""Durable, sequential evaluation of four complete inputs, with bounded workers."""
import argparse
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

from support import (ROOT, BASE, RUN, OUT, GIB, METHODS, PERSISTENT, METRICS, RECOVERY,
    atomic_json, atomic_csv, read_json, sha, memory, cgroup_stats, output_dirs,
    marker, done, valid)
import cgroup_policy
import outcomes
from phase_timeouts import TIMEOUTS_S

UNIT='qmf-paper-benchmark-20260911'
SLICE='qmf-paper.slice'
PGUNIT='qmf-paper-postgres'
COMMON=RUN/'common'
ACTIVE=RUN/'active'
SCRIPT=Path(__file__).resolve().parent
STATE=RUN/'status.json'
START=time.time()
CURRENT={'dataset':'preflight','method':'none','phase':'initializing'}
WORKER_SEQUENCE=0
PGBIN=Path('/usr/lib/postgresql/14/bin')
ENV={**os.environ,'REPRO_ROOT':str(BASE),'QMF_RUNTIME':str(COMMON),
     'QMAP_BUILD_ROOT':str(COMMON/'build'),'QMAP_BASELINE_WORK':str(COMMON/'baselines'),
     'QMAP_PROJECT_ROOT':str(BASE),'PYTHONPATH':str(BASE/'src/common/python'),
     'PYTHONDONTWRITEBYTECODE':'1','QMF_PGPORT':'55445','PGPORT':'55445',
     'PGHOST':str(COMMON/'pg_socket'),'PGDATABASE':'qmf_full',
     'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
     'QMAP_QMF_SCALAR':'1','QMF_BUILD_JOBS':'2'}
for _key in ['OLD_ROOT','QMF_GEOLIFE_SOURCE','QMF_GEOLIFE_SOURCE_URL','LD_LIBRARY_PATH','QMAP_QMF_SIMD']:
    ENV.pop(_key,None)

class Blocked(Exception):
    def __init__(self,status,reason,phase=None):
        self.status=status; self.phase=phase; super().__init__(reason)

def ctl(*args,check=False):
    benchmark=any(str(a).startswith(('qmf-paper-worker-','qmf-paper-postgres','qmf-paper.slice')) for a in args)
    manager=cgroup_policy.manager(args[0] not in ('show','status','is-active','list-units')) if benchmark else ['systemctl','--user']
    return subprocess.run([*manager,*args],text=True,capture_output=True,check=check)

def launch_prefix():
    # Same user, same fixed budget; system-owned slice avoids the unrelated desktop
    # user@1000 memory-pressure policy that killed otherwise valid benchmark work.
    return (['sudo','-n','systemd-run','--uid='+str(os.getuid()),'--gid='+str(os.getgid())]
            if cgroup_policy.SYSTEM_MANAGER else ['systemd-run','--user'])

def props(unit):
    text=ctl('show',unit,'-p','ActiveState','-p','Result','-p','ExecMainStatus','-p','ExecMainCode','-p','ControlGroup').stdout
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line)

def update(**kwargs):
    CURRENT.update(kwargs)
    mem=memory(); completed=[]; failed=[]
    for p in (OUT/'checkpoints').glob('*/*_method.done'):
        value=read_json(p)['payload']
        label=p.parent.name+':'+value['Method']
        (completed if value['Status']=='PASS' else failed).append(label)
    atomic_json(STATE,{**CURRENT,'pid':os.getpid(),'started_at':START,
        'elapsed_seconds':time.time()-START,'updated_at':time.time(),
        'completed_methods':completed,'failed_methods':failed,'available_ram_GiB':mem['available']/GIB})

def environment_args():
    # Pass only the benchmark overrides to independently managed services.
    names=['REPRO_ROOT','QMF_RUNTIME','QMAP_BUILD_ROOT','QMAP_BASELINE_WORK','QMAP_PROJECT_ROOT',
           'PYTHONPATH','PYTHONDONTWRITEBYTECODE','QMF_PGPORT','PGPORT','PGHOST','PGDATABASE',
           'OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','QMAP_QMF_SCALAR','QMF_BUILD_JOBS']
    if RECOVERY: names.append('QMF_GEO_RECOVERY')
    return [arg for key in names for arg in ['--setenv',key+'='+ENV[key]]]

def observed_query_phase(command,started):
    prefix=next((str(command[i+1]) for i,v in enumerate(command[:-1]) if v=='--latency-output'),None)
    if prefix:
        # A previous failed attempt or completed repetition is not evidence that
        # this worker has finished its own warmup.
        for path in Path(prefix).parent.glob(Path(prefix).name+'.r*.csv*'):
            try:
                if path.stat().st_mtime >= started: return 'timing'
            except FileNotFoundError: pass
    return 'warmup'

def monitor(command,label,timeout=14400,on_tick=None,adopt_unit=None,elapsed_before=0):
    global WORKER_SEQUENCE
    WORKER_SEQUENCE+=1
    unit=adopt_unit or f'qmf-paper-worker-{os.getpid()}-{WORKER_SEQUENCE}'
    if not adopt_unit and props(unit).get('ActiveState')=='active':
        raise RuntimeError('Existing paper worker is active; refuse duplicate or restart')
    if not adopt_unit: ctl('reset-failed',unit)
    if memory()['available']<7*GIB//2:
        import diagnose
        atomic_json(OUT/'00_environment'/(label+'_preflight_host_stop.json'),diagnose.ownership(SLICE))
        raise Blocked('HOST_SAFETY_STOP','HOST_SAFETY_STOP: preflight MemAvailable below 3.5 GiB')
    parent=cgroup_policy.snapshot(SLICE)
    cgroup_policy.validate(parent)
    initial_events=parent['kernel'].get('memory.events',{})
    cap=cgroup_policy.MEMORY_MAX
    pg_phase=CURRENT['phase'] in ('correctness','timing','counts','postgis_build','load')
    logs=RUN/'logs'; logs.mkdir(exist_ok=True)
    logfile=logs/(label+'.log'); usage=logs/(label+'.rusage')
    cmd=[*launch_prefix(),'--quiet','--unit',unit,'--slice',SLICE,
        '--property=MemoryAccounting=yes','--property=ManagedOOMPreference=omit',
        '--property=TimeoutStopSec=10','--property=KillMode=control-group',
        '--property=StandardOutput=append:'+str(logfile),'--property=StandardError=append:'+str(logfile),
        '--working-directory='+str(RUN),*environment_args(),
        '/usr/bin/time','-f','%e,%M,%F','-o',str(usage),*map(str,command)]
    if not adopt_unit: subprocess.run(cmd,check=True,capture_output=True,text=True)
    child=cgroup_policy.snapshot(unit)
    children=[child] if child['path'] else []
    if props(PGUNIT).get('ActiveState')=='active': children.append(cgroup_policy.snapshot(PGUNIT))
    try: cgroup_policy.validate(parent,children)
    except BaseException:
        ctl('stop',unit)
        raise
    atomic_json(OUT/'00_environment'/(label+'_cgroup.json'),{'parent':parent,'children':children})
    started=time.monotonic(); wall_started=time.time(); initial=memory(); last=initial
    maximum={'rss':0,'vm_peak':0,'swap':0,'major_faults':0}
    reason=None; code=None; samples=0; measured_peak=0; parent_peak=0; swap_peak=0
    trigger=None; failed_phase=CURRENT['phase']; terminal_journal=''
    stats_path=OUT/'00_environment'/(label+'_resources.csv')
    with stats_path.open('w',newline='') as handle:
        w=csv.writer(handle); w.writerow(['elapsed_s','rss_bytes','VmPeak_bytes','VmSwap_bytes','major_faults','available_bytes','pswpin','pswpout','parent_memory_current','parent_memory_peak','parent_swap_current'])
        while True:
            info=props(unit); group=info.get('ControlGroup','')
            s=cgroup_stats(group) if group else {k:0 for k in maximum}
            pg_group=props(PGUNIT).get('ControlGroup','')
            pg_stats=cgroup_stats(pg_group) if pg_group else {k:0 for k in maximum}
            measured_peak=max(measured_peak,s['rss']+(pg_stats.get('max_process_rss',pg_stats['rss']) if pg_phase else 0))
            if pg_phase:
                # Include backend memory, not just the small PostgreSQL client.
                for key in ('rss','swap','major_faults'): s[key]+=pg_stats[key]
                s['vm_peak']=max(s['vm_peak'],pg_stats['vm_peak'])
            for k in maximum: maximum[k]=max(maximum[k],s[k])
            now=memory(); elapsed=time.monotonic()-started
            parent_now=cgroup_policy.snapshot(SLICE); kernel=parent_now['kernel']
            parent_peak=max(parent_peak,kernel.get('memory.current') or 0)
            swap_peak=max(swap_peak,kernel.get('memory.swap.current') or 0)
            last=now
            if samples%50==0:
                w.writerow([round(elapsed,3),*[s[k] for k in maximum],now['available'],now['swap_in'],now['swap_out'],kernel.get('memory.current'),kernel.get('memory.peak'),kernel.get('memory.swap.current')]); handle.flush()
            samples+=1
            if samples%10==1: update(current_rss_GiB=s['rss']/GIB,current_vm_peak_GiB=s['vm_peak']/GIB,
                   active_unit=unit,shared_ceiling_GiB=cap/GIB,parent_cgroup=parent_now,
                   parent_memory_current=kernel.get('memory.current'),parent_memory_peak=kernel.get('memory.peak'),
                   experiment_swap_peak=swap_peak,next_phase='complete current phase, checkpoint, advance sequentially')
            events=kernel.get('memory.events',{})
            if events.get('oom_kill',0)>initial_events.get('oom_kill',0):
                reason='Kernel OOM kill observed in experiment parent'; code='OOM_KILLED'
            if swap_peak>0 or s['swap']>0:
                reason='Experiment cgroup swap detected; timing invalid'; code='SWAP_INVALID'
            if now['available']<7*GIB//2:
                reason='HOST_SAFETY_STOP: MemAvailable below fixed 3.5 GiB emergency reserve; not proof of 24 GiB exhaustion'
                code='HOST_SAFETY_STOP'
            if CURRENT['phase']=='timing':
                # The unchanged harness creates latency.r*.csv.part only after all warmup queries return.
                failed_phase=observed_query_phase(command,wall_started)
            if elapsed+elapsed_before>timeout:
                reason=f'Predeclared phase timeout {timeout}s'; code=outcomes.phase_failure(failed_phase)
            if reason:
                trigger={'timestamp':time.time(),'host':now,'parent':parent_now,'worker':s,'postgres':pg_stats,
                         'phase':failed_phase,'reason':reason,'status':code}
                atomic_json(OUT/'00_environment'/(label+'_stop_receipt.json'),trigger)
                import diagnose
                try: atomic_json(OUT/'00_environment'/(label+'_stop_ownership.json'),diagnose.ownership(SLICE))
                except Exception as e: print('Stop ownership snapshot unavailable: '+repr(e),flush=True)
                ctl('stop',unit)
                # Query/build PostgreSQL backends live in the dedicated server unit.
                if pg_phase: ctl('stop',PGUNIT)
                break
            if on_tick:
                try: on_tick()
                except BaseException:
                    ctl('stop',unit)
                    if pg_phase: ctl('stop',PGUNIT)
                    raise
            if info.get('ActiveState') in ('inactive','failed'):
                if info.get('Result')!='success' or info.get('ExecMainStatus')!='0':
                    tail=logfile.read_text(errors='replace')[-2000:] if logfile.exists() else ''
                    reason=f'{info.get("Result")}: {tail}'
                    journal=subprocess.run(['journalctl',*([] if cgroup_policy.SYSTEM_MANAGER else ['--user']),'--since','@'+str(int(wall_started)),
                        '-u',unit,'-u',PGUNIT,'--no-pager','-o','short-iso'],capture_output=True,text=True)
                    terminal_journal=journal.stdout
                    code=outcomes.classify(failed_phase,reason,events,initial_events,
                        oomd='systemd-oomd killed' in terminal_journal,swap=swap_peak)
                break
            time.sleep(.1)
    result={'elapsed_seconds':time.monotonic()-started,'peak_rss_kib':measured_peak/1024,
            'guard_aggregate_peak_rss_kib':maximum['rss']/1024,
            'VmPeak_bytes':maximum['vm_peak'],'major_faults':maximum['major_faults'],
            'shared_ceiling_bytes':cap,'parent_peak_sampled_bytes':parent_peak,
            'parent_memory_peak_bytes':kernel.get('memory.peak'),'experiment_swap_peak_bytes':swap_peak,
            'parent_cgroup':parent_now,'phase':failed_phase,'timestamp':time.time(),'reason':reason,
            'trigger_receipt':trigger,'systemd_exit':info,'user_journal':terminal_journal,
            'swap_pages_in':last['swap_in']-initial['swap_in'],
            'swap_pages_out':last['swap_out']-initial['swap_out'],'status':code or 'PASS'}
    if usage.exists():
        try:
            seconds,peak_rss,major_faults=usage.read_text().strip().splitlines()[-1].split(',')
            result['elapsed_seconds']=float(seconds)
            result['peak_rss_kib']=max(result['peak_rss_kib'],int(peak_rss))
            result['major_faults']=max(result['major_faults'],int(major_faults))
        except (ValueError,IndexError): pass
    atomic_json(OUT/'00_environment'/(label+'_resource_summary.json'),result)
    if reason:
        evidence=subprocess.run(['journalctl','-k','--since','-'+str(int(time.monotonic()-started)+10)+' seconds','--no-pager','-o','short-iso'],capture_output=True,text=True)
        lines=[line for line in evidence.stdout.splitlines() if any(word in line for word in ['CONSTRAINT_MEMCG','oom-kill','Out of memory','Killed process',SLICE])]
        atomic_json(OUT/'00_environment'/(label+'_oom_evidence.json'),{'parent_memory_events':kernel.get('memory.events',{}),
            'kernel_lines':lines,'journal_access_error':evidence.stderr.strip(),'reason':reason})
    ctl('reset-failed',unit)
    if reason: raise Blocked(code,reason,failed_phase)
    return result

def worker(phase,dataset=None,rep=None):
    return [sys.executable,'-B',str(SCRIPT/'worker.py'),phase]+([dataset] if dataset else [])+([str(rep)] if rep is not None else [])

def sql(text,label,timeout=14400):
    return monitor(['psql','-X','-v','ON_ERROR_STOP=1','-c',text],label,timeout)

def scalar(text,database=None):
    return subprocess.check_output(['psql','-X','-At','-v','ON_ERROR_STOP=1','-c',text],
        env={**ENV,**({'PGDATABASE':database} if database else {})},text=True).strip()

def setup():
    update(phase='baseline_verification')
    subprocess.run(['bash',str(BASE/'scripts/00_verify_archive.sh')],check=True,env=ENV)
    monitor(['bash',str(BASE/'scripts/01_check_environment.sh')],'environment',600)
    manifest=sha(BASE/'MANIFEST.sha256')
    lock=OUT/'00_environment'/'baseline_lock.json'
    if lock.exists() and read_json(lock)['manifest_sha256']!=manifest:
        raise RuntimeError('Authoritative baseline changed during experiment')
    atomic_json(lock,{'root':str(BASE),'manifest_sha256':manifest,'algorithm_changed':False})
    if not valid('_global','compiled'):
        update(phase='compile')
        monitor(['bash',str(BASE/'third_party/fetch_baselines.sh')],'fetch',1800)
        monitor(['bash',str(BASE/'scripts/04_build_all.sh')],'compile',1800)
        monitor(['g++','-O3','-DNDEBUG','-march=native','-std=c++17','-I/usr/include/postgresql',
                 SCRIPT/'postgres_full.cpp','-lpq','-pthread','-o',RUN/'qmf_postgres_full'],'compile_harness',600)
        done('_global','compiled',files=[RUN/'qmf_postgres_full',COMMON/'build/bin/qmap_build_index'])
    pg=COMMON/'pg_data'; (COMMON/'pg_socket').mkdir(parents=True,exist_ok=True)
    if not (pg/'PG_VERSION').exists():
        monitor([PGBIN/'initdb','-D',pg,'--auth-local=trust','--auth-host=scram-sha-256',
                 '--encoding=UTF8','--locale=C.UTF-8'],'initdb',600)
        shutil.copy2(BASE/'config/postgres.conf.repro',pg/'repro.conf')
        with (pg/'postgresql.conf').open('a') as f: f.write("\ninclude = 'repro.conf'\n")
    ensure_pg()
    if scalar("SELECT count(*) FROM pg_database WHERE datname='qmf_full'",'postgres')== '0':
        subprocess.run(['createdb','qmf_full'],env={**ENV,'PGDATABASE':'postgres'},check=True)
    sql('CREATE EXTENSION IF NOT EXISTS postgis','postgis_extension',600)
    if scalar('SELECT PostGIS_Lib_Version()')!='3.2.0': raise RuntimeError('PostGIS version mismatch')
    if scalar("SELECT count(*) FROM pg_proc WHERE proname='qmap_range_count'")=='0':
        text=(BASE/'src/postgres/qmap_benchmark--1.0.sql').read_text().replace('MODULE_PATHNAME',str(COMMON/'extension/qmap_benchmark'))
        path=RUN/'install_extension.sql'; path.write_text(text)
        monitor(['psql','-X','-v','ON_ERROR_STOP=1','-f',path],'install_extension',600)
    atomic_json(OUT/'00_environment'/'environment.json',{
        'postgres':subprocess.check_output(['pg_config','--version'],text=True).strip(),
        'postgis':scalar('SELECT PostGIS_Lib_Version()'),'memory':memory(),
        'cpu':subprocess.check_output(['lscpu'],text=True),'python':sys.version,
        'slice':SLICE,'swap_policy':'Shared parent MemoryHigh=22GiB MemoryMax=24GiB MemorySwapMax=0; historical host swap occupancy allowed',
        'timing_policy':'single connection/worker, prepared SQL, 300 warmup then five 3000-query repetitions; no OS cache flush'})

def ensure_pg():
    if props(PGUNIT).get('ActiveState')!='active':
        for _ in range(300):
            if props(PGUNIT).get('ActiveState')!='deactivating': break
            time.sleep(.1)
        ctl('reset-failed',PGUNIT)
        subprocess.run([*launch_prefix(),'--quiet','--unit',PGUNIT,'--slice',SLICE,
            '--property=MemoryAccounting=yes','--property=ManagedOOMPreference=omit','--property=TimeoutStopSec=30',
            '--property=KillSignal=SIGINT','--property=StandardOutput=append:'+str(RUN/'postgres.log'),
            '--property=StandardError=append:'+str(RUN/'postgres.log'),
            str(PGBIN/'postgres'),'-D',str(COMMON/'pg_data'),'-k',str(COMMON/'pg_socket'),'-p','55445',
            '-c','listen_addresses='],check=True)
        for _ in range(120):
            p=subprocess.run(['pg_isready','-h',ENV['PGHOST'],'-p','55445'],capture_output=True)
            if p.returncode==0:
                cgroup_policy.validate(cgroup_policy.snapshot(SLICE),[cgroup_policy.snapshot(PGUNIT)])
                return
            time.sleep(.5)
        raise RuntimeError('Dedicated PostgreSQL failed to start')

def prepare_dataset(row):
    dataset=row['dataset_id']; work=ACTIVE/dataset; work.mkdir(parents=True,exist_ok=True)
    source=Path(row['source_path'])
    if source.stat().st_size!=row['raw_bytes'] or source.stat().st_mtime_ns!=row['mtime_ns']:
        raise RuntimeError('Frozen source stat changed')
    update(dataset=dataset,method='shared',phase='normalize')
    if RECOVERY:
        from recovery import DATASET,CACHE,NORMAL_SHA
        if dataset!=DATASET or not valid(dataset,'recovery_artifacts',False):
            raise RuntimeError('RECOVERY_ARTIFACT_GATE_NOT_PASSED')
        persistent=CACHE/'points_normalized.csv'
        if not persistent.is_file() or read_json(CACHE/'normalized_manifest.json')['sha256']!=NORMAL_SHA:
            raise RuntimeError('GEOLIFE_CONVERSION_ARTIFACT_MISSING')
        if not (work/'points_normalized.csv').exists(): (work/'points_normalized.csv').symlink_to(persistent)
    elif not valid(dataset,'normalize'):
        monitor(worker('normalize',dataset),dataset+'_normalize',14400)
        meta=read_json(work/'normalized.json')
        # The normalized data SHA is recorded here and checked on a resumed phase.
        done(dataset,'normalize',meta,files=[work/'normalized.json',work/'points_normalized.csv'])
        shutil.copy2(work/'normalized.json',OUT/'01_dataset_inventory'/f'{dataset}_normalized.json')
    update(phase='queries')
    if RECOVERY and not valid(dataset,'queries'):
        raise RuntimeError('FULL_QUERY_SHA_MISMATCH: recovery never regenerates queries')
    if not RECOVERY and not valid(dataset,'queries'):
        monitor(worker('queries',dataset),dataset+'_queries',600)
        folder=OUT/'02_queries'/dataset
        done(dataset,'queries',read_json(folder/'query_manifest.json'),files=sorted(folder.glob('*.csv')))
        manifests=[read_json(p) for p in sorted((OUT/'02_queries').glob('*/query_manifest.json'))]
        fields=['dataset','query_count','S1_count','S2_count','S3_count','correctness_count','warmup_count','query_sha256']
        atomic_csv(OUT/'02_queries'/'query_manifest.csv',[{k:r[k] for k in fields} for r in manifests],fields)
    ensure_pg(); update(phase='load')
    has_table=scalar("SELECT count(*) FROM pg_tables WHERE tablename='points'")=='1'
    if not valid(dataset,'load',False) or not has_table:
        sql('DROP VIEW IF EXISTS evaluation; DROP TABLE IF EXISTS points CASCADE; '
            'CREATE TABLE points (id BIGINT GENERATED ALWAYS AS IDENTITY (MINVALUE 0 START 0) PRIMARY KEY, '
            'x DOUBLE PRECISION NOT NULL,y DOUBLE PRECISION NOT NULL, '
            'geom geometry(Point,4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(x,y),4326)) STORED);',dataset+'_table',600)
        path=RUN/'load.sql'
        safe=str(source).replace("'","''")
        path.write_text(f"\\copy points(x,y) FROM '{safe}' WITH (FORMAT csv, HEADER true)\n")
        monitor(['psql','-X','-v','ON_ERROR_STOP=1','-f',path],dataset+'_load',14400)
        sql('CREATE VIEW evaluation AS SELECT id,x,y,x AS lon,y AS lat,geom FROM points; ANALYZE points;',dataset+'_analyze',1800)
        count=int(scalar('SELECT count(*) FROM points'))
        if count!=row['record_count']: raise RuntimeError('PostgreSQL full dataset row count mismatch')
        done(dataset,'load',{'points':count,'id_mapping':'source ordinal from identity START 0'})
    # Reference GiST is shared setup and its construction is charged only to PostGIS.
    update(method='PostGIS-GiST',phase='postgis_build')
    if not marker(dataset,'reference_build_failure').exists() and (not valid(dataset,'postgis_reference',False) or scalar("SELECT to_regclass('points_gist') IS NOT NULL")!='t'):
        try:
            # This exact receipt supplies PostGIS's formal Build measurement.
            result=sql('DROP INDEX IF EXISTS points_gist; CREATE INDEX points_gist ON points USING GIST(geom); ANALYZE points;',dataset+'_reference_gist',TIMEOUTS_S['build'])
            size=int(scalar("SELECT pg_relation_size('points_gist')"))
            done(dataset,'postgis_reference',{**result,'serialized_bytes':size})
        except Blocked as e:
            done(dataset,'reference_build_failure',{'status':e.status,'reason':str(e)})

def ensure_counts(row):
    # No precomputed reference phase. Exact ID truth is evaluated only in correctness.
    return

def query_command(row,runtime,phase,correctness,latency,summary,start):
    dataset=row['dataset_id']; bounds=row['bounds']
    command=['taskset','-c',str(min(os.sched_getaffinity(0))),str(RUN/'qmf_postgres_full'),
        '--conninfo','dbname=qmf_full application_name=qmf_full_'+runtime,
        '--method',runtime,'--table','evaluation',
        '--queries',str(OUT/'02_queries'/dataset/f'{dataset}_queries.csv'),
        '--repetitions','5','--phase',phase,'--start-repetition',str(start),
        '--index-root',str(ACTIVE/dataset/'indexes'),
        '--source-xmin',str(bounds[0]),'--source-ymin',str(bounds[1]),
        '--source-xmax',str(bounds[2]),'--source-ymax',str(bounds[3]),
        '--correctness-output',str(correctness),'--latency-output',str(latency),'--summary-output',str(summary)]
    return command

def fairness(record):
    value=record['fairness']
    if value=='NATIVE_POSTGIS': return
    for key in ['query_rebuild_count','query_reload_count','query_training_count',
                'query_external_process_count','query_python_count','query_quantum_count']:
        if value.get(key)!=0: raise Blocked(outcomes.phase_failure(CURRENT['phase']),'Online safety counter failed: '+key)
    if value.get('load_count')!=1: raise Blocked(outcomes.phase_failure(CURRENT['phase']),'Index did not preload exactly once')

def build_one(row,runtime,rep):
    dataset=row['dataset_id']; work=ACTIVE/dataset
    folder=work/'methods'/runtime/f'rep{rep}'; folder.mkdir(parents=True,exist_ok=True)
    normalized=work/'points_normalized.csv'; qdir=OUT/'02_queries'/dataset
    index=folder/(runtime+'.idx'); update(phase='build',repetition=rep)
    if runtime=='postgis_gist':
        if rep==0:
            failure=marker(dataset,'reference_build_failure')
            if failure.exists():
                value=read_json(failure)['payload']; raise Blocked(value['status'],value['reason'])
            result=read_json(marker(dataset,'postgis_reference'))['payload']
        else:
            update(phase='postgis_build')
            result=sql('DROP INDEX IF EXISTS points_gist; CREATE INDEX points_gist ON points USING GIST(geom); ANALYZE points;',f'{dataset}_{runtime}_build{rep}',TIMEOUTS_S['build'])
            result['serialized_bytes']=int(scalar("SELECT pg_relation_size('points_gist')"))
        return {'build_seconds':result['elapsed_seconds'],'serialized_bytes':result['serialized_bytes'],
                'peak_rss_kib':result['peak_rss_kib'],'repetition':rep}
    extra_seconds=extra_peak=0
    if runtime=='qmap_uniform_qmf':
        resources=monitor(worker('qmf',dataset,rep),f'{dataset}_{runtime}_build{rep}',TIMEOUTS_S['build'])
        metadata=read_json(folder/'metadata.json')
        if metadata['point_count']!=row['record_count']: raise Blocked('BUILD_FAILED','QMF row count mismatch')
        if metadata['online_quantum_search'] or metadata['online_python_controller']:
            raise Blocked('BUILD_FAILED','QMF online flag enabled')
        diagnostic=OUT/'06_qmf_diagnostics'/dataset; diagnostic.mkdir(parents=True,exist_ok=True)
        shutil.copy2(folder/'metadata.json',diagnostic/f'build_r{rep}.json')
        shutil.copy2(folder/'tree_decision_manifest.csv',diagnostic/f'tree_r{rep}.csv')
        if rep and sha(diagnostic/'tree_r0.csv')!=sha(diagnostic/f'tree_r{rep}.csv'):
            raise Blocked('BUILD_FAILED','QMF tree changed across identical builds')
        return {'build_seconds':metadata['index_build_seconds'],'serialized_bytes':index.stat().st_size,
                'peak_rss_kib':max(metadata['peak_rss_kib'],resources['peak_rss_kib']),
                'tree_sha256':sha(folder/'tree_decision_manifest.csv'),'index_sha256':sha(index),
                'index_path':str(index),'repetition':rep}
    args=[COMMON/'build/bin/qmap_build_index','--method',runtime,'--points',normalized,
          '--train-queries',qdir/'train_normalized.csv','--validation-queries',qdir/'validation_normalized.csv',
          '--index',index,'--output',folder/'build.csv']
    if runtime=='bmtree':
        source=COMMON/'bmtree-official'
        if not source.exists():
            source.mkdir()
            with subprocess.Popen(['git','-C',str(COMMON/'baselines/bmtree'),'archive','HEAD'],stdout=subprocess.PIPE) as a:
                subprocess.run(['tar','-x','-C',str(source)],stdin=a.stdout,check=True)
                a.wait()
        result=monitor([sys.executable,'-B',BASE/'scripts/export_bmtree_model.py','--source',source,
            '--points',normalized,'--train-queries',qdir/'train_normalized.csv','--output',folder/'bmtree.model',
            '--metadata',folder/'bmtree_model.json','--seed','1'],f'{dataset}_bmtree_model{rep}',TIMEOUTS_S['build'])
        extra_seconds=result['elapsed_seconds']; extra_peak=result['peak_rss_kib']
        args+=['--bmtree-model',folder/'bmtree.model']
    # BMTree's model export and index construction share the same total monitored
    # build budget; other baselines have no preceding build subprocess.
    resources=monitor(args,f'{dataset}_{runtime}_build{rep}',TIMEOUTS_S['build'],elapsed_before=extra_seconds)
    with (folder/'build.csv').open() as f: values=next(csv.DictReader(f))
    return {'build_seconds':int(values['total_ns'])/1e9+extra_seconds,
            'serialized_bytes':index.stat().st_size,'peak_rss_kib':max(float(values['peak_rss_kib']),extra_peak,resources['peak_rss_kib']),
            'index_path':str(index),'index_sha256':sha(index),'repetition':rep}

def run_method(row,display,runtime):
    import numpy as np
    import pandas as pd
    dataset=row['dataset_id']; work=ACTIVE/dataset
    update(method=display,phase='build')
    existing=marker(dataset,runtime+'_method')
    if existing.exists():
        cleanup_method(dataset,runtime)
        return read_json(existing)['payload']
    output={k:None for k in METRICS}
    output.update(Method=display,Correctness='NOT_RUN',Status='BUILD_FAILED',reason='',BUILD_REPETITIONS=1)
    builds=[]
    try:
        query=OUT/'02_queries'/dataset/f'{dataset}_queries.csv'
        if sha(query)!=read_json(OUT/'02_queries'/dataset/'query_manifest.json')['query_sha256']:
            raise RuntimeError('Frozen query workload changed before method')
        source=Path(row['source_path'])
        if source.stat().st_size!=row['raw_bytes'] or source.stat().st_mtime_ns!=row['mtime_ns']:
            raise RuntimeError('Frozen source changed before method')
        if runtime!='qmap_uniform_qmf': ensure_pg()
        for rep in range(1):
            if rep and builds[0]['build_seconds']>600: break
            name=f'{runtime}_build_r{rep}'
            if valid(dataset,name): values=read_json(marker(dataset,name))['payload']
            else:
                values=build_one(row,runtime,rep)
                done(dataset,name,values,files=([values['index_path']] if 'index_path' in values else []))
            builds.append(values)
            (OUT/'03_build'/dataset).mkdir(parents=True,exist_ok=True)
            atomic_json(OUT/'03_build'/dataset/(runtime+'.json'),builds)
        output['BUILD_REPETITIONS']=len(builds)
        output['Build_s']=float(np.mean([b['build_seconds'] for b in builds]))
        output['IndexSize_MiB']=float(np.mean([b['serialized_bytes'] for b in builds]))/1024**2 if runtime in PERSISTENT else None
        if runtime=='postgis_gist':
            actual_size=int(scalar("SELECT pg_relation_size('points_gist')"))
            output['IndexSize_MiB']=actual_size/1024**2
            output['original_build_index_bytes']=builds[0]['serialized_bytes']
            output['index_size_basis']='Actual query-ready PostgreSQL relation; original build receipt retained'
        output['PeakMemory_MiB']=max(b['peak_rss_kib'] for b in builds)/1024
        ensure_pg()
        # Exact truth is evaluated only for the 1000 correctness queries.
        ensure_counts(row)
        indexes=work/'indexes'; indexes.mkdir(exist_ok=True)
        if runtime!='postgis_gist':
            link=indexes/(runtime+'.idx')
            if link.is_symlink(): link.unlink()
            link.symlink_to(Path(builds[0]['index_path']))
        corrdir=OUT/'04_correctness'/dataset; corrdir.mkdir(parents=True,exist_ok=True)
        corr=corrdir/(runtime+'.csv'); summary=corrdir/(runtime+'_summary.json')
        perf=OUT/'05_performance'/dataset/runtime; perf.mkdir(parents=True,exist_ok=True)
        update(phase='correctness')
        if not valid(dataset,runtime+'_correctness'):
            monitor(query_command(row,runtime,'correctness',corr,perf/'latency',summary,0),f'{dataset}_{runtime}_correctness',43200)
            frame=pd.read_csv(corr)
            if len(frame)!=1000 or not frame.exact.eq(1).all() or frame.missing.sum()!=0 or frame.extra.sum()!=0:
                raise Blocked('CORRECTNESS_FAILED','Exact 1000-query gate failed')
            fairness(read_json(summary))
            done(dataset,runtime+'_correctness',{'exact':1000,'missing':0,'extra':0},[corr,summary])
        output['Correctness']='1000/1000 exact'
        stats=read_json(summary)
        output['PeakMemory_MiB']=max(output['PeakMemory_MiB'],(stats['backend_peak_rss_kib']+stats['client_peak_rss_kib'])/1024)
        update(phase='timing')
        def accept_repetitions():
            for rep in range(5):
                cp=f'{runtime}_timing_r{rep+1}'
                if marker(dataset,cp).exists(): continue
                raw=perf/f'latency.r{rep}.csv'; ready=Path(str(raw)+'.ready')
                if ready.exists() and raw.exists():
                    values=read_json(ready); fairness(values)
                    with raw.open() as f:
                        n=sum(1 for _ in f)-1
                    if n!=3000: raise RuntimeError('Incomplete repetition output')
                    done(dataset,cp,values,files=[raw,ready])
        accept_repetitions()
        pending=[rep for rep in range(5) if not valid(dataset,f'{runtime}_timing_r{rep+1}')]
        if pending:
            first=min(pending)
            # Resume only a contiguous prefix, preserving the declared query order.
            if any(marker(dataset,f'{runtime}_timing_r{r+1}').exists() for r in range(first+1,5)):
                raise RuntimeError('Noncontiguous timing checkpoints')
            monitor(query_command(row,runtime,'timing',corr,perf/'latency',summary,first),
                    f'{dataset}_{runtime}_timing',43200,on_tick=accept_repetitions)
            accept_repetitions()
        update(phase='finalization')
        frames=[]
        compressed=perf/'query_latency_raw.csv.zst'
        already_compressed=compressed.exists() and all(valid(dataset,f'{runtime}_timing_r{r+1}') for r in range(5)) and not (perf/'latency.r0.csv').exists()
        if already_compressed:
            with subprocess.Popen(['zstd','-q','-d','-c',str(compressed)],stdout=subprocess.PIPE) as proc:
                frames.append(pd.read_csv(proc.stdout))
                if proc.wait()!=0: raise RuntimeError('Corrupt compressed timing file')
        for rep in range(5):
            raw=perf/f'latency.r{rep}.csv'
            if not already_compressed: frames.append(pd.read_csv(raw))
            stats=read_json(marker(dataset,f'{runtime}_timing_r{rep+1}'))['payload']
            output['PeakMemory_MiB']=max(output['PeakMemory_MiB'],(stats['backend_peak_rss_kib']+stats['client_peak_rss_kib'])/1024)
        frame=pd.concat(frames,ignore_index=True)
        if len(frame)!=15000 or frame.repetition.nunique()!=5:
            raise RuntimeError('Incomplete paper timing evidence')
        expected=[r['query_id'] for r in csv.DictReader(query.open()) if r['split']=='performance']
        for rep in range(5):
            if frame[frame.repetition==rep].query_id.tolist()!=expected:
                raise RuntimeError('Timing repetition query order mismatch')
        v=frame.latency_ns.to_numpy(dtype=np.float64)
        output.update(Mean_ms=float(v.mean()/1e6),P95_ms=float(np.quantile(v,.95)/1e6),
                      P99_ms=float(np.quantile(v,.99)/1e6),QPS=float(1e9/v.mean()),Status='PASS')
        uncompressed=perf/'query_latency_raw.csv'
        frame.to_csv(uncompressed,index=False)
        subprocess.run(['zstd','-q','-f',str(uncompressed),'-o',str(perf/'query_latency_raw.csv.zst')],check=True)
        if subprocess.run(['zstd','-q','-t',str(perf/'query_latency_raw.csv.zst')]).returncode:
            raise RuntimeError('Compressed timing verification failed')
        uncompressed.unlink()
        for rep in range(5):
            raw=perf/f'latency.r{rep}.csv'
            done(dataset,f'{runtime}_timing_r{rep+1}',read_json(marker(dataset,f'{runtime}_timing_r{rep+1}'))['payload'],files=[perf/'query_latency_raw.csv.zst'])
        # Write completion before pruning the now-redundant raw repetition files.
        done(dataset,runtime+'_method',output)
        for rep in range(5):
            raw=perf/f'latency.r{rep}.csv'
            raw.unlink(missing_ok=True); Path(str(raw)+'.ready').unlink(missing_ok=True)
    except Blocked as e:
        output.update(Status=e.status,reason=str(e),failed_phase=e.phase or CURRENT['phase'])
    except Exception as e:
        if any(word in str(e) for word in ['Frozen', 'SHA', 'source changed', 'CGROUP_FIX']): raise
        output.update(Status=outcomes.phase_failure(CURRENT['phase']),reason=f'{type(e).__name__}: {e}',failed_phase=CURRENT['phase'])
    finally:
        # Close all clients first. Each method's query backend exits with the client.
        if props(PGUNIT).get('ActiveState')=='active':
            subprocess.run(['psql','-X','-c',"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name LIKE 'qmf_full_%' AND pid<>pg_backend_pid()"],env=ENV,capture_output=True)
    if builds:
        output['BUILD_REPETITIONS']=len(builds)
        if output['Build_s'] is None: output['Build_s']=float(np.mean([b['build_seconds'] for b in builds]))
    if output['Status']!='PASS':
        perf=OUT/'05_performance'/dataset/runtime
        for raw in sorted(perf.glob('latency.r*.csv*')):
            if raw.suffix not in ('.csv','.part'): continue
            compressed=Path(str(raw)+'.zst')
            subprocess.run(['zstd','-q','-f',str(raw),'-o',str(compressed)],check=True)
            subprocess.run(['zstd','-q','-t',str(compressed)],check=True)
            if raw.suffix=='.csv':
                rep=int(raw.name.split('.')[1][1:])
                cp=f'{runtime}_timing_r{rep+1}'
                if marker(dataset,cp).exists():
                    done(dataset,cp,read_json(marker(dataset,cp))['payload'],files=[compressed])
            raw.unlink()
    for resource in (OUT/'00_environment').glob(dataset+'_'+runtime+'_*resource_summary.json'):
        peak=read_json(resource).get('peak_rss_kib',0)/1024
        output['PeakMemory_MiB']=max(output.get('PeakMemory_MiB') or 0,peak) or None
    done(dataset,runtime+'_method',output)
    cleanup_method(dataset,runtime)
    print(f'{dataset} {display}: {output["Status"]} {output["reason"][:180]}',flush=True)
    return output

def cleanup_method(dataset,runtime):
    path=ACTIVE/dataset/'methods'/runtime
    cp=marker(dataset,runtime+'_method')
    successful=cp.exists() and read_json(cp)['payload'].get('Status')=='PASS'
    if successful and path.is_dir() and path.is_relative_to(ACTIVE) and len(path.relative_to(ACTIVE).parts)==3:
        shutil.rmtree(path)
    link=ACTIVE/dataset/'indexes'/(runtime+'.idx')
    if link.is_symlink(): link.unlink()
    atomic_json(OUT/'00_environment'/f'{dataset}_{runtime}_idle.json',memory())
