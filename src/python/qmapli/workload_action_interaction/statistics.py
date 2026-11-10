"""Deterministic scalar and paired bootstrap confidence intervals."""

from __future__ import annotations

import numpy as np


def bootstrap_summary(values, *, samples: int, seed: int):
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"mean": np.nan, "std": np.nan, "ci_low": np.nan, "ci_high": np.nan, "count": 0}
    rng = np.random.default_rng(int(seed))
    means = np.asarray([np.mean(rng.choice(values, len(values), replace=True)) for _ in range(int(samples))])
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "ci_low": float(np.percentile(means, 2.5)),
        "ci_high": float(np.percentile(means, 97.5)),
        "count": int(len(values)),
    }


def paired_bootstrap_difference(left, right, *, samples: int, seed: int):
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.shape != right.shape:
        raise ValueError("paired arrays must have identical shapes")
    differences = left - right
    rng = np.random.default_rng(int(seed))
    means = np.asarray(
        [np.mean(differences[rng.integers(0, len(differences), len(differences))]) for _ in range(int(samples))]
    )
    return {
        "mean_difference": float(np.mean(differences)),
        "ci_low": float(np.percentile(means, 2.5)),
        "ci_high": float(np.percentile(means, 97.5)),
        "count": int(len(differences)),
    }
