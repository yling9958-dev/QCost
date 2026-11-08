import os, sys, subprocess, json, time, csv, signal, shutil
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from initial_audit import ROOT,FLOOD,KIT,COMMON,VALIDATOR,sha,write
sys.path.insert(0,str(KIT/'scripts'))
import kitlib
SLICE='qmf-skewed-completion.slice'
RUNTIME=Path(os.environ.get('FLOOD_COMPLETION_RUNTIME','/var/tmp/flood-skewed2d-completion-20261024'))
def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def run(cmd,**kw):return subprocess.run(list(map(str,cmd)),check=True,**kw)
def native_env():
    return {'LD_LIBRARY_PATH':str(COMMON/'build/lib')} if os.environ.get('FLOOD_COMPLETION_COMMON') else {}
def configure():
    RUNTIME.mkdir(exist_ok=True)
    run(['sudo','-n','systemctl','set-property','--runtime',SLICE,'MemoryAccounting=yes','MemoryHigh=23622320128','MemoryMax=25769803776','MemorySwapMax=0'])
    run(['sudo','-n','systemctl','start',SLICE])
def monitor(command,folder,label,timeout=43200,env=None):
    folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/(label+'_receipt.json')
    if receipt.exists():raise RuntimeError('Existing stage receipt: refuse overwrite '+str(receipt))
    unit='qmf-skewed-'+label.replace('_','-')+'-'+str(time.time_ns())+'.service'
    cmd=['sudo','-n','systemd-run','--quiet','--wait','--pipe','--unit='+unit,'--slice='+SLICE,'--uid='+str(os.getuid()),'--gid='+str(os.getgid()),'-p','KillMode=control-group','-p','TimeoutStopSec=30']
    for k,v in {**{x:'1' for x in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']},**native_env(),**(env or {})}.items():cmd+=['--setenv='+k+'='+str(v)]
    cmd+=['/usr/bin/time','-v',*map(str,command)]
    started=time.monotonic();meta=dict(started=now(),command=list(map(str,command)),unit=unit,phase=label,sampling_interval_s=0.1,trace_interval_s=2)
    group_name=subprocess.check_output(['systemctl','show',SLICE,'-p','ControlGroup','--value'],text=True).strip()
    group=Path('/sys/fs/cgroup')/group_name.lstrip('/')
    assert group_name and (group/'memory.max').read_text().strip()=='25769803776'
    meta['cgroup_path']=str(group)
    meta['initial_memory_events']=(group/'memory.events').read_text()
    write(folder/(label+'_command.json'),meta)
    reason=None;peak=0;historical_peak=0;last_trace=-2
    with (folder/(label+'.log')).open('w') as log,(folder/(label+'_resources.jsonl')).open('w') as trace:
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        try:
            while proc.poll() is None:
                mem={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines())}
                obs=dict(at=now(),elapsed_s=time.monotonic()-started,available=mem['MemAvailable'])
                obs['runtime_free_bytes']=shutil.disk_usage(RUNTIME).free
                obs['output_free_bytes']=shutil.disk_usage(ROOT).free
                for f in ['memory.current','memory.peak','memory.swap.current','memory.events','memory.pressure','memory.stat']:
                    if (group/f).exists():obs[f]=(group/f).read_text()
                pids=[]
                if group.exists():
                    for f in group.rglob('cgroup.procs'):
                        pids.extend(f.read_text().split())
                rss={}
                for pid in pids:
                    try:
                        status=Path('/proc',pid,'status').read_text().splitlines()
                        rss[pid]={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in status if l.startswith(('VmRSS:','VmHWM:','VmSwap:')))}
                    except (FileNotFoundError,ProcessLookupError):pass
                obs['process_memory']=rss
                peak=max(peak,sum(v.get('VmRSS',0) for v in rss.values()))
                worker_rss=0;pg_max=0
                for pid,v in rss.items():
                    try:cg=Path('/proc',pid,'cgroup').read_text()
                    except FileNotFoundError:continue
                    if unit in cg:worker_rss+=v.get('VmRSS',0)
                    elif 'qmf-skewed-completion-postgres.service' in cg:pg_max=max(pg_max,v.get('VmRSS',0))
                measured=worker_rss+(pg_max if label in ('correctness','timing') else 0)
                historical_peak=max(historical_peak,measured)
                obs['historical_peak_rss_bytes']=historical_peak
                if obs['elapsed_s']-last_trace>=2:
                    trace.write(json.dumps(obs)+'\n');trace.flush();last_trace=obs['elapsed_s']
                if mem['MemAvailable']<3758096384:reason='HOST_SAFETY_STOP: MemAvailable below 3.5 GiB'
                if obs.get('memory.swap.current','0').strip()!='0':reason='SWAP_INVALID'
                if time.monotonic()-started>timeout:reason='TIMEOUT'
                if obs['runtime_free_bytes']<12*1024**3:reason='STORAGE_SAFETY_STOP: NVMe free below 12 GiB'
                if obs['output_free_bytes']<10*1024**3:reason='STORAGE_SAFETY_STOP: output free below 10 GiB'
                if reason:
                    run(['sudo','-n','systemctl','stop',unit]);break
                time.sleep(0.1)
            code=proc.wait()
        except BaseException:
            subprocess.run(['sudo','-n','systemctl','stop',unit]);proc.wait();raise
    meta.update(ended=now(),elapsed_s=time.monotonic()-started,returncode=code,stop_reason=reason,sampled_process_tree_peak_bytes=peak,historical_peak_rss_bytes=historical_peak)
    meta['final_memory_events']=(group/'memory.events').read_text()
    write(receipt,meta)
    print(json.dumps(meta),flush=True)
    if code or reason:raise RuntimeError('Stage failed; receipt preserved: '+str(receipt))
    return meta
