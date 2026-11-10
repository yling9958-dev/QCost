"""Bounded-memory input conversion and the frozen full-scale query generator."""

from pathlib import Path
import argparse
import csv
import json
import math
import zipfile

import numpy as np
import pandas as pd

from .models import sha256

SEED = 20260910
QUERY_COUNTS = dict(train=1000, validation=1000, correctness=1000, warmup=300, performance=3000)
COORDINATES = ['xmin', 'ymin', 'xmax', 'ymax']
QUERY_COLUMNS = ['query_id', 'selectivity_group', 'split', *COORDINATES, 'expected_count']


def point_chunks(source, *, kind='csv', x_column='x', y_column='y',
                 limit=None, count=100000, seed=SEED, power=9., chunk_size=250000):
    if limit is not None and limit < 1:
        raise ValueError('The row limit must be positive')
    if kind == 'skewed':
        if count < 2 or power < 1 or not math.isfinite(power):
            raise ValueError('Skewed generation requires count >= 2 and finite power >= 1')
        rng = np.random.default_rng(seed)

        def synthetic():
            for start in range(0, count, chunk_size):
                values = rng.random((min(chunk_size, count - start), 2))
                values[:, 1] **= power
                yield values
        chunks = synthetic()
    elif kind == 'geolife':
        def trajectories():
            with zipfile.ZipFile(source) as archive:
                names = sorted(name for name in archive.namelist() if name.lower().endswith('.plt'))
                if not names:
                    raise ValueError('No GeoLife .plt trajectories found')
                for name in names:
                    with archive.open(name) as handle:
                        for frame in pd.read_csv(handle, skiprows=6, header=None, usecols=[0, 1],
                                                 dtype=np.float64, chunksize=chunk_size):
                            values = frame[[1, 0]].to_numpy()
                            if ((np.abs(values[:, 0]) > 180) | (np.abs(values[:, 1]) > 90)).any():
                                raise ValueError('Invalid geographic coordinate; no silent filtering is performed')
                            yield values
        chunks = trajectories()
    elif kind == 'gowalla':
        frames = pd.read_csv(source, sep='\t', header=None, usecols=[2, 3],
                             dtype=np.float64, chunksize=chunk_size, compression='infer')
        chunks = (frame[[3, 2]].to_numpy() for frame in frames)
    elif kind == 'csv':
        frames = pd.read_csv(source, usecols=[x_column, y_column], dtype=np.float64,
                             chunksize=chunk_size, float_precision='round_trip')
        chunks = (frame[[x_column, y_column]].to_numpy() for frame in frames)
    else:
        raise ValueError('Unsupported source format: ' + kind)
    consumed = 0
    for values in chunks:
        if limit is not None:
            values = values[:max(0, limit - consumed)]
        if not len(values):
            break
        if not np.isfinite(values).all():
            raise ValueError('Nonfinite coordinate; no rows are silently discarded')
        yield values
        consumed += len(values)
        if limit is not None and consumed >= limit:
            break


