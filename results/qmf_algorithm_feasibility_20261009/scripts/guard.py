"""Run one diagnostic task with CPU affinity, RSS monitoring and a hard timeout.
All task artifacts are exclusively created below this diagnostic directory.
"""
from pathlib import Path
import argparse, csv, datetime, json, os, shlex, signal, subprocess, sys, time

RUN = Path(__file__).resolve().parents[1]

def status_values(pid):
    try:
        lines = Path(f'/proc/{pid}/status').read_text().splitlines()
    except FileNotFoundError:
        return {}
    out = {}
    for line in lines:
        if line.startswith(('VmRSS:', 'VmHWM:', 'VmSwap:', 'Threads:')):
            key, val = line.split(':', 1)
            out[key] = int(val.strip().split()[0]) * (1024 if key != 'Threads' else 1)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    ap.add_argument('command', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    command = a.command[1:] if a.command and a.command[0] == '--' else a.command
    job = RUN/'jobs'/a.name
    job.mkdir(exist_ok=False)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    env = os.environ.copy()
    settings = {k:'1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS',
        'NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS','BLIS_NUM_THREADS','TORCH_NUM_THREADS']}
    settings.update(PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0', CUDA_VISIBLE_DEVICES='',
        QMF_DIAG_JOB=str(job), MPLCONFIGDIR=str(job/'mplconfig'), XDG_CACHE_HOME=str(job/'cache'))
    env.update(settings)
    started = time.perf_counter()
    receipt = {'command_argv':command,'command_shell':shlex.join(command),
        'cwd':str(RUN),'environment_overrides':settings,'affinity':cpus,
        'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'timeout_seconds':600,'rss_limit_bytes':4*1024**3,'job_directory':str(job)}
    (job/'command.json').write_text(json.dumps(receipt,indent=2))
    max_rss = max_hwm = 0
    state = 'RUNNING'
    with (job/'stdout.log').open('x') as so, (job/'stderr.log').open('x') as se, (job/'resources.csv').open('x',newline='') as rf:
        writer = csv.writer(rf);writer.writerow(['monotonic','elapsed_s','rss_bytes','hwm_bytes','swap_bytes','threads'])
        child = subprocess.Popen(command,cwd=RUN,env=env,stdout=so,stderr=se,start_new_session=True,
            preexec_fn=lambda:os.sched_setaffinity(0,cpus))
        while child.poll() is None:
            now = time.perf_counter();v=status_values(child.pid)
            rss=v.get('VmRSS',0);hwm=v.get('VmHWM',0)
            max_rss=max(max_rss,rss);max_hwm=max(max_hwm,hwm)
            writer.writerow([now,now-started,rss,hwm,v.get('VmSwap',0),v.get('Threads',0)])
            if rss > 4*1024**3:
                state='RSS_LIMIT';os.killpg(child.pid,signal.SIGKILL);break
            if now-started > 600:
                state='TIMEOUT';os.killpg(child.pid,signal.SIGKILL);break
            time.sleep(0.025)
        rc=child.wait()
    if state=='RUNNING':state='PASS' if rc==0 else 'FAILED'
    receipt.update(status=state,returncode=rc,elapsed_seconds=time.perf_counter()-started,
        peak_sampled_rss_bytes=max_rss,peak_observed_hwm_bytes=max_hwm,
        completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (job/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps({'job':a.name,'status':state,'seconds':receipt['elapsed_seconds'],
        'peak_rss_mib':max(max_rss,max_hwm)/1024**2,'output':str(job)},ensure_ascii=False),flush=True)
    return 0 if state=='PASS' else 1

if __name__=='__main__':sys.exit(main())
