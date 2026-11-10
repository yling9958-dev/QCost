#!/usr/bin/env python3
"""Measure a real PostGIS GiST baseline in a session-owned temporary table."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
import numpy as np
import pandas as pd
from qcost_repro.data import COORDINATES

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--points', type=Path, required=True)
    p.add_argument('--queries', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--dsn', default=os.environ.get('QCOST_PG_DSN'), help='Prefer QCOST_PG_DSN; never written to output')
    p.add_argument('--repetitions', type=int, default=5)
    a = p.parse_args()
    if not a.dsn:
        p.error('Set QCOST_PG_DSN to an experiment database with PostGIS already installed')
    if a.repetitions < 1:
        p.error('repetitions must be positive')
    import psycopg2
    a.output.mkdir(parents=True, exist_ok=False)
    queries = {s: pd.read_csv(a.queries / (s + '.csv')) for s in ['correctness', 'warmup', 'performance']}
    all_points, all_ids = [], []
    with psycopg2.connect(a.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT postgis_version()')
            version = cursor.fetchone()[0]
            cursor.execute('CREATE TEMP TABLE qcost_points (id bigint, x double precision, y double precision, '
                           'geom geometry(Point,0) GENERATED ALWAYS AS (ST_MakePoint(x,y)) STORED) ON COMMIT DROP')
            for chunk in pd.read_csv(a.points, usecols=['id', 'x', 'y'], chunksize=250000, float_precision='round_trip'):
                points = chunk[['x', 'y']].to_numpy().astype(np.float32)
                chunk[['x', 'y']] = points.astype(float)
                buffer = io.StringIO()
                chunk[['id', 'x', 'y']].to_csv(buffer, index=False, header=False, float_format='%.17g')
                buffer.seek(0)
                cursor.copy_expert('COPY qcost_points(id,x,y) FROM STDIN WITH (FORMAT CSV)', buffer)
                all_points.append(points)
                all_ids.append(chunk.id.to_numpy())
            points, ids = np.concatenate(all_points), np.concatenate(all_ids)
            started = time.perf_counter()
            cursor.execute('CREATE INDEX ON qcost_points USING gist (geom)')
            cursor.execute('ANALYZE qcost_points')
            build_seconds = time.perf_counter() - started
            condition = ' FROM qcost_points WHERE geom && ST_MakeEnvelope(%s,%s,%s,%s,0)'
            for rect in queries['correctness'][COORDINATES].to_numpy(float):
                cursor.execute('SELECT id' + condition, tuple(map(float, rect)))
                observed = np.asarray([r[0] for r in cursor.fetchall()])
                expected = ids[(points[:,0]>=rect[0]) & (points[:,1]>=rect[1]) & (points[:,0]<=rect[2]) & (points[:,1]<=rect[3])]
                assert np.array_equal(np.sort(observed), np.sort(expected))
            for rect in queries['warmup'][COORDINATES].to_numpy(float):
                cursor.execute('SELECT count(*)' + condition, tuple(map(float, rect)))
                cursor.fetchone()
            timings = []
            for repeat in range(a.repetitions):
                for rect in queries['performance'][COORDINATES].to_numpy(float):
                    started = time.perf_counter_ns()
                    cursor.execute('SELECT count(*)' + condition, tuple(map(float, rect)))
                    cursor.fetchone()
                    timings.append(time.perf_counter_ns() - started)
    values = np.asarray(timings, float)
    result = dict(status='PASS', method='PostGIS GiST', postgis=version, build_seconds=build_seconds,
                  correctness_queries=len(queries['correctness']), repetitions=a.repetitions,
                  mean_ms=float(values.mean()/1e6), p95_ms=float(np.percentile(values,95)/1e6),
                  p99_ms=float(np.percentile(values,99)/1e6), qps=float(1e9/values.mean()),
                  timing_scope='Single psycopg2 client, execute through fetch; COPY excluded from build time',
                  historical_paper_measurements=False)
    (a.output / 'postgis_metrics.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
