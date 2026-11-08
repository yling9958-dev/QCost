"""Prepare isolated training tensors and train the original controller family."""

from pathlib import Path
import argparse
import copy
import json

import numpy as np
import pandas as pd
import torch
import yaml

from qmapli.cpsr_vqc.training import fit_cst_normalizer
from qmapli.final_full_scale.controllers import MODEL_NAMES, fit_final_controller
from qmapli.workload_action_interaction.controller import REPRESENTATION_CHANNELS, fit_controller
from qmapli.workload_action_interaction.data import PreparedInteractionData
from qmapli.workload_action_interaction.node_bank import SpatialNode
from .fresh_data import synthetic_nodes, prepare_fresh_data, assert_query_isolation
from .models import PROJECT_ROOT, sha256


def save_prepared(path, data):
    """NPZ contains only numeric arrays and JSON strings, never pickled objects."""
    payload = dict(scalar=data.scalar, spatial=data.spatial, valid=data.valid,
                   groups_json=np.asarray(data.groups.to_json(orient='table', index=False)),
                   hashes_json=np.asarray(data.query_hashes.to_json(orient='table', index=False)))
    for split in ('oracle', 'validation', 'test'):
        payload['costs_' + split] = data.costs[split]
        payload['raw_' + split] = data.raw_metrics[split]
    with Path(path).open('xb') as handle:
        np.savez_compressed(handle, **payload)


def _read_frame(text):
    from io import StringIO
    return pd.read_json(StringIO(str(text)), orient='table')


def load_prepared(path):
    with np.load(path, allow_pickle=False) as data:
        result = PreparedInteractionData(
            scalar=data['scalar'], spatial=data['spatial'], valid=data['valid'],
            costs={key: data['costs_' + key] for key in ('oracle', 'validation', 'test')},
            raw_metrics={key: data['raw_' + key] for key in ('oracle', 'validation', 'test')},
            groups=_read_frame(data['groups_json']), query_hashes=_read_frame(data['hashes_json']),
            preparation_seconds=0.)
    if len(result.scalar) != len(result.groups) or result.scalar.shape[-1] != 46:
        raise ValueError('Prepared tensor schema mismatch')
    return result


