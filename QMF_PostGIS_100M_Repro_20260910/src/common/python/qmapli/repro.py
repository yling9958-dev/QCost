"""Relocation-safe transport around the frozen builder and benchmark harness."""
import argparse
import csv
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import numpy as np
import pandas as pd
import yaml

from .postgis_100m_pilot import runner,analysis,protocol
from .postgis_100m_pilot.data import select_geolife_prefix

ROOT=Path(os.environ['REPRO_ROOT'])
WORK=Path(os.environ['QMF_RUNTIME'])
OUTPUT=WORK/'results/current'
DATA_SHA='56a07a638db478485ba5e78ff45bc7300987ef45d7d4a319666a5dabbcaa555e'
FULL_SHA='98619de96d873e54587ee8cdec9b20162e077b33305b420075494992abbe5c1a'
QUERY_SHA='50c6e29f5a24188814a82a6f1541be5a64a5a9a7d3923659c3f289b02d0f4259'
TREE_SHA='a7c540d4d5f8e1b34e7508d2be921741203cc13667403fa8b7df587e03696230'
INDEX_SHA='12bbd47ef650888b67e042002d794e75de64ec5d91c0c2476eded5d85e577282'

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def config():
    cfg=protocol.load_config()
    cfg['paths'].update(work_root=str(WORK),output=str(OUTPUT))
    cfg['dataset']['source']=str(WORK/'geolife_100m.csv')
    runner.PRIMARY_METHODS=protocol.PRIMARY_METHODS
    analysis.PRIMARY_METHODS=protocol.PRIMARY_METHODS
    runner.QUERY_READY_PERSISTENCE['rtree']=False
    OUTPUT.mkdir(parents=True,exist_ok=True)
    return cfg

def verify_stage_a():
    record=json.loads((ROOT/'expected/stage_a_verification.json').read_text())
    assert record['verified']==37 and record['failed']==0
    assert len((ROOT/'expected/stage_a_original.sha256').read_text().splitlines())==37
    assert protocol.sha256_file(ROOT/'config/r4.pt')==protocol.load_config()['qmf']['r4_checkpoint_sha256']
    return 'SOURCE_37_37_ATTESTED; PACKAGED_R4_HASH_PASS'

def environment():
    cfg=config()
    verify_stage_a()
    assert protocol.sha256_file(ROOT/'queries/geolife_100m_queries.csv')==QUERY_SHA
    expected={line.split('==',1)[0]:line.split('==',1)[1] for line in (ROOT/'environment/python_requirements.lock').read_text().splitlines() if '==' in line and not line.startswith('#')}
    mismatches=[]
    for name,version in expected.items():
        actual=importlib.metadata.version(name)
        if actual!=version: mismatches.append(f'{name}: expected {version}, actual {actual}')
    version=subprocess.check_output(['pg_config','--version'],text=True).strip()
    if version!='PostgreSQL 14.24 (Ubuntu 14.24-0ubuntu0.22.04.1)' and '14.24' not in version:
        mismatches.append(version)
    dump(WORK/'environment_check.json',{'python_mismatches':mismatches,'postgres':version})
    if mismatches: raise RuntimeError('ENVIRONMENT_MISMATCH: '+str(mismatches))
    print('Environment and frozen checkpoint/query checks PASS')

def data():
    source=ROOT/'data/frozen/geolife_100m.csv'
    if not source.is_file():
        raise RuntimeError(
            'LOCAL_FROZEN_DATASET_REQUIRED: data/frozen/geolife_100m.csv is missing; '
            'public-light users must explicitly run data/recovery/fetch_geolife.sh'
        )
    if source.stat().st_size != 104857576 or protocol.sha256_file(source)!=DATA_SHA:
        raise ValueError('LOCAL_FROZEN_DATASET_MISMATCH')
    target=WORK/'geolife_100m.csv'
    if target.is_file():
        if target.stat().st_size != 104857576 or protocol.sha256_file(target)!=DATA_SHA:
            raise ValueError('RUNTIME_FROZEN_DATASET_MISMATCH')
        return
    with source.open('rb') as src,target.open('xb') as dst:
        remaining=104857576
        while remaining:
            block=src.read(min(8*1024**2,remaining))
            if not block: raise ValueError('truncated frozen source')
            dst.write(block); remaining-=len(block)
    assert protocol.sha256_file(target)==DATA_SHA

