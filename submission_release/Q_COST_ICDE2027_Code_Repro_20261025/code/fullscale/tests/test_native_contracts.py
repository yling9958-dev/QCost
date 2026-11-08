"""Small synthetic adapter tests, distinct from frozen full-dataset measurements."""
import csv
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from qmapli import repro

@pytest.mark.parametrize('method',['flood','lisa','tsunami','lmsfc','bmtree','rtree'])
def test_baseline_exact_ids(method,tmp_path):
    executable=repro.WORK/'build/bin/qmap_build_index'
    if not executable.exists(): pytest.skip('build native targets first')
    rng=np.random.default_rng(20260909)
    points=rng.uniform(size=(2048,2)).astype(np.float32)
    points_path=tmp_path/'points.csv'
    pd.DataFrame({'id':np.arange(len(points)),'x':points[:,0],'y':points[:,1]}).to_csv(points_path,index=False,float_format='%.17g')
    rectangles=rng.uniform(size=(32,4)).reshape(-1,2,2)
    lo=rectangles.min(axis=1); hi=rectangles.max(axis=1)
    q=tmp_path/'queries.csv'
    pd.DataFrame({'query_id':np.arange(len(lo)),'selectivity_group':'test','split':'train','xmin':lo[:,0],'ymin':lo[:,1],'xmax':hi[:,0],'ymax':hi[:,1]}).to_csv(q,index=False,float_format='%.17g')
    index=tmp_path/'index.idx'
    command=[str(executable),'--method',method,'--points',str(points_path),'--train-queries',str(q),'--validation-queries',str(q),'--index',str(index),'--output',str(tmp_path/'build.csv')]
    if method=='bmtree':
        from qmapli.postgis_100m_pilot.runner import _prepare_bmtree
        model,_,_=_prepare_bmtree(tmp_path,points_path,q,0,120)
        command += ['--bmtree-model',str(model)]
    subprocess.run(command,check=True,capture_output=True,text=True,timeout=120)
    output=tmp_path/'exact.csv'
    subprocess.run([str(repro.WORK/'build/bin/qmap_static_query'),'--method',method,'--index',str(index),'--queries',str(q),'--output',str(output)],check=True,capture_output=True,text=True,timeout=120)
    for row in csv.DictReader(output.open()):
        ordinal=int(row['query_id'])
        truth=np.flatnonzero(((points>=lo[ordinal])&(points<=hi[ordinal])).all(axis=1)).tolist()
        got=sorted(map(int,row['result_ids'].split(';'))) if row['result_ids'] else []
        assert got==truth

def test_zero_query_core_allocations(tmp_path):
    index=repro.WORK/'indexes/qmap_uniform_qmf.idx'
    if not index.exists(): pytest.skip('run complete QMF build first')
    queries=tmp_path/'frozen_normalized.csv'
    pd.concat([pd.read_csv(repro.ROOT/'queries'/name,float_precision='round_trip') for name in ('warmup_normalized.csv','performance_normalized.csv')]).to_csv(queries,index=False,float_format='%.17g')
    output=tmp_path/'allocation_audit.csv'
    subprocess.run([str(repro.WORK/'build/bin/qmap_profile'),'qmap_uniform_qmf',str(index),str(queries),str(output),'count'],check=True,capture_output=True,text=True,timeout=120)
    values=pd.read_csv(output)
    assert len(values)==15000
    assert values.heap_allocations.eq(0).all()
    assert values.allocated_bytes.eq(0).all()

def test_final_result_parser():
    value=json.loads((repro.ROOT/'expected/expected_result.json').read_text())
    assert value['kind']=='GOLDEN_REFERENCE_NOT_RERUN'
    assert len(value['methods'])==8
    assert float(next(row['MeanLatency_ms'] for row in value['methods'] if row['Method']=='QMF-Index'))>0

def test_actual_persistent_size():
    index=repro.WORK/'indexes/qmap_uniform_qmf.idx'
    if not index.exists(): pytest.skip('run complete QMF build first')
    assert index.stat().st_size/2**20==pytest.approx(80.066906,abs=1e-6)
