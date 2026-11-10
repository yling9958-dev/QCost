"""Synthetic roots and local real-data roots for the interaction study."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np



SYNTHETIC_DISTRIBUTIONS = (
    "uniform",
    "gaussian_clusters",
    "diagonal_band",
    "anti_diagonal_band",
    "horizontal_strips",
    "vertical_strips",
    "ring",
    "checkerboard",
    "center_dense",
    "corner_hotspot",
)


@dataclass(frozen=True)
class RootDataset:
    root_id: str
    dataset: str
    distribution_type: str
    root_seed: int
    points: np.ndarray


def _clip(points: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(points, dtype=np.float64), 0.0, 1.0)


def generate_distribution(name: str, count: int, seed: int) -> np.ndarray:
    if name not in SYNTHETIC_DISTRIBUTIONS:
        raise ValueError(f"unknown synthetic distribution: {name}")
    rng = np.random.default_rng(int(seed))
    if name == "uniform":
        points = rng.random((count, 2))
    elif name == "gaussian_clusters":
        centers = np.asarray(((0.22, 0.25), (0.72, 0.30), (0.48, 0.76)))
        labels = rng.integers(0, len(centers), count)
        scales = np.asarray(((0.055, 0.075), (0.075, 0.045), (0.06, 0.065)))
        points = centers[labels] + rng.normal(size=(count, 2)) * scales[labels]
    elif name in {"diagonal_band", "anti_diagonal_band"}:
        x = rng.random(count)
        baseline = x if name == "diagonal_band" else 1.0 - x
        points = np.column_stack((x, baseline + rng.normal(0.0, 0.035, count)))
    elif name in {"horizontal_strips", "vertical_strips"}:
        centers = np.asarray((0.16, 0.38, 0.64, 0.84))
        strip = centers[rng.integers(0, len(centers), count)] + rng.normal(0.0, 0.018, count)
        points = np.column_stack((rng.random(count), strip))
        if name == "vertical_strips":
            points = points[:, ::-1]
    elif name == "ring":
        angle = rng.uniform(0.0, 2.0 * np.pi, count)
        radius = np.clip(rng.normal(0.31, 0.025, count), 0.20, 0.42)
        points = np.column_stack((0.5 + radius * np.cos(angle), 0.5 + radius * np.sin(angle)))
    elif name == "checkerboard":
        cells = np.asarray([(x, y) for x in range(4) for y in range(4) if (x + y) % 2 == 0])
        selected = cells[rng.integers(0, len(cells), count)]
        points = (selected + rng.random((count, 2))) / 4.0
    elif name == "center_dense":
        points = rng.beta(4.5, 4.5, size=(count, 2))
    else:
        corners = np.asarray(((0.08, 0.08), (0.08, 0.92), (0.92, 0.08), (0.92, 0.92)))
        labels = rng.choice(len(corners), count, p=(0.55, 0.15, 0.15, 0.15))
        points = corners[labels] + rng.normal(0.0, 0.045, size=(count, 2))
    return _clip(points)


def synthetic_roots(distributions, seeds, points_per_root) -> list[RootDataset]:
    return [
        RootDataset(
            root_id=f"synthetic:{name}:s{seed}",
            dataset="synthetic",
            distribution_type=name,
            root_seed=int(seed),
            points=generate_distribution(name, int(points_per_root), int(seed)),
        )
        for name in distributions
        for seed in seeds
    ]