def prepare_points(output, source=None, *, kind='csv', x_column='x', y_column='y',
                   limit=None, count=100000, seed=SEED, power=9.):
    if kind != 'skewed' and source is None:
        raise ValueError('An explicit source file is required')
    source = Path(source) if source is not None else None
    initial = (source.stat().st_size, source.stat().st_mtime_ns) if source else None
    options = dict(kind=kind, x_column=x_column, y_column=y_column,
                   limit=limit, count=count, seed=seed, power=power)
    low, high = np.full(2, np.inf), np.full(2, -np.inf)
    total = 0
    for values in point_chunks(source, **options):
        low = np.minimum(low, values.min(axis=0))
        high = np.maximum(high, values.max(axis=0))
        total += len(values)
    if total < 2 or total >= 2 ** 32 or np.any(high <= low):
        raise ValueError('Input must be nondegenerate with 2 <= count < 2**32')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'points.csv'
    offset = 0
    with target.open('x', encoding='ascii', newline='') as handle:
        handle.write('id,x,y\n')
        for values in point_chunks(source, **options):
            normalized = (values - low) / (high - low)
            frame = pd.DataFrame(dict(id=np.arange(offset, offset + len(values), dtype=np.uint32),
                                      x=normalized[:, 0], y=normalized[:, 1]))
            frame.to_csv(handle, header=False, index=False, float_format='%.17g', lineterminator='\n')
            offset += len(values)
    if offset != total or (source and initial != (source.stat().st_size, source.stat().st_mtime_ns)):
        raise ValueError('Source changed during normalization; output is not valid')
    receipt = dict(kind='NEW_PREPARED_INPUT', source=str(source) if source else None,
                   source_sha256=sha256(source) if source else None, format=kind,
                   row_limit=limit, point_count=total, bounds=[*low.tolist(), *high.tolist()],
                   normalized_sha256=sha256(target), normalized_file='points.csv',
                   normalization='float64 affine min-max; source row ordinal is uint32 ID',
                   source_policy='No filtering, deduplication, or replication; GeoLife trajectories sorted by archive member name',
                   generator=dict(seed=seed, count=count, power=power) if kind == 'skewed' else None,
                   historical_processed_input_reconstruction=False)
    (output / 'metadata.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def query_rows(bounds=(0., 0., 1., 1.), *, counts=None, seed=SEED):
    counts = dict(QUERY_COUNTS if counts is None else counts)
    if counts.get('performance', 0) < 3 or counts['performance'] % 3:
        raise ValueError('Performance query count must be a positive multiple of three')
    if any(count < 1 for count in counts.values()):
        raise ValueError('All split counts must be positive')
    low, high = np.asarray(bounds[:2]), np.asarray(bounds[2:])
    if np.any(high <= low):
        raise ValueError('Degenerate query coordinate domain')
    scale = high - low
    rng = np.random.default_rng(seed)
    rows = {}
    for split in ('train', 'validation', 'correctness', 'warmup', 'performance'):
        local = []
        for index in range(counts[split]):
            group = index // (counts['performance'] // 3) if split == 'performance' else index % 3
            aspect = float(rng.choice([.5, 1., 2.]))
            area = [.0001, .001, .01][group]
            size = np.asarray([math.sqrt(area * aspect), math.sqrt(area / aspect)])
            center = rng.random(2)
            rectangle = np.r_[np.maximum(center - size / 2, 0), np.minimum(center + size / 2, 1)]
            f32 = rectangle.astype(np.float32)
            snapped = (f32.astype(np.float64) + np.nextafter(f32, np.float32(np.inf)).astype(np.float64)) / 2
            snapped[rectangle == 0] = 0.
            snapped[rectangle == 1] = 1.
            raw = snapped * np.tile(scale, 2) + np.tile(low, 2)
            normalized = (raw - np.tile(low, 2)) / np.tile(scale, 2)
            local.append(dict(query_id=f'{split}-{index:05d}', selectivity_group=f'S{group + 1}',
                split=split, **dict(zip(COORDINATES, map(float, normalized))), expected_count=''))
        rows[split] = local
    return rows


def write_queries(output, *, metadata=None, counts=None, seed=SEED):
    bounds = json.loads(Path(metadata).read_text())['bounds'] if metadata else (0., 0., 1., 1.)
    rows = query_rows(bounds, counts=counts, seed=seed)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for split, values in rows.items():
        with (output / (split + '.csv')).open('x', encoding='ascii', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=QUERY_COLUMNS, lineterminator='\n')
            writer.writeheader()
            writer.writerows(values)
    receipt = dict(seed=seed, counts={key: len(value) for key, value in rows.items()},
                   historical_generator=True, historical_workload_identity_verified=False,
                   files={p.name: sha256(p) for p in sorted(output.glob('*.csv'))},
                   semantics='PCG64, clipped uniform centers, aspect .5/1/2, float32 midpoint boundaries')
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--format', choices=['csv', 'geolife', 'gowalla', 'skewed'], default='csv')
    prepare.add_argument('--source', type=Path)
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--x-column', default='x')
    prepare.add_argument('--y-column', default='y')
    prepare.add_argument('--limit', type=int)
    prepare.add_argument('--points', type=int, default=100000)
    prepare.add_argument('--seed', type=int, default=SEED)
    prepare.add_argument('--power', type=float, default=9.)
    queries = commands.add_parser('queries')
    queries.add_argument('--metadata', type=Path)
    queries.add_argument('--output', type=Path, required=True)
    queries.add_argument('--seed', type=int, default=SEED)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare_points(args.output, args.source, kind=args.format,
            x_column=args.x_column, y_column=args.y_column, limit=args.limit,
            count=args.points, seed=args.seed, power=args.power)
    else:
        result = write_queries(args.output, metadata=args.metadata, seed=args.seed)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
