"""Aligned 4x4 data, workload, action-geometry, and interaction maps."""

from __future__ import annotations

import numpy as np

from .actions import SplitAction, normalized_threshold


GRID_SIZE = 4
CHANNEL_NAMES = ("P", "W", "M", "B", "I_DQ", "I_QB", "I_DQB")


def _normalize_points(points: np.ndarray):
    points = np.asarray(points, dtype=np.float64)
    lower = points.min(axis=0)
    span = np.maximum(points.max(axis=0) - lower, 1e-12)
    return np.clip((points - lower) / span, 0.0, 1.0), lower, span


def density_grid(points: np.ndarray, bins: int = GRID_SIZE) -> np.ndarray:
    normalized, _lower, _span = _normalize_points(points)
    histogram, _x, _y = np.histogram2d(
        normalized[:, 0], normalized[:, 1], bins=bins, range=((0.0, 1.0), (0.0, 1.0))
    )
    # histogram2d returns [x, y]; the public representation is [row=y, column=x].
    result = histogram.T / max(float(histogram.sum()), 1.0)
    return result.astype(np.float32)


def query_heatmap(points: np.ndarray, queries: np.ndarray, bins: int = GRID_SIZE) -> np.ndarray:
    _normalized, lower, span = _normalize_points(points)
    queries = np.asarray(queries, dtype=np.float64)
    local = queries.copy()
    local[:, (0, 2)] = (local[:, (0, 2)] - lower[0]) / span[0]
    local[:, (1, 3)] = (local[:, (1, 3)] - lower[1]) / span[1]
    local = np.clip(local, 0.0, 1.0)
    edges = np.linspace(0.0, 1.0, bins + 1)
    heat = np.zeros((bins, bins), dtype=np.float64)
    query_areas = np.maximum((local[:, 2] - local[:, 0]) * (local[:, 3] - local[:, 1]), 1e-15)
    for row in range(bins):
        for column in range(bins):
            x0, x1 = edges[column], edges[column + 1]
            y0, y1 = edges[row], edges[row + 1]
            width = np.maximum(0.0, np.minimum(local[:, 2], x1) - np.maximum(local[:, 0], x0))
            height = np.maximum(0.0, np.minimum(local[:, 3], y1) - np.maximum(local[:, 1], y0))
            heat[row, column] = np.mean(width * height / query_areas)
    heat /= max(float(heat.sum()), 1e-15)
    return heat.astype(np.float32)


def partition_side_mask(points: np.ndarray, action: SplitAction, bins: int = GRID_SIZE) -> np.ndarray:
    threshold = normalized_threshold(points, action)
    edges = np.linspace(0.0, 1.0, bins + 1)
    result = np.empty((bins, bins), dtype=np.float64)
    for row in range(bins):
        for column in range(bins):
            index = column if action.axis == 0 else row
            start, stop = edges[index], edges[index + 1]
            left_fraction = np.clip((threshold - start) / (stop - start), 0.0, 1.0)
            result[row, column] = 1.0 - 2.0 * left_fraction
    return result.astype(np.float32)


def boundary_proximity(points: np.ndarray, action: SplitAction, bins: int = GRID_SIZE) -> np.ndarray:
    threshold = normalized_threshold(points, action)
    centers = (np.arange(bins, dtype=np.float64) + 0.5) / bins
    distances = np.abs(centers - threshold)
    one_dimensional = np.exp(-0.5 * (distances / (1.0 / bins)) ** 2)
    result = (
        np.repeat(one_dimensional[None, :], bins, axis=0)
        if action.axis == 0
        else np.repeat(one_dimensional[:, None], bins, axis=1)
    )
    return result.astype(np.float32)


def interaction_maps(points: np.ndarray, context_queries: np.ndarray, action: SplitAction) -> dict[str, np.ndarray]:
    density = density_grid(points)
    workload = query_heatmap(points, context_queries)
    mask = partition_side_mask(points, action)
    boundary = boundary_proximity(points, action)
    return {
        "P": density,
        "W": workload,
        "M": mask,
        "B": boundary,
        "I_DQ": density * workload,
        "I_QB": workload * boundary,
        "I_DQB": density * workload * boundary,
    }


def stacked_maps(points: np.ndarray, context_queries: np.ndarray, action: SplitAction) -> np.ndarray:
    maps = interaction_maps(points, context_queries, action)
    return np.stack([maps[name] for name in CHANNEL_NAMES]).astype(np.float32)
