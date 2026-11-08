"""Read-only Flood preflight: never call foreground/new_attempt/perform or a worker."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

import flood_resume as f
import diagnose
import repair_geolife as repair


def inspect():
    results = {}
    values = {}
    lock = None

    def step(name, action, summarize=lambda value: value):
        started = time.monotonic()
        try:
            value = action()
            values[name] = value
            row = {'status': 'PASS', 'value': summarize(value)}
        except Exception as exc:
            row = {'status': 'FAIL', 'exception': repr(exc), 'traceback': traceback.format_exc()}
        row['elapsed_s'] = time.monotonic() - started
        results[name] = row
        print(name, row['status'], f"{row['elapsed_s']:.6f}s", flush=True)

    def acquire():
        nonlocal lock
        # Existing inode only; never replace/delete/create a campaign lock.
        lock = (f.RUNTIME/'campaign.lock').open('r')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return {'acquired': True, 'pid': os.getpid(), 'path': str(f.RUNTIME/'campaign.lock')}

    def stale():
        found = repair.stale_processes(values['ownership'])
        if found:
            raise RuntimeError('Stale benchmark processes: '+repr(found))
        return []

    def memory():
        gate = values['verify_gate']
        required = int(gate['predicted_181m_peak_mib']*1024**2)+f.HOST_EMERGENCY_RESERVE
        available = values['ownership']['host_meminfo']['MemAvailable']
        return {'required_bytes': required, 'available_bytes': available,
                'admitted_now': available >= required, 'if_insufficient': 'WAIT, not method failure'}

    def paths():
        for p in [f.FORMAL/'01_dataset_inventory'/(f.DATASET+'.json'),
                  f.FORMAL/'02_queries'/f.DATASET, f.RUNTIME/'geolife_repair/common/pg_data']:
            if not p.exists():
                raise FileNotFoundError(p)
        return {'new_attempt_called': False, 'perform_called': False,
                'attempt_mount': subprocess.check_output(['findmnt','-T',str(f.ATTEMPTS),'-n','-o','FSTYPE'],text=True).strip(),
                'runtime_mount': subprocess.check_output(['findmnt','-T','/var/tmp','-n','-o','FSTYPE'],text=True).strip()}

    try:
        step('verify_gate', f.verify_gate)
        step('validate_build', f.validate_build)
        step('protected_files', f.protected_files, lambda v: {'count': len(v), 'files': v})
        step('lock', acquire)
        step('ownership', lambda: diagnose.ownership(f.o.SLICE))
        step('stale_processes', stale)
        step('cgroup_policy', lambda: f.o.cgroup_policy.validate(values['ownership']['parent']))
        step('memory_admission', memory)
        step('latest_pass_attempt', f.latest_pass_attempt, lambda v: str(v) if v else None)
        step('new_attempt_paths_dry_validation', paths)
    finally:
        if lock is not None:
            lock.close()
    return {'steps': results, 'first_failing_step': next((k for k,v in results.items() if v['status']=='FAIL'), None),
            'environment': {'PWD': os.getcwd(), **{k: os.environ.get(k) for k in
                ['PATH','PYTHONPATH','HOME','TMPDIR','LD_LIBRARY_PATH','PGHOST','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS']}},
            'full_geoLife_started': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Only a fresh independent /var/tmp diagnostic output is permitted.
    if not str(args.output.resolve()).startswith('/var/tmp/qmf-flood-resume-preflight-'):
        parser.error('Output must be in a dedicated /var/tmp/qmf-flood-resume-preflight-* directory')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(inspect(), handle, indent=2)
        handle.write('\n')
