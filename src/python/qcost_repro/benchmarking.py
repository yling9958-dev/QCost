"""Shared correctness and timing adapter for newly generated native index runs."""
import csv
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from .data import COORDINATES
from .native import RuntimeIndex

def benchmark(library, index, method, points, ids, query_root, output, repetitions=5):
    if repetitions < 1:
        raise ValueError('repetitions must be positive')
    output = Path(output)
    truth_points = np.asarray(points, dtype=np.float32)
    ids = np.asarray(ids)
    frames = {s: pd.read_csv(Path(query_root) / (s + '.csv'))
              for s in ['correctness', 'warmup', 'performance']}
    timings = []
    with RuntimeIndex(library, index, method) as engine:
        for rect in frames['correctness'][COORDINATES].to_numpy(float):
            expected = ids[(truth_points[:, 0] >= rect[0]) & (truth_points[:, 1] >= rect[1]) &
                           (truth_points[:, 0] <= rect[2]) & (truth_points[:, 1] <= rect[3])]
            observed, _ = engine.query(rect)
            assert np.array_equal(np.sort(observed), np.sort(expected)), 'Returned ID-set mismatch'
            assert engine.count(rect)[0] == len(expected), 'Range count mismatch'
        for rect in frames['warmup'][COORDINATES].to_numpy(float):
            engine.count(rect)
        with (output / 'timings.csv').open('x', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['repetition', 'query_id', 'selectivity_group', 'latency_ns', 'count', 'candidates'])
            for repeat in range(repetitions):
                for row in frames['performance'].itertuples(index=False):
                    start = time.perf_counter_ns()
                    count, candidates = engine.count([row.xmin, row.ymin, row.xmax, row.ymax])
                    elapsed = time.perf_counter_ns() - start
                    timings.append(elapsed)
                    writer.writerow([repeat, row.query_id, row.selectivity_group, elapsed, count, candidates])
    values = np.asarray(timings, dtype=float)
    result = dict(status='PASS', method=method, correctness_queries=len(frames['correctness']),
                  performance_queries=len(frames['performance']), repetitions=repetitions,
                  mean_ms=float(values.mean() / 1e6), p95_ms=float(np.percentile(values, 95) / 1e6),
                  p99_ms=float(np.percentile(values, 99) / 1e6), qps=float(1e9 / values.mean()),
                  timing_scope='Warm native count through ctypes, including FFI; excludes I/O and truth checks',
                  historical_paper_measurements=False)
    (output / 'query_metrics.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
