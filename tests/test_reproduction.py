from pathlib import Path
import gzip
import json
import zipfile

import numpy as np
import pandas as pd
import pytest
import torch

from qcost_repro.data import prepare_points, query_rows, write_queries, QUERY_COUNTS
from qcost_repro.models import load_model, sha256, verify_models
from qcost_repro.index_run import run_index
from qcost_repro.training import prepare_training, load_prepared, train_models
from qcost_repro.validation import verify_plan
from qcost_experiments.ablation.hybrid_optimizer import optimize
from qcost_experiments.selection.hybrid_optimizer import optimize as selection_optimize
from qmapli.wg_qmf.prior import FrozenR4Prior

ROOT = Path(__file__).resolve().parents[1]
MODEL_MANIFEST = json.loads((ROOT / 'models/manifest.json').read_text())


@pytest.mark.parametrize('row', MODEL_MANIFEST['models'], ids=lambda row: row['model_name'])
def test_original_checkpoint_hash_and_model_factory(row):
    path = ROOT / 'models' / row['file']
    assert sha256(path) == row['sha256']
    model, payload = load_model(path)
    assert payload['model_name'] == row['model_name']
    with torch.no_grad():
        result = model(torch.zeros(2, row['scalar_size']), torch.full((2, 7, 4, 4), 1 / 16))
    assert result.shape == (2,)
    assert torch.isfinite(result).all()


def test_all_original_checkpoints_are_manifested():
    assert len(verify_models()) == 15
    assert {p.name for p in (ROOT / 'models').glob('*.pt')} == {r['file'] for r in MODEL_MANIFEST['models']}


@pytest.mark.parametrize('kind', ['csv', 'gowalla', 'geolife', 'skewed'])
def test_dataset_conversion_and_source_ordinal_ids(tmp_path, kind):
    source = None
    if kind == 'csv':
        source = tmp_path / 'raw.csv'
        source.write_text('longitude,latitude\n10,20\n20,40\n30,60\n')
    elif kind == 'gowalla':
        source = tmp_path / 'raw.txt.gz'
        with gzip.open(source, 'wt') as handle:
            handle.write('1\t2010-01-01T00:00:00Z\t20\t10\t5\n2\t2010-01-02T00:00:00Z\t40\t20\t6\n')
    elif kind == 'geolife':
        source = tmp_path / 'raw.zip'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('Geolife/Data/000/a.plt', 'header\n' * 6 + '20,10,0,0,0,0,0\n40,20,0,0,0,0,0\n')
    result = prepare_points(tmp_path / 'prepared', source, kind=kind,
        x_column='longitude', y_column='latitude', count=32)
    frame = pd.read_csv(tmp_path / 'prepared/points.csv')
    assert np.array_equal(frame.id.to_numpy(), np.arange(result['point_count']))
    assert frame[['x', 'y']].to_numpy().min() >= 0
    assert frame[['x', 'y']].to_numpy().max() <= 1
    assert sha256(tmp_path / 'prepared/points.csv') == result['normalized_sha256']
    with pytest.raises(FileExistsError):
        prepare_points(tmp_path / 'prepared', source, kind=kind,
            x_column='longitude', y_column='latitude', count=32)


def test_invalid_coordinates_are_not_silently_removed(tmp_path):
    source = tmp_path / 'raw.csv'
    source.write_text('x,y\n0,1\nNaN,2\n')
    with pytest.raises(ValueError, match='Nonfinite'):
        prepare_points(tmp_path / 'output', source)


def test_frozen_workload_counts_and_seed_are_deterministic():
    first, second = query_rows(), query_rows()
    assert first == second
    assert {key: len(rows) for key, rows in first.items()} == QUERY_COUNTS
    assert len({row['query_id'] for rows in first.values() for row in rows}) == 6300
    groups = pd.Series(row['selectivity_group'] for row in first['performance']).value_counts().to_dict()
    assert groups == dict(S1=1000, S2=1000, S3=1000)
    assert first != query_rows(seed=123)


@pytest.fixture(scope='module')
def prepared_training(tmp_path_factory):
    root = tmp_path_factory.mktemp('repro_training')
    prepare_training(root / 'inputs', smoke=True)
    return root