def prepare_training(output, *, config=None, smoke=False, geolife_development=None,
                     geolife_confirmatory=None):
    config = copy.deepcopy(config or yaml.safe_load(
        (PROJECT_ROOT / 'configs/training_data.yaml').read_text()))
    if smoke:
        config['data'].update(distributions=['uniform', 'diagonal_band'], points_per_root=256,
            development_seeds=[90, 93], development_train_seeds=[90],
            development_validation_seeds=[93], confirmatory_seeds=[100],
            query_count_per_split_per_workload=4)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    prepared = {}
    for stage, geo in [('development', geolife_development), ('confirmatory', geolife_confirmatory)]:
        nodes = synthetic_nodes(config, stage)
        if geo is not None:
            frame = pd.read_csv(geo, usecols=['x', 'y'])
            points = frame[['x', 'y']].to_numpy(dtype=np.float64)
            if len(points) < 32 or not np.isfinite(points).all():
                raise ValueError('Invalid external GeoLife root')
            uid = f'geolife:external:{stage}:{sha256(geo)[:16]}'
            nodes.append(SpatialNode(dataset='geolife', distribution_type='geolife_external_root',
                root_seed=config['seed'], root_id=uid, node_id=uid + ':root', points=points,
                generation_method='explicit_external_root',
                model_split='validation' if stage == 'development' else 'test'))
        prepared[stage] = prepare_fresh_data(nodes, config, stage=stage)
    assert_query_isolation(*(value.query_hashes for value in prepared.values()))
    for stage, data in prepared.items():
        save_prepared(output / (stage + '.npz'), data)
    receipt = dict(kind='NEW_TRAINING_INPUTS', smoke=smoke,
                   historical_checkpoint_reconstruction=False, config=config,
                   geolife_development_sha256=sha256(geolife_development) if geolife_development else None,
                   geolife_confirmatory_sha256=sha256(geolife_confirmatory) if geolife_confirmatory else None,
                   note='Synthetic protocol is preserved. Exact historical GeoLife root selection is external data.')
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def train_models(development, confirmatory, output, *, models=None, seeds=None, epochs=None,
                 config=None, representations=False):
    if config is None and representations:
        representation = yaml.safe_load((PROJECT_ROOT / 'configs/representation_training.yaml').read_text())
        stage = representation['stage_a']
        config = dict(seed=representation['seed'], controller=dict(
            epochs=stage['epochs'], learning_rate=stage['learning_rate'], batch_size=stage['batch_size'],
            early_stopping_patience=stage['early_stopping_patience'],
            ranking_temperature=stage['ranking_temperature'], model_seeds=stage['model_seeds']))
    config = copy.deepcopy(config or yaml.safe_load(
        (PROJECT_ROOT / 'configs/controller_training.yaml').read_text()))
    if epochs is not None:
        if epochs < 1:
            raise ValueError('Epochs must be positive')
        config['controller']['epochs'] = epochs
    development_path, confirmatory_path = Path(development), Path(confirmatory)
    development, confirmatory = load_prepared(development_path), load_prepared(confirmatory_path)
    assert_query_isolation(development.query_hashes, confirmatory.query_hashes)
    if set(development.groups.root_id) & set(confirmatory.groups.root_id):
        raise ValueError('Development and confirmatory roots overlap')
    train = np.flatnonzero(development.groups.model_split.to_numpy() == 'train')
    validation = np.flatnonzero(development.groups.model_split.to_numpy() == 'validation')
    test = np.flatnonzero(confirmatory.groups.model_split.to_numpy() == 'test')
    if not len(train) or not len(validation) or not len(test):
        raise ValueError('Train, validation, and test splits must be nonempty')
    names = list(models or (REPRESENTATION_CHANNELS if representations else MODEL_NAMES))
    allowed = REPRESENTATION_CHANNELS if representations else MODEL_NAMES
    if any(name not in allowed for name in names) or len(names) != len(set(names)):
        raise ValueError('Invalid or duplicate model name')
    seeds = list(seeds if seeds is not None else config['controller']['model_seeds'])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    normalizer = fit_cst_normalizer(development, train)
    (output / 'cst_normalizer.json').write_text(json.dumps(normalizer.statistics.to_dict(), indent=2) + '\n')
    rows = []
    for name in names:
        for seed in seeds:
            if representations:
                # Each root contributes only its permitted training or validation labels.
                costs = development.costs['oracle'].copy()
                costs[validation] = development.costs['validation'][validation]
                fitted = fit_controller(development.scalar, development.spatial, costs,
                    development.valid, train, validation, variant=name, seed=seed,
                    epochs=config['controller']['epochs'], learning_rate=config['controller']['learning_rate'],
                    batch_size=config['controller']['batch_size'],
                    patience=config['controller']['early_stopping_patience'],
                    tau=config['controller']['ranking_temperature'], mse_weight=.1)
                payload = dict(model=fitted.model.state_dict(), scalar_mean=fitted.scalar_mean,
                    scalar_scale=fitted.scalar_scale, representation=name, model_seed=seed,
                    channels=fitted.channels, kind='REPRESENTATION_STUDY_NOT_PRODUCTION')
                metrics = dict(model=name, model_seed=seed, epochs_run=fitted.epochs_run)
            else:
                fitted, frame, metrics = fit_final_controller(name, development, train, validation,
                    confirmatory, test, config=config, model_seed=seed, cst_normalizer=normalizer)
                payload = dict(model=fitted['model'].state_dict(), scalar_mean=fitted['scalar_mean'],
                    scalar_scale=fitted['scalar_scale'], model_name=name, model_seed=seed)
            filename = name.lower().replace('-', '_') + f'_seed{seed}.pt'
            torch.save(payload, output / filename)
            rows.append(metrics)
            print(json.dumps(dict(model=name, seed=seed, checkpoint=filename)), flush=True)
    receipt = dict(kind='NEW_TRAINING_RUN', development_sha256=sha256(development_path),
                   confirmatory_sha256=sha256(confirmatory_path), config=config,
                   models=names, seeds=seeds, representations=representations, metrics=rows,
                   note='New measurements do not replace or relabel the bundled original checkpoints.')
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--smoke', action='store_true')
    prepare.add_argument('--geolife-development', type=Path)
    prepare.add_argument('--geolife-confirmatory', type=Path)
    train = commands.add_parser('train')
    train.add_argument('--development', type=Path, required=True)
    train.add_argument('--confirmatory', type=Path, required=True)
    train.add_argument('--output', type=Path, required=True)
    train.add_argument('--models', nargs='+')
    train.add_argument('--seeds', nargs='+', type=int)
    train.add_argument('--epochs', type=int)
    train.add_argument('--representations', action='store_true')
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.command == 'prepare':
        prepare_training(args.output, smoke=args.smoke,
            geolife_development=args.geolife_development, geolife_confirmatory=args.geolife_confirmatory)
    else:
        train_models(args.development, args.confirmatory, args.output, models=args.models,
            seeds=args.seeds, epochs=args.epochs, representations=args.representations)


if __name__ == '__main__':
    main()
