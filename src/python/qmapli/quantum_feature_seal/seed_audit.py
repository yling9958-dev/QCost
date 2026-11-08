"""Deterministic fingerprints for every Quantum Feature Seal controller."""

from __future__ import annotations

import hashlib
import numpy as np
import torch

from .models import bind_runtime_seed, create_seal_model


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def state_dict_sha256(model) -> str:
    digest = hashlib.sha256()
    for key, value in sorted(model.state_dict().items()):
        array = np.ascontiguousarray(value.detach().cpu().numpy())
        digest.update(key.encode("utf-8"))
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
        digest.update(array.view(np.uint8).tobytes())
    return digest.hexdigest()


def array_sha256(values) -> str:
    array = np.ascontiguousarray(np.asarray(values))
    return _digest_bytes(array.view(np.uint8).tobytes())


def first_batch_indices(item_count: int, batch_size: int, model_seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(model_seed) + 3401)
    return rng.permutation(int(item_count))[: int(batch_size)]


def deterministic_probe(
    model_name: str,
    *,
    scalar_size: int = 24,
    model_seed: int = 0,
    dataset_seed: int = 20260825,
) -> dict[str, object]:
    """Run a small initialization/prediction/update fingerprint probe."""

    bind_runtime_seed(model_seed)
    rng = np.random.default_rng(int(dataset_seed))
    scalar = torch.from_numpy(rng.normal(size=(12, scalar_size)).astype(np.float32))
    spatial = torch.from_numpy(rng.normal(size=(12, 7, 4, 4)).astype(np.float32))
    target = torch.from_numpy(rng.normal(size=12).astype(np.float32))
    model = create_seal_model(model_name, scalar_size, model_seed)
    initialization_hash = state_dict_sha256(model)
    batch = first_batch_indices(12, 6, model_seed)
    first_batch_hash = array_sha256(batch.astype("<i8"))
    model.eval()
    with torch.no_grad():
        prediction_hash = array_sha256(model(scalar, spatial).detach().cpu().numpy())
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.Adam(parameters, lr=1e-3)
    model.train()
    index = torch.from_numpy(batch.astype(np.int64))
    for _ in range(2):
        prediction = model(scalar[index], spatial[index])
        loss = torch.nn.functional.mse_loss(prediction, target[index])
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    return {
        "model": model_name,
        "model_seed": int(model_seed),
        "initialization_hash": initialization_hash,
        "first_batch_hash": first_batch_hash,
        "prediction_hash": prediction_hash,
        "final_model_hash": state_dict_sha256(model),
    }
