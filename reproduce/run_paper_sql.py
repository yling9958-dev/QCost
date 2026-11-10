#!/usr/bin/env python3
"""Compile and execute the unchanged formal libpq correctness/timing client."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--dsn', default=os.environ.get('QCOST_PG_DSN'))
    p.add_argument('--queries', type=Path, required=True, help='Directory with all five original workload splits')
    p.add_argument('--points', type=Path, help='Load a session-owned schema with normalized float32 point semantics')
    p.add_argument('--table', help='Existing schema.table with id,lon,lat,geom(4326); alternative to --points')
    p.add_argument('--method', choices=['postgis_gist','qmap_uniform_qmf','lisa','flood','tsunami','lmsfc','bmtree','rtree'], default='postgis_gist')
    p.add_argument('--index-root', type=Path, default=Path('runs/indexes'))
    p.add_argument('--bounds', nargs=4, type=float, default=[0.,0.,1.,1.], metavar=('XMIN','YMIN','XMAX','YMAX'))
    a = p.parse_args()
    if not a.dsn or bool(a.points) == bool(a.table):
        p.error('Set QCOST_PG_DSN and supply exactly one of --points or --table')
    if a.table and not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*\.[A-Za-z_][A-Za-z_0-9]*', a.table):
        p.error('table must be a plain schema.table identifier')
    import numpy as np
    import pandas as pd
    import psycopg2
    from psycopg2 import sql
    import io
    a.output.mkdir(parents=True, exist_ok=False)
    includedir = subprocess.check_output(['pg_config','--includedir'], text=True).strip()
    libdir = subprocess.check_output(['pg_config','--libdir'], text=True).strip()
    executable = a.output.resolve() / 'qcost_paper_sql'
    subprocess.run(['g++','-std=c++17','-O3','-pthread','-I'+includedir,
                    str(ROOT / 'src/postgres/client/postgres_full.cpp'), '-L'+libdir,
                    '-lpq','-o',str(executable)], check=True)
    combined = a.output / 'all_queries.csv'
    with combined.open('x', newline='') as target:
        writer = None
        for split in ['train','validation','correctness','warmup','performance']:
            with (a.queries / (split+'.csv')).open(newline='') as source:
                reader = csv.DictReader(source)
                if writer is None:
                    writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
                    writer.writeheader()
                writer.writerows(reader)
    owner_schema = 'qcost_run_' + uuid.uuid4().hex
    connection = psycopg2.connect(a.dsn)
    connection.autocommit = True
    created = False
    try:
        if a.points:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(owner_schema)))
                created = True
                table = sql.Identifier(owner_schema, 'points')
                cursor.execute(sql.SQL('CREATE TABLE {} (id bigint, lon double precision, lat double precision, '
                    'geom geometry(Point,4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon,lat),4326)) STORED)').format(table))
                for frame in pd.read_csv(a.points, usecols=['id','x','y'], chunksize=250000, float_precision='round_trip'):
                    frame[['x','y']] = frame[['x','y']].to_numpy().astype(np.float32).astype(float)
                    stream = io.StringIO()
                    frame[['id','x','y']].to_csv(stream, header=False, index=False, float_format='%.17g')
                    stream.seek(0)
                    cursor.copy_expert(sql.SQL('COPY {}(id,lon,lat) FROM STDIN WITH (FORMAT CSV)').format(table), stream)
                cursor.execute(sql.SQL('CREATE INDEX ON {} USING gist(geom)').format(table))
                cursor.execute(sql.SQL('ANALYZE {}').format(table))
            table_name = owner_schema + '.points'
        else:
            table_name = a.table
        for phase in ['correctness','timing']:
            command = [str(executable), '--method',a.method, '--table',table_name,
                '--queries',str(combined.resolve()), '--repetitions','5','--start-repetition','0',
                '--phase',phase,'--conninfo',a.dsn,'--index-root',str(a.index_root.resolve()),
                '--source-xmin',str(a.bounds[0]),'--source-ymin',str(a.bounds[1]),
                '--source-xmax',str(a.bounds[2]),'--source-ymax',str(a.bounds[3]),
                '--correctness-output',str((a.output/'correctness.csv').resolve()),
                '--latency-output',str((a.output/'latency').resolve()),
                '--summary-output',str((a.output/'correctness_summary.json').resolve())]
            # Credentials remain in memory and are never written to a manifest.
            run = subprocess.run(command, capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError(f'Original SQL client failed during {phase}: ' + run.stderr.replace(a.dsn,'[DSN]'))
        result = dict(status='PASS', method=a.method, correctness_queries=1000,
            performance_queries=3000, repetitions=5, timed_samples=15000,
            original_client_source='src/postgres/client/postgres_full.cpp',
            timing_scope='Original C++ libpq prepared count statement, one persistent connection per phase; jit off, no parallel gather',
            historical_full_dataset_identity_verified=False,
            note='Original SQL client and fixed query counts; historical datasets, server settings and index artifacts must still match')
        (a.output/'sql_validation.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2))
    finally:
        if created:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(owner_schema)))
        connection.close()

if __name__ == '__main__':
    main()
