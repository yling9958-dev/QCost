"""Read-only process ownership and historical failure evidence; no controller imports."""
import csv
import datetime
import os
from pathlib import Path
import subprocess
import time
import support as s
import cgroup_policy as cg
import report

def fields(path):
    values={}
    for line in Path(path).read_text().splitlines():
        key,*rest=line.replace(':','').split()
        if not rest: continue
        try: values[key]=int(rest[0])*(1024 if len(rest)>1 and rest[1]=='kB' else 1)
        except ValueError: pass
    return values

def ownership(parent='qmf-paper.slice'):
    group=cg.snapshot(parent); processes=[]; inaccessible=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            status=fields(proc/'status'); path=(proc/'cgroup').read_text().strip().split(':')[-1]
            p={'pid':int(proc.name),'name':(proc/'comm').read_text().strip(),'cgroup':path,
               'in_experiment':bool(group['path']) and path.startswith(group['path']+'/'),
               'rss_bytes':status.get('VmRSS',0),'rss_anon_bytes':status.get('RssAnon',0),
               'rss_file_bytes':status.get('RssFile',0),'swap_bytes':status.get('VmSwap',0)}
            try:
                rollup=fields(proc/'smaps_rollup')
                p.update(pss_bytes=rollup.get('Pss'),pss_anon_bytes=rollup.get('Pss_Anon'))
            except (PermissionError,ProcessLookupError): p['pss_bytes']=None; inaccessible.append(p['pid'])
            try:
                p['normalized_mappings']=[line.split()[-1] for line in (proc/'maps').read_text().splitlines()
                                          if 'points_normalized' in line]
            except PermissionError: p['normalized_mappings']=None
            processes.append(p)
        except (FileNotFoundError,ProcessLookupError,PermissionError): continue
    processes.sort(key=lambda p:p['rss_bytes'],reverse=True)
    root=Path('/sys/fs/cgroup')/group['path'].lstrip('/')
    return {'timestamp':time.time(),'host_meminfo':fields('/proc/meminfo'),'parent':group,
        'parent_memory_stat':fields(root/'memory.stat') if (root/'memory.stat').exists() else {},
        'processes':processes,'pss_inaccessible_pids':inaccessible,
        'outside_pss_observed_bytes':sum(p.get('pss_bytes') or 0 for p in processes if not p['in_experiment']),
        'outside_anon_pss_observed_bytes':sum(p.get('pss_anon_bytes') or 0 for p in processes if not p['in_experiment'])}

def journal(start,end,unit=None,user=False):
    cmd=['journalctl',*(['--user'] if user else []),'--since',start,'--until',end,'--no-pager','-o','short-iso']
    if unit: cmd+=['-u',unit]
    result=subprocess.run(cmd,capture_output=True,text=True)
    return {'stdout':result.stdout,'stderr':result.stderr,'returncode':result.returncode}

