#!/usr/bin/env python3
"""Release-maintenance tool: extract portable identities from existing experiment manifests."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    datasets = []
    for row in json.loads((ROOT / 'configs/dataset_downloads.json').read_text())['datasets']:
        original_id = Path(row['file']).stem
        old = a.source_root / 'data_cache/full' / original_id / 'normalized_manifest.json'
        normalized = json.loads(old.read_text())
        old_queries = a.source_root / 'results/four_dataset_paper_protocol_20260911/02_queries' / original_id
        qmeta = json.loads((old_queries / 'query_manifest.json').read_text())
        splits = {}
        for split in ['train','validation','correctness','warmup','performance']:
            path = ROOT / 'experiments/workloads' / original_id / (split + '.csv')
            data = path.read_bytes()
            original = old_queries / (split + '_normalized.csv')
            assert data == original.read_bytes(), original
            with path.open(newline='') as f:
                count = sum(1 for _ in csv.DictReader(f))
            splits[split] = dict(file=path.relative_to(ROOT).as_posix(), count=count,
                                 bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        datasets.append(dict(id=row['id'], original_id=original_id, points=normalized['points'],
            raw_sha256=row['sha256'], normalized_sha256=normalized['sha256'],
            normalized_bytes=normalized['bytes'], bounds=normalized['bounds'],
            query_seed=qmeta['seed'], query_splits=splits,
            provenance=dict(normalized_manifest=old.relative_to(a.source_root).as_posix(),
                            query_manifest=(old_queries / 'query_manifest.json').relative_to(a.source_root).as_posix())))
    a.output.write_text(json.dumps(dict(datasets=datasets,
        policy='Identities copied from original manifests; included workload CSVs compared byte for byte'), indent=2) + '\n')
    print(json.dumps(dict(status='PASS', datasets=len(datasets), included_workloads=20)))

if __name__ == '__main__':
    main()