def install_sql():
    original=(ROOT/'src/postgres/qmap_benchmark--1.0.sql').read_text()
    library=WORK/'extension/qmap_benchmark'
    sql=original.replace('MODULE_PATHNAME',str(library))
    # Fresh dedicated DB; repeated setup must not replace functions used elsewhere.
    exists=subprocess.check_output(['psql','-X','-Atc',"SELECT count(*) FROM pg_proc WHERE proname='qmap_range_count'"],text=True).strip()
    if exists=='0': subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1'],input=sql,text=True,check=True)
    actual=subprocess.check_output(['psql','-X','-Atc','SELECT PostGIS_Lib_Version()'],text=True).strip()
    if actual!='3.2.0': raise RuntimeError('PostGIS version mismatch: '+actual)

def prepare():
    cfg=config(); data()
    metadata=select_geolife_prefix(cfg,WORK)
    assert metadata['point_count']==4197223 and metadata['unique_coordinate_count']==3956264
    assert metadata['selected_prefix_sha256']==DATA_SHA
    golden=json.loads((ROOT/'data/normalized_hashes.json').read_text())
    assert metadata['normalized_points_sha256']==golden['normalized_points_sha256']
    assert metadata['raw_points_sha256']==golden['raw_points_sha256']
    qdir=WORK/'queries'; qdir.mkdir(exist_ok=True)
    for p in (ROOT/'queries').glob('*_normalized.csv'): shutil.copy2(p,qdir/p.name)
    prepared={'dataset':metadata,'queries':{'combined_sha256':QUERY_SHA}}
    dump(WORK/'prepare_status.json',prepared)
    runner._load_postgis_table(cfg,metadata,WORK)
    print('Dataset and exact normalized-query files prepared without query generation')

def install_tree_audit(destination):
    from .indexes.qmap_nai.index import PrefixHybridIndex
    previous=PrefixHybridIndex.build
    def build(self,*args,**kwargs):
        result=previous(self,*args,**kwargs)
        parents={child.node_id:node.node_id for node in self.nodes for child in node.children}
        rows=[]
        for node in sorted(self.nodes,key=lambda n:n.node_id):
            rows.append({'node_id':node.node_id,'parent_id':parents.get(node.node_id,-1),
                'axis':node.split_action.axis if node.children else -1,
                'threshold':float(node.threshold).hex() if node.children else '',
                'left_child':node.children[0].node_id if node.children else -1,
                'right_child':node.children[1].node_id if node.children else -1,
                'is_leaf':int(not node.children),'point_start':node.storage_start,'point_end':node.storage_end,
                'bbox':'|'.join(float(v).hex() for v in node.mbr)})
        pd.DataFrame(rows).to_csv(destination,index=False,lineterminator='\n')
        if protocol.sha256_file(destination)!=TREE_SHA: raise RuntimeError('LOGICAL_TREE_SHA_MISMATCH')
        return result
    PrefixHybridIndex.build=build

def verify_built_indexes():
    builds=pd.read_csv(OUTPUT/'baseline_build_status.csv')
    for row in builds[builds.runtime_method=='qmap_uniform_qmf'].itertuples():
        assert row.status=='BUILT'
        assert protocol.sha256_file(Path(row.index_path))==INDEX_SHA
        assert protocol.sha256_file(Path(row.index_path).parent/'tree_decision_manifest.csv')==TREE_SHA

def build():
    runner.build(config()); verify_built_indexes()

def benchmark():
    runner.benchmark(config())

