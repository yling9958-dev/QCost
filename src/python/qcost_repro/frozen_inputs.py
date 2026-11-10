"""Verify and copy the actual small, frozen FULL query workload files."""
import json
from pathlib import Path
import shutil
from .models import sha256

ROOT = Path(__file__).resolve().parents[3]

def identity(dataset):
    rows = json.loads((ROOT / 'configs/input_identities.json').read_text())['datasets']
    return next(row for row in rows if row['id'] == dataset)

def verify_workloads(dataset, directory=None):
    row = identity(dataset)
    for split, record in row['query_splits'].items():
        path = Path(directory) / (split + '.csv') if directory is not None else ROOT / record['file']
        if not path.is_file() or path.stat().st_size != record['bytes'] or sha256(path) != record['sha256']:
            raise ValueError('Frozen workload identity mismatch: ' + str(path))
    return row

def copy_workloads(dataset, output):
    row = verify_workloads(dataset)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for split, record in row['query_splits'].items():
        shutil.copyfile(ROOT / record['file'], output / (split + '.csv'))
    verify_workloads(dataset, output)
    receipt = dict(seed=row['query_seed'], counts={s:r['count'] for s,r in row['query_splits'].items()},
                   historical_workload_identity_verified=True,
                   files={s+'.csv':r['sha256'] for s,r in row['query_splits'].items()})
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