def main():
    folder=s.OUT/'debug'; folder.mkdir(exist_ok=True)
    current=ownership(); s.atomic_json(folder/'HOST_MEMORY_CONSUMERS.json',current)
    lines=['# Host memory consumers',f'Observation: {datetime.datetime.fromtimestamp(current["timestamp"]).astimezone().isoformat()}',
        f'MemAvailable: {current["host_meminfo"]["MemAvailable"]/s.GIB:.3f} GiB; observed outside-experiment PSS: {current["outside_pss_observed_bytes"]/s.GIB:.3f} GiB.',
        'RSS can double-count shared pages; inaccessible PSS is N/A. Present memory cannot reconstruct historical ownership.',
        '', '| PID | Process | RSS MiB | PSS MiB | Experiment |','|---|---|---:|---:|---|']
    for p in current['processes'][:40]:
        lines.append(f'| {p["pid"]} | {p["name"]} | {p["rss_bytes"]/2**20:.2f} | {report.fmt(p.get("pss_bytes")/2**20 if p.get("pss_bytes") is not None else None)} | {p["in_experiment"]} |')
    lines+=['','Host file cache and reclaimable slab are recorded separately in JSON; persistent disk files are not counted as anonymous method memory.',
            'No unrelated applications were stopped. System PostgreSQL and browser/desktop processes remain outside the benchmark.']
    report.text(folder/'HOST_MEMORY_CONSUMERS.md','\n'.join(lines)+'\n')
    records={}
    for runtime,phase in [('qmap_uniform_qmf','build0'),('postgis_gist','timing'),('flood','correctness'),('rtree','build0')]:
        label='geolife_2d_4p2G_'+runtime+'_'+phase
        path=s.OUT/'00_environment'/(label+'_resource_summary.json'); summary=s.read_json(path)
        with (s.OUT/'00_environment'/(label+'_resources.csv')).open() as f: samples=list(csv.DictReader(f))
        records[runtime]={'resource_summary':summary,'resource_summary_sha256':s.sha(path),
            'last_periodic_sample':samples[-1] if samples else None,
            'timestamp_local':datetime.datetime.fromtimestamp(summary['timestamp']).astimezone().isoformat()}
    q=records['qmap_uniform_qmf']; k=q['resource_summary']['parent_cgroup']['kernel']
    evidence={'classification':'HOST_SAFETY_STOP','QMF_24G_EXHAUSTION_PROVEN':False,'QMF_HOST_PRESSURE_OBSERVED':True,
      'timestamp':q['resource_summary']['timestamp'],'timestamp_scope':'summary written after stop; journal stop at 19:21:31–32 +0800',
      'phase':'build','reason':q['resource_summary']['reason'],
      'trigger_condition':"now['available'] < 7*GIB//2; available is /proc/meminfo MemAvailable",
      'MemAvailable_at_exact_trigger_bytes':None,'MemAvailable_proven_upper_bound_exclusive_bytes':3758096384,
      'MemTotal_at_exact_trigger_bytes':None,
      'memory_current_final_poll_bytes':k['memory.current'],'memory_peak_bytes':k['memory.peak'],
      'memory_high_bytes':k['memory.high'],'memory_max_bytes':k['memory.max'],'memory_events':k['memory.events'],
      'MemorySwapCurrent_bytes':k['memory.swap.current'],'QMF_RSS_peak_observed_bytes':q['resource_summary']['peak_rss_kib']*1024,
      'QMF_RSS_exact_trigger_bytes':None,'PostgreSQL_RSS_exact_trigger_bytes':None,'PostgreSQL_PSS_exact_trigger_bytes':None,
      'outside_experiment_memory_exact_trigger_bytes':None,'last_periodic_sample':q['last_periodic_sample'],
      'missing_evidence':'Original monitor sampled CSV approximately every 5 seconds and did not persist the triggering MemAvailable or ownership snapshot. No exact number is fabricated from an earlier sample.',
      'source_receipt':q,'OLD_11_3G_PRODUCTION_LIMIT_FOUND':False}
    s.atomic_json(folder/'QMF_STOP_FORENSICS.json',evidence)
    report.text(folder/'QMF_STOP_FORENSICS.md',f'''# QMF stop forensics

Classification: HOST_SAFETY_STOP. QMF_24G_EXHAUSTION_PROVEN = NO. QMF_HOST_PRESSURE_OBSERVED = YES.

The stop was issued at 2026-09-11 19:21:31–32 +0800 during build. The receipt explicitly records the fixed MemAvailable < 3.5 GiB condition. Observed QMF peak RSS was 11,340.26171875 MiB; parent peak was {k['memory.peak']} bytes ({k['memory.peak']/s.GIB:.6f} GiB), with final sampled current {k['memory.current']} bytes. memory.high = {k['memory.high']}; memory.max = {k['memory.max']}; high/max/oom/oom_kill events were all zero. Experiment swap was zero.

Exact triggering MemAvailable, MemTotal, instantaneous worker RSS, PostgreSQL RSS/PSS, and outside-process ownership were not persisted. The last periodic CSV sample had MemAvailable 5,209,817,088 bytes, before the later trigger; it is not the stop-time value. The exact trigger value is therefore N/A, with the strict upper bound 3,758,096,384 bytes supported by the code and receipt. Current host measurements are reported separately and do not explain historical ownership by themselves.

No 11.3 GiB production hard cap was found. The source and kernel evidence both show the 24 GiB hard cap. Future monitor failures record the complete triggering sample and per-process snapshot before termination.
''')
    records['postgis_gist']['systemd_oomd']=journal('2026-09-11 21:38:00','2026-09-11 21:42:00','systemd-oomd')
    records['rtree']['systemd_oomd']=journal('2026-09-12 04:40:00','2026-09-12 04:46:00','systemd-oomd')
    records['postgis_gist'].update(classification='OOM_KILLED',failed_phase='timing',killer='systemd-oomd')
    records['rtree'].update(classification='OOM_KILLED',failed_phase='build',killer='systemd-oomd')
    records['flood'].update(classification='HOST_SAFETY_STOP',failed_phase='correctness')
    records['qmap_uniform_qmf'].update(classification='HOST_SAFETY_STOP',failed_phase='build')
    s.atomic_json(folder/'FOUR_METHOD_FAILURE_FORENSICS.json',records)
    print({'MemAvailable_GiB':current['host_meminfo']['MemAvailable']/s.GIB,
        'outside_pss_GiB':current['outside_pss_observed_bytes']/s.GIB,
        'classifications':{k:v['classification'] for k,v in records.items()}})

if __name__=='__main__': main()
