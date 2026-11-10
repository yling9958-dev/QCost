"""Fresh QMF build, exact returned-ID checks, and warmup/timing repetitions."""

from pathlib import Path
import argparse
import csv
import json
import platform
import resource
import subprocess
import time

import numpy as np
import pandas as pd
import torch
import yaml

from qmapli.wg_qmf.index import QWBuildConfig, build_qw_static_index
from qmapli.wg_qmf.point_io import read_points
from .data import COORDINATES
from .models import PROJECT_ROOT, sha256
from .native import RuntimeIndex


def build_native(directory):
    directory = Path(directory).resolve()
    subprocess.run(['cmake', '-S', str(PROJECT_ROOT / 'src/cpp'), '-B', str(directory)], check=True)
    subprocess.run(['cmake', '--build', str(directory), '--parallel', '2'], check=True)
    return directory / 'lib/libqmap_runtime.so'


def run_index(points_file, query_root, output, *, checkpoint=None, mode='uniform_qmf',
              repetitions=5, native_library=None, config=None):
    if repetitions < 1:
        raise ValueError('Repetitions must be positive')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    query_root = Path(query_root)
    checkpoint = Path(checkpoint or PROJECT_ROOT / 'models/r4.pt')
    config = config or yaml.safe_load((PROJECT_ROOT / 'configs/qmf_frozen.yaml').read_text())
    library = Path(native_library) if native_library else build_native(output / 'native')
    point_metadata = Path(points_file).with_name('metadata.json')
    expected_count = None
    if point_metadata.is_file():
        meta = json.loads(point_metadata.read_text())
        if meta.get('normalized_file') == Path(points_file).name:
            if sha256(points_file) != meta['normalized_sha256']:
                raise ValueError('Prepared points SHA-256 mismatch')
            expected_count = meta['point_count']
    points, ids = read_points(points_file, expected_count=expected_count)
    queries = {split: pd.read_csv(query_root / (split + '.csv'))
               for split in ('train', 'correctness', 'warmup', 'performance')}
    training = queries['train'][COORDINATES].to_numpy(dtype=np.float64)
    started = time.perf_counter()
    index = output / 'qmf.idx'
    build_metadata = build_qw_static_index(mode=mode, r4_checkpoint=checkpoint,
        points=points, ids=ids, train_queries=training, output_path=index,
        context_seed=config['context_seed'], beta_leaf=config['beta_leaf'], beta_point=config['beta_point'],
        build_config=QWBuildConfig(max_depth=config['max_depth'], min_leaf_size=config['min_leaf_size'],
            max_leaves=config['max_leaves'], budget_sqrt_factor=config['budget_sqrt_factor'],
            lookahead_depth=config.get('lookahead_depth', 3), top_k=config.get('top_k', 4),
            minimum_lookahead_points=config.get('minimum_lookahead_points', 4096)))
    build_seconds = time.perf_counter() - started
    (output / 'build_metadata.json').write_text(json.dumps(build_metadata, indent=2) + '\n')
    method = 'qmap_uniform_qmf' if mode == 'uniform_qmf' else 'qmap_qw'
    # Quantized float32 coordinates are the native index's stored point semantics.
    # Keep source-order arrays for truth; the builder is allowed to reorder storage.
    del points, ids
    canonical, identifiers = read_points(points_file, expected_count=expected_count)
    canonical = canonical.astype(np.float32)
    latencies = []
    with RuntimeIndex(library, index, method) as runtime:
        for rectangle in queries['correctness'][COORDINATES].to_numpy(dtype=np.float64):
            found, _ = runtime.query(rectangle)
            expected = identifiers[(canonical[:, 0] >= rectangle[0]) & (canonical[:, 1] >= rectangle[1])
                & (canonical[:, 0] <= rectangle[2]) & (canonical[:, 1] <= rectangle[3])]
            if not np.array_equal(np.sort(found), np.sort(expected)):
                raise AssertionError('Exact returned-ID correctness check failed')
            if runtime.count(rectangle)[0] != len(expected):
                raise AssertionError('Count and returned-ID kernels disagree')
        for rectangle in queries['warmup'][COORDINATES].to_numpy(dtype=np.float64):
            runtime.count(rectangle)
        performance = queries['performance']
        with (output / 'timings.csv').open('x', newline='') as handle:
            writer = csv.writer(handle, lineterminator='\n')
            writer.writerow(['repetition', 'query_id', 'selectivity_group', 'latency_ns', 'count', 'candidates'])
            for repetition in range(repetitions):
                for row in performance.itertuples(index=False):
                    started = time.perf_counter_ns()
                    count, candidates = runtime.count([row.xmin, row.ymin, row.xmax, row.ymax])
                    elapsed = time.perf_counter_ns() - started
                    latencies.append(elapsed)
                    writer.writerow([repetition, row.query_id, row.selectivity_group, elapsed, count, candidates])
    latencies = np.asarray(latencies, dtype=np.float64)
    receipt = dict(status='PASS', kind='NEW_QMF_RUN', method=method, build_seconds=build_seconds,
        index_bytes=index.stat().st_size, mean_ms=float(latencies.mean() / 1e6),
        p95_ms=float(np.percentile(latencies, 95) / 1e6), p99_ms=float(np.percentile(latencies, 99) / 1e6),
        qps=float(1e9 / latencies.mean()), process_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        correctness_queries=len(queries['correctness']), warmup_queries=len(queries['warmup']),
        performance_queries=len(queries['performance']), repetitions=repetitions,
        points_sha256=sha256(points_file), checkpoint_sha256=sha256(checkpoint),
        query_files_sha256={p.name: sha256(p) for p in sorted(query_root.glob('*.csv'))},
        environment=dict(python=platform.python_version(), numpy=np.__version__, torch=torch.__version__),
        timing_scope='Warm native count calls through ctypes, including Python/FFI overhead; excludes I/O and truth checks',
        memory_scope='Whole Python process high-water RSS, including input/truth arrays; not the historical paper memory estimator',
        historical_paper_measurements=False)
    (output / 'metrics.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--points', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--mode', choices=['uniform_qmf', 'wg_qmf'], default='uniform_qmf')
    parser.add_argument('--repetitions', type=int, default=5)
    args = parser.parse_args()
    torch.set_num_threads(1)
    print(json.dumps(run_index(args.points, args.queries, args.output, checkpoint=args.checkpoint,
                               mode=args.mode, repetitions=args.repetitions), indent=2))


if __name__ == '__main__':
    main()
