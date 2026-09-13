"""Filesystem checkpoints and Linux resource accounting for the full-data run."""
import csv
import hashlib
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'QMF_PostGIS_100M_Repro_20260910'
RECOVERY = False
RUN = Path('/var/tmp/qmf-paper-protocol-20260911')
OUT = ROOT / 'results/four_dataset_paper_protocol_20260911'
SEED = 20260910
GIB = 1024**3
METHODS = [('QMF','qmap_uniform_qmf'), ('PostGIS-GiST','postgis_gist'),
           ('LISA','lisa'), ('Flood','flood'), ('Tsunami','tsunami'),
           ('LMSFC','lmsfc'), ('BMTree','bmtree'), ('Boost-Rstar','rtree')]
PERSISTENT = {'qmap_uniform_qmf','postgis_gist','tsunami','lmsfc','bmtree'}
METRICS = ['Build_s','IndexSize_MiB','Mean_ms','P95_ms','P99_ms','QPS','PeakMemory_MiB']

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.part')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def read_json(path):
    return json.loads(Path(path).read_text())

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8*1024**2), b''): h.update(block)
    return h.hexdigest()

def atomic_csv(path, rows, fields=None):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.part')
    with tmp.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader(); writer.writerows(rows); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def memory():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, rest = line.split(':', 1); values[key] = int(rest.split()[0])*1024
    vm = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
    return {'available': values['MemAvailable'], 'total': values['MemTotal'],
            'swap_used': values['SwapTotal']-values['SwapFree'],
            'swap_in': int(vm['pswpin']), 'swap_out': int(vm['pswpout']),
            'major_faults': int(vm['pgmajfault'])}

def proc_stats(pid):
    try:
        values = {}
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith(('VmRSS:', 'VmPeak:', 'VmSwap:')):
                key, val, *_ = line.split(); values[key.rstrip(':')] = int(val)*1024
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        values['major_faults'] = int(stat[9])
        return values
    except (OSError, ValueError): return {}

def cgroup_stats(group):
    if not group:
        return {'rss':0,'vm_peak':0,'swap':0,'major_faults':0,'max_process_rss':0}
    root = Path('/sys/fs/cgroup') / group.lstrip('/')
    rss = peak = swap = faults = largest = 0
    if root.is_dir():
        for file in root.rglob('cgroup.procs'):
            try: pids = file.read_text().split()
            except OSError: continue
            for pid in pids:
                s = proc_stats(pid)
                largest = max(largest,s.get('VmRSS',0))
                rss += s.get('VmRSS', 0); peak = max(peak, s.get('VmPeak',0))
                swap += s.get('VmSwap',0); faults += s.get('major_faults',0)
    return {'rss':rss,'vm_peak':peak,'swap':swap,'major_faults':faults,'max_process_rss':largest}

def output_dirs():
    for name in ['00_environment','01_dataset_inventory','02_queries','03_build',
                 '04_correctness','05_performance','06_qmf_diagnostics','07_rankings',
                 '08_figures','09_reports','checkpoints']:
        (OUT/name).mkdir(parents=True,exist_ok=True)
    RUN.mkdir(parents=True,exist_ok=True)

def marker(dataset, phase):
    return OUT/'checkpoints'/dataset/(phase+'.done')

def done(dataset, phase, payload=None, files=()):
    entries = []
    for path in files:
        path=Path(path)
        entries.append({'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)})
    atomic_json(marker(dataset,phase), {'completed_at':time.time(), 'payload':payload,
                                      'files':entries})

def valid(dataset, phase, verify_files=True):
    path=marker(dataset,phase)
    if not path.is_file(): return False
    record=read_json(path)
    if verify_files:
        for entry in record['files']:
            p=Path(entry['path'])
            if not p.is_file() or p.stat().st_size != entry['bytes'] or sha(p)!=entry['sha256']:
                return False
    return True