def test_training_splits_are_isolated_and_reload_without_pickle(prepared_training):
    dev = load_prepared(prepared_training / 'inputs/development.npz')
    confirm = load_prepared(prepared_training / 'inputs/confirmatory.npz')
    assert dev.scalar.shape[-1] == 46
    assert not (set(dev.groups.root_id) & set(confirm.groups.root_id))
    assert set(dev.groups.model_split) == {'train', 'validation'}
    assert set(confirm.groups.model_split) == {'test'}
    train = np.flatnonzero(dev.groups.model_split.to_numpy() == 'train')
    assert np.isfinite(dev.costs['oracle'][train][dev.valid[train]]).all()
    assert np.isinf(dev.costs['test']).all()


def test_new_controller_training_checkpoint_reloads(prepared_training):
    output = prepared_training / 'new_models'
    receipt = train_models(prepared_training / 'inputs/development.npz',
        prepared_training / 'inputs/confirmatory.npz', output, models=['R4', 'CST'], seeds=[0], epochs=1)
    assert receipt['models'] == ['R4', 'CST']
    for name in ['r4', 'cst']:
        model, _ = load_model(output / (name + '_seed0.pt'))
        with torch.no_grad():
            assert torch.isfinite(model(torch.zeros(2, 46), torch.full((2, 7, 4, 4), 1 / 16))).all()


def test_representation_models_have_a_training_entry_point(prepared_training):
    output = prepared_training / 'representations'
    receipt = train_models(prepared_training / 'inputs/development.npz',
        prepared_training / 'inputs/confirmatory.npz', output, models=['R0', 'R1', 'R2', 'R3', 'R4'],
        seeds=[101], epochs=1, representations=True)
    assert len(list(output.glob('*.pt'))) == 5
    assert receipt['representations']


@pytest.mark.parametrize('mode', ['uniform_qmf', 'wg_qmf'])
def test_complete_prepare_build_and_query_workflow(tmp_path, native_build, mode):
    prepare_points(tmp_path / 'points', kind='skewed', count=512)
    write_queries(tmp_path / 'queries', metadata=tmp_path / 'points/metadata.json',
        counts=dict(train=4, validation=2, correctness=4, warmup=2, performance=3))
    receipt = run_index(tmp_path / 'points/points.csv', tmp_path / 'queries', tmp_path / 'run',
        mode=mode, native_library=native_build / 'lib/libqmap_runtime.so', repetitions=1)
    assert receipt['status'] == 'PASS'
    assert receipt['correctness_queries'] == 4
    assert receipt['performance_queries'] == 3
    assert receipt['mean_ms'] > 0
    assert not receipt['historical_paper_measurements']


@pytest.fixture(scope='module')
def optimizer_inputs():
    points = np.random.default_rng(37).random((2048, 2))
    queries = np.asarray([[0., 0., .25, .8], [.1, .2, .9, .7], [0., 0., 1., 1.]])
    scorer = FrozenR4Prior(ROOT / 'models/r4.pt')
    return points, queries, scorer


@pytest.mark.parametrize('options', [{}, dict(method='M4'), dict(enable_cache=False),
    dict(enable_incumbent_feedback=False), dict(direct_enumeration=True)])
def test_original_ablation_variants_return_legal_exact_plans(optimizer_inputs, options):
    points, queries, scorer = optimizer_inputs
    result = optimize(points, queries, scorer, h=2, k=2, trace=False, **options)
    legal, cost = verify_plan(result['plan'], points, queries)
    assert legal and result['stats']['proven_optimal']
    assert cost == pytest.approx(result['stats']['selected_cost'], rel=1e-12)


@pytest.mark.parametrize('method,feedback', [('M8', True), ('M4', True), ('M8', False), ('M4', False)])
def test_instrumented_selection_variants(optimizer_inputs, method, feedback):
    points, queries, scorer = optimizer_inputs
    result = selection_optimize(points, queries, scorer, method=method,
        enable_incumbent_feedback=feedback, h=2, k=2, diagnostic=True, trace=False)
    legal, cost = verify_plan(result['plan'], points, queries)
    assert legal and result['stats']['proven_optimal']
    assert cost == pytest.approx(result['stats']['selected_cost'], rel=1e-12)
    assert 'observer' in result


def test_frozen_reference_files_are_byte_identical():
    nodes = json.loads((ROOT / 'configs/NODE_MANIFEST.json').read_text())
    assert len(nodes) == 80
    for node in nodes:
        assert sha256(ROOT / node['Reference_File']) == node['Reference_SHA256']
