"""Focused functional contracts for the portable frozen reproduction package."""
import json
from pathlib import Path
import os

import numpy as np
import pandas as pd
import pytest
import yaml

from qmapli import repro
from qmapli.postgis_100m_pilot import protocol,analysis
from qmapli.wg_qmf.index import QWBuildConfig

def test_stage_a_integrity():
    assert 'R4_HASH_PASS' in repro.verify_stage_a()

def test_stage_a_verification_does_not_change_quick_registry(monkeypatch):
    methods=(('QMF-Index','qmap_uniform_qmf'),)
    monkeypatch.setattr(repro.runner,'PRIMARY_METHODS',methods)
    repro.verify_stage_a()
    assert repro.runner.PRIMARY_METHODS==methods

def test_frozen_qmf_config():
    cfg=repro.config()['qmf']; model=QWBuildConfig()
    assert cfg['top_k']==model.top_k==4
    assert cfg['lookahead_depth']==model.lookahead_depth==3
    assert cfg['minimum_lookahead_points']==model.minimum_lookahead_points==4096
    assert cfg['max_depth']==model.max_depth==8
    assert cfg['min_leaf_size']==model.min_leaf_size==256
    assert cfg['max_leaves']==model.max_leaves==128
    assert cfg['search_mode']=='uniform_qmf'
    assert cfg['maximum_configurations']==16384
    assert cfg['receding_horizon_root_commit'] is True
    assert cfg['online_quantum_execution'] is False
    canonical=yaml.safe_load((repro.ROOT/'config/qmf_frozen_config.yaml').read_text())
    for name in ('top_k','lookahead_depth','search_mode','maximum_configurations',
                 'receding_horizon_root_commit','online_quantum_execution'):
        assert canonical[name]==cfg[name]

def test_dataset_sha():
    path=repro.ROOT/'data/frozen/geolife_100m.csv'
    if not path.exists(): pytest.skip('public-light package omits licensed frozen input')
    assert path.stat().st_size==104857576
    assert protocol.sha256_file(path)==repro.DATA_SHA

def test_query_sha():
    assert protocol.sha256_file(repro.ROOT/'queries/geolife_100m_queries.csv')==repro.QUERY_SHA
    for row in pd.read_csv(repro.ROOT/'queries/query_manifest.csv').itertuples():
        assert protocol.sha256_file(repro.ROOT/'queries'/row.file)==row.sha256

def test_official_dataset_recovery_manifest():
    manifest=json.loads((repro.ROOT/'data/dataset_manifest.json').read_text())
    order=repro.ROOT/'data/recovery/geolife_plt_order.txt'
    assert manifest['official_archive_sha256']=='1107c5ac064d0a23c8d021a8736a77e53abc75b227062e6260342c6a8d86bdb6'
    assert manifest['trajectory_order_count']==len(order.read_text().splitlines())==18670
    assert manifest['trajectory_order_sha256']==protocol.sha256_file(order)
    assert manifest['sha256']==repro.DATA_SHA

def test_tree_sha_reference():
    assert protocol.sha256_file(repro.ROOT/'expected/tree_decision_manifest.csv')==repro.TREE_SHA

def test_metric_definitions():
    assert [name for name,_ in protocol.PRIMARY_METRICS]==['BuildTime_s','IndexSize_MiB','MeanLatency_ms','P95Latency_ms','P99Latency_ms','QPS','PeakMemory_MiB']
    frame=pd.DataFrame({'latency_ns':[1000000,2000000,3000000]})
    values=analysis._aggregate_query(frame)
    assert values['MeanLatency_ms']==2
    assert values['QPS']==500

def test_final_method_set():
    assert [runtime for _,runtime in protocol.PRIMARY_METHODS]==['qmap_uniform_qmf','postgis_gist','lisa','flood','tsunami','lmsfc','bmtree','rtree']

def test_persistent_size_caveat():
    frame=pd.read_csv(repro.ROOT/'expected/primary_7_metric_table.csv')
    assert frame.IndexSize_MiB.notna().sum()==5
    assert set(frame[frame.IndexSize_MiB.isna()].Method)=={'LISA','Flood','Boost-R*-tree'}

def test_expected_ranking():
    frame=pd.read_csv(repro.ROOT/'expected/primary_7_metric_table.csv').set_index('Method')
    assert [frame.loc['QMF-Index','Rank_'+name] for name in ('Build','Size','Mean','P95','P99','QPS','Memory')]==[8,1,1,1,1,1,5]

def test_r4_checkpoint_is_only_inference_model():
    import torch
    from qmapli.repro_stage_a import create_final_model
    payload=torch.load(repro.ROOT/'config/r4.pt',weights_only=False,map_location='cpu')
    model=create_final_model('R4',len(payload['scalar_mean']),0)
    model.load_state_dict(payload['model'],strict=True)
    with pytest.raises(ValueError): create_final_model('AQ',len(payload['scalar_mean']),0)

def test_local_module_dependencies():
    import sys
    from qmapli.wg_qmf import build_static_qw_index
    root=(repro.ROOT/'src/common/python').resolve()
    for name,module in sys.modules.copy().items():
        if name.startswith('qmapli') and getattr(module,'__file__',None):
            assert Path(module.__file__).resolve().is_relative_to(root)

def test_postgres_correctness_and_no_online_qmf():
    path=repro.OUTPUT/'correctness_results.csv'
    if not path.exists(): pytest.skip('run --quick to build and query through PostgreSQL')
    frame=pd.read_csv(path)
    assert frame.exact.eq(1).all() and frame.count_exact.eq(1).all()
    assert frame.missing.sum()==0 and frame.extra.sum()==0
    for _,group in frame.groupby('method'): assert len(group)==5000
    run=pd.read_csv(repro.OUTPUT/'benchmark_run_status.csv')
    for row in run.itertuples():
        if row.runtime_method=='postgis_gist': continue
        counters=json.loads(row.fairness_json)
        assert counters['load_count']==1
        for name in ('query_reload_count','query_rebuild_count','query_python_count','query_quantum_count','query_training_count','query_external_process_count'):
            assert counters[name]==0

def test_actual_tree_and_index():
    if not (repro.OUTPUT/'baseline_build_status.csv').exists(): pytest.skip('run --quick first')
    repro.verify_built_indexes()
