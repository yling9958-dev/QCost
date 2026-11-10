#!/usr/bin/env python3
"""Unified classical QUICK/FULL workflow. Quantum circuits have an independent entry point."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
from qcost_repro.frozen_inputs import identity, verify_workloads

def call(script, *args):
    subprocess.run([sys.executable, '-B', str(ROOT / 'reproduce' / script), *map(str, args)], check=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['QUICK', 'FULL'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--data-root', type=Path, help='prepare_external.py output')
    p.add_argument('--inputs-root', type=Path, help='Original frozen NODE_ID/input.npz payloads')
    p.add_argument('--tasks', nargs='+', choices=['indexes','search','efficiency','sensitivity','ablation','selection'],
                   default=['indexes','search','efficiency','sensitivity','ablation','selection'])
    a = p.parse_args()
    # Resolve all requested FULL inputs before starting expensive work.
    if a.mode == 'FULL':
        if 'indexes' in a.tasks:
            if not a.data_root:
                p.error('FULL indexes require --data-root')
            source_rows = json.loads((ROOT / 'configs/dataset_downloads.json').read_text())['datasets']
            for row in source_rows:
                folder = a.data_root / row['id']
                meta_path = folder / 'points/metadata.json'
                if not meta_path.is_file():
                    p.error('Missing prepared FULL metadata: ' + str(meta_path))
                meta = json.loads(meta_path.read_text())
                if meta['point_count'] != row['points'] or meta['source_sha256'] != row['sha256'] or meta['row_limit'] is not None:
                    p.error('FULL preparation identity mismatch: ' + str(folder))
                if meta['normalized_sha256'] != identity(row['id'])['normalized_sha256']:
                    p.error('FULL normalized input identity mismatch: ' + str(folder))
                verify_workloads(row['id'], folder / 'queries')
                for split in ['train','validation','correctness','warmup','performance']:
                    if not (folder / 'queries' / (split+'.csv')).is_file():
                        p.error('Missing FULL workload split: ' + str(folder / 'queries' / (split+'.csv')))
        if set(a.tasks) - {'indexes'}:
            if not a.inputs_root:
                p.error('FULL node studies require --inputs-root')
            nodes = json.loads((ROOT / 'configs/NODE_MANIFEST.json').read_text())
            for node in nodes:
                needed = node['Cohort'] == 'Original' or 'selection' in a.tasks
                if needed and not (a.inputs_root / node['Input_File']).is_file():
                    p.error('Missing frozen node: ' + str(a.inputs_root / node['Input_File']))
    a.output.mkdir(parents=True, exist_ok=False)
    call('check_environment.py', '--output', a.output / 'environment.json')
    if a.mode == 'QUICK':
        call('smoke.py', '--output', a.output / 'smoke')
        for task in ['search','efficiency','sensitivity']:
            call('run_studies.py', '--mode', 'QUICK', '--task', task, '--output', a.output / task)
    else:
        for task in a.tasks:
            if task == 'indexes':
                for dataset in ['geolife','gowalla','nyc_taxi','skewed_2d']:
                    source = a.data_root / dataset
                    call('run_index.py', '--points', source / 'points/points.csv', '--queries', source / 'queries',
                         '--output', a.output / dataset, '--repetitions', 5)
            elif task in ['ablation','selection']:
                extra = ['--cohort','Both'] if task == 'selection' else []
                call('run_optimizer.py', '--mode', task, '--inputs-root', a.inputs_root,
                     '--output', a.output / task, *extra)
            else:
                call('run_studies.py', '--mode', 'FULL', '--task', task, '--inputs-root', a.inputs_root,
                     '--output', a.output / task)
    (a.output / 'workflow.json').write_text(json.dumps(dict(status='COMPLETE', mode=a.mode,
        historical_paper_measurements=False, quantum_entry='reproduce/run_quantum.py'), indent=2) + '\n')

if __name__ == '__main__':
    main()
