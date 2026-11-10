#!/usr/bin/env python3
"""Verify frozen external CSVs, normalize using the retained converter, and prepare queries."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
from qcost_repro.data import prepare_points, write_queries
from qcost_repro.models import sha256
from qcost_repro.frozen_inputs import identity, copy_workloads

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--datasets', nargs='+', default=['geolife', 'gowalla', 'nyc_taxi', 'skewed_2d'])
    p.add_argument('--limit', type=int, help='Explicit development prefix; disables FULL identity claims')
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    inventory = json.loads((ROOT / 'configs/dataset_downloads.json').read_text())['datasets']
    by_id = {r['id']: r for r in inventory}
    if any(d not in by_id for d in a.datasets) or len(set(a.datasets)) != len(a.datasets):
        p.error('Unknown or repeated dataset')
    for name in a.datasets:
        row = by_id[name]
        source = a.raw_root / row['file']
        if not source.is_file():
            p.error(f'Missing external input: {source}; download URL: {row["url"]}')
        with source.open() as f:
            if f.readline().strip() != 'x,y':
                raise ValueError(f'Expected x,y header: {source}')
        if a.limit is None:
            if source.stat().st_size != row['bytes'] or sha256(source) != row['sha256']:
                raise ValueError(f'FULL dataset byte/hash mismatch: {source}')
        if a.check_only:
            print(json.dumps(dict(dataset=name, status='PASS', full_identity_checked=a.limit is None)))
            continue
        output = a.output / name
        meta = prepare_points(output / 'points', source, limit=a.limit)
        if a.limit is None and meta['point_count'] != row['points']:
            raise ValueError('Frozen dataset point count mismatch')
        if a.limit is None:
            frozen = identity(name)
            if meta['normalized_sha256'] != frozen['normalized_sha256'] or meta['bounds'] != frozen['bounds']:
                raise ValueError('Prepared data differs from frozen normalized FULL input; do not run FULL')
            workload = copy_workloads(name, output / 'queries')
        else:
            workload = write_queries(output / 'queries', metadata=output / 'points/metadata.json')
        receipt = dict(dataset=name, raw_identity_checked=a.limit is None,
                       development_prefix=a.limit, metadata=meta, workload=workload,
                       historical_workload_files_verified=a.limit is None)
        (output / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(dict(dataset=name, points=meta['point_count'], status='PASS')))

if __name__ == '__main__':
    main()