def stage(name):
    with kitlib.GlobalLease('flood_skewed2d_completion') as lease:
        configure()
        write(ROOT/'01_environment'/f'{name}_lease.json',dict(ticket=str(lease.ticket),at=now()))
        if name=='validation':
            binary=VALIDATOR
            for n in [16384,1000000]:
                folder=ROOT/'03_validation'/f'validation_{n}';folder.mkdir(exist_ok=True)
                monitor([binary,ROOT/'03_validation'/f'diagnostic_{n}.csv',folder/'correctness.csv',RUNTIME/f'diagnostic_{n}'],folder,f'validation_{n}')
                rows=list(csv.DictReader((folder/'correctness.csv').open()))
                assert len(rows)==4808 and all(r['exact']=='1' and r['missing']=='0' and r['extra']=='0' for r in rows)
                write(folder/'PASS.json',dict(checks=len(rows),real_points=n,diagnostic_only=True))
        elif name=='full_read':
            monitor([sys.executable,ROOT/'tools/initial_audit.py','full'],ROOT/'03_validation','full_read',14400)
        elif name=='build':
            assert all((ROOT/'03_validation'/f'validation_{n}/PASS.json').exists() for n in [16384,1000000])
            data=json.loads((ROOT/'03_validation/full_input_validation.json').read_text());assert len(data)==2 and all(d['points']==204986702 for d in data)
            q=ROOT/'03_validation/frozen_queries';f=ROOT/'04_build'
            assert sha(COMMON/'build/bin/qmap_build_index')=='01008977adf8b6b394d828ddc79e69306704e1a7aeefba033b5f91a50f2afd4a'
            monitor([COMMON/'build/bin/qmap_build_index','--method','flood','--points',data[1]['path'],'--train-queries',q/'train_normalized.csv','--validation-queries',q/'validation_normalized.csv','--index',RUNTIME/'flood.idx','--output',f/'build.csv'],f,'full_build',env={'QMF_FLOOD_OWNERSHIP_TRACE':f/'ownership.csv'})
            write(f/'artifact.json',dict(path=str(RUNTIME/'flood.idx'),sha256=sha(RUNTIME/'flood.idx'),bytes=(RUNTIME/'flood.idx').stat().st_size))
        elif name=='grid':
            monitor([sys.executable,ROOT/'tools/audit_grid.py'],ROOT/'04_build','grid_audit',3600)
        else:raise ValueError(name)
if __name__=='__main__':stage(sys.argv[1])
