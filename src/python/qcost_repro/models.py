"""Load and verify every original controller checkpoint with its own factory."""

from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import torch

from qmapli.final_full_scale.controllers import create_final_model
from qmapli.quantum.channel_tensor_encoding import ChannelTensorNormalizer, ChannelTensorStatistics
from qmapli.wg_qmf.cached_features import node_action_features

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_normalizer(path):
    row = json.loads(Path(path).read_text(encoding='utf-8'))
    normalizer = ChannelTensorNormalizer(row['selected_channels'], row['clip'])
    normalizer.statistics = ChannelTensorStatistics(
        np.asarray(row['channel_mean']), np.asarray(row['channel_std']),
        row['global_log_norm_mean'], row['global_log_norm_std'],
        tuple(row['selected_channels']), row['clip'])
    return normalizer


def load_model(checkpoint, *, normalizer_path=None):
    """Load a trusted project checkpoint; never load untrusted pickle files."""
    checkpoint = Path(checkpoint)
    payload = torch.load(checkpoint, map_location='cpu', weights_only=False)
    name = payload['model_name']
    normalizer = None
    if name == 'CST':
        normalizer = read_normalizer(normalizer_path or checkpoint.with_name('cst_normalizer.json'))
    model = create_final_model(name, len(payload['scalar_mean']),
                               payload['model_seed'], cst_normalizer=normalizer)
    model.load_state_dict(payload['model'], strict=True)
    model.eval()
    return model, payload


class ModelScorer:
    direction = 'higher_is_better'

    def __init__(self, checkpoint, *, normalizer_path=None):
        self.model, payload = load_model(checkpoint, normalizer_path=normalizer_path)
        self.mean = np.asarray(payload['scalar_mean'], dtype=np.float32)
        self.scale = np.asarray(payload['scalar_scale'], dtype=np.float32)

    def score_actions(self, points, context_queries, actions):
        scalar, spatial = node_action_features(points, context_queries, actions)
        with torch.no_grad():
            result = self.model(torch.from_numpy((scalar - self.mean) / self.scale),
                                torch.from_numpy(spatial))
        return result.cpu().numpy().astype(np.float64)


def verify_models(model_root=PROJECT_ROOT / 'models'):
    model_root = Path(model_root)
    manifest = json.loads((model_root / 'manifest.json').read_text(encoding='utf-8'))
    if sha256(model_root / 'cst_normalizer.json') != manifest['cst_normalizer_sha256']:
        raise ValueError('CST normalizer SHA-256 mismatch')
    result = []
    for row in manifest['models']:
        path = model_root / row['file']
        if sha256(path) != row['sha256']:
            raise ValueError('Model SHA-256 mismatch: ' + row['file'])
        model, payload = load_model(path)
        if payload['model_name'] != row['model_name']:
            raise ValueError('Checkpoint model identity mismatch')
        with torch.no_grad():
            scores = model(torch.zeros(2, row['scalar_size']), torch.full((2, 7, 4, 4), 1 / 16))
        if scores.shape != (2,) or not torch.isfinite(scores).all():
            raise ValueError('Nonfinite or incorrectly shaped inference: ' + row['file'])
        result.append(dict(file=row['file'], model=row['model_name'], status='PASS',
                           parameters=sum(p.numel() for p in model.parameters())))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, default=PROJECT_ROOT / 'models')
    args = parser.parse_args()
    torch.set_num_threads(1)
    print(json.dumps(verify_models(args.models), indent=2))


if __name__ == '__main__':
    main()