def quick():
    cfg=config(); cfg['benchmark']['build_repetitions']=1
    # The frozen correctness SQL uses PostGIS as its exact reference. Full mode
    # builds GiST first; quick mode must provide the same reference access path.
    reference=runner._build_postgis(cfg,WORK)
    assert reference[0]['status']=='BUILT'
    indexroot=WORK/'indexes'; indexroot.mkdir(exist_ok=True)
    rows=runner._build_qmf(cfg,runner._read_prepared(WORK),WORK,indexroot)
    runner._write_build_tables(OUTPUT,rows)
    verify_built_indexes()
    cfg['benchmark']['query_repetitions']=1
    runner.PRIMARY_METHODS=(('QMF-Index','qmap_uniform_qmf'),)
    original=runner._valid_builds
    runner._valid_builds=lambda _: {'qmap_uniform_qmf':'BUILT'}
    try: runner.benchmark(cfg)
    finally: runner._valid_builds=original
    results=pd.read_csv(OUTPUT/'correctness_results.csv')
    assert len(results)==5000 and results.exact.eq(1).all() and results.count_exact.eq(1).all()
    assert results.missing.sum()==0 and results.extra.sum()==0
    run=pd.read_csv(OUTPUT/'benchmark_run_status.csv').iloc[0]
    fairness=json.loads(run.fairness_json)
    assert fairness['load_count']==1
    for name in ('query_reload_count','query_rebuild_count','query_python_count','query_quantum_count','query_training_count','query_external_process_count'):
        assert fairness[name]==0
    raw=pd.read_csv(OUTPUT/'query_latency_raw.csv')
    from .postgis_100m_pilot.analysis import _aggregate_query
    dump(OUTPUT/'quick_result.json',{'quick':'PASS','full':'NOT_RUN', 'correctness':5000,
        'missing':0,'extra':0,'tree_sha':TREE_SHA,'index_sha':INDEX_SHA,
        'build_seconds':rows[0]['build_seconds'],'index_size_mib':rows[0]['serialized_bytes']/2**20,
        'peak_memory_mib':max(rows[0]['peak_rss_kib'],int(run.total_peak_rss_kib))/1024,
        'fairness':fairness,
        'metrics_one_repetition_only':_aggregate_query(raw),
        'performance_reproduction':'NOT_EVALUATED_QUICK_MODE','no_online_qmf':True})
    print('QUICK_REPRO=PASS; FULL_PERFORMANCE_REPRO=NOT_EVALUATED')

def analyze():
    cfg=config(); _,statuses=analysis._status_maps(OUTPUT)
    correctness=analysis._correctness_summary(OUTPUT,statuses)
    query,_=analysis._query_tables(OUTPUT,correctness)
    analysis._fairness(OUTPUT)
    analysis._primary_table(OUTPUT,correctness,query)

def compare():
    cfg=config()
    expected=pd.read_csv(ROOT/'expected/primary_7_metric_table.csv').set_index('Method')
    current=pd.read_csv(OUTPUT/'primary_7_metric_table.csv').set_index('Method')
    if set(current.index)!=set(expected.index): raise ValueError('METHOD_SET_MISMATCH')
    tolerances={'BuildTime_s':.25,'IndexSize_MiB':.001,'MeanLatency_ms':.20,'P95Latency_ms':.25,'P99Latency_ms':.30,'QPS':.20,'PeakMemory_MiB':.20}
    rows=[]
    for method in expected.index:
        for metric,tolerance in tolerances.items():
            ref=expected.loc[method,metric]; got=current.loc[method,metric]
            if pd.isna(ref): passed=pd.isna(got); change=None
            else: change=float(got/ref-1); passed=bool(np.isfinite(change) and abs(change)<=tolerance)
            rows.append({'method':method,'metric':metric,'relative_difference':change,'tolerance':tolerance,'pass':passed})
    rank_pass=all(current.loc['QMF-Index','Rank_'+name]==1 for name in ('Size','Mean','P95','P99','QPS'))
    functional=bool(current.Correctness.eq('VALID').all())
    verify_built_indexes()
    dump(OUTPUT/'reproduction_comparison.json',{'functional':'PASS' if functional else 'FAIL',
        'performance':'PASS' if rank_pass and all(r['pass'] for r in rows) else 'PERFORMANCE_REPRODUCTION_MISMATCH',
        'ranking_pass':bool(rank_pass),'metric_comparisons':rows})
    if not functional: raise RuntimeError('FUNCTIONAL_REPRODUCTION_FAILED')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=['environment','data','install-sql','prepare','build','benchmark','quick','analyze','compare'])
    args=parser.parse_args(); globals()[args.phase.replace('-','_')]()
