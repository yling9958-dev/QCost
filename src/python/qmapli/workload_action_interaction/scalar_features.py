"""Fixed scalar branch shared by every representation variant."""

from __future__ import annotations

import numpy as np
from scipy.stats import skew

from .actions import SplitAction, enumerate_actions, normalized_threshold


def scalar_node_feature_names() -> list[str]:
    names = [
        "log_point_count",
        "aspect_ratio",
        "mean_x",
        "mean_y",
        "variance_x",
        "variance_y",
        "pearson_correlation",
        "skewness_x",
        "skewness_y",
    ]
    names.extend(f"quartile_{axis}_{q}" for axis in ("x", "y") for q in (25, 50, 75))
    names.extend(f"split_balance_{axis}_q{q:g}" for axis in ("x", "y") for q in (0.25, 0.375, 0.5, 0.625, 0.75))
    names.extend(f"x_hist_{index}" for index in range(8))
    names.extend(f"y_hist_{index}" for index in range(8))
    return names


ACTION_SCALAR_NAMES = ("axis_x", "axis_y", "quantile", "normalized_threshold", "split_balance")


def scalar_node_features(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64)
    lower, upper = points.min(axis=0), points.max(axis=0)
    spans = np.maximum(upper - lower, 1e-12)
    correlation = np.corrcoef(points[:, 0], points[:, 1])[0, 1]
    values = [
        np.log1p(len(points)),
        spans[0] / spans[1],
        *points.mean(axis=0),
        *points.var(axis=0),
        float(correlation) if np.isfinite(correlation) else 0.0,
        float(np.nan_to_num(skew(points[:, 0], bias=False))),
        float(np.nan_to_num(skew(points[:, 1], bias=False))),
    ]
    for axis in (0, 1):
        values.extend(np.quantile(points[:, axis], (0.25, 0.5, 0.75)).tolist())
    for action in enumerate_actions(points):
        values.append(abs(action.left_count - action.right_count) / len(points))
    for axis in (0, 1):
        histogram, _ = np.histogram(points[:, axis], bins=8, range=(lower[axis], upper[axis]))
        values.extend((histogram / max(histogram.sum(), 1)).tolist())
    result = np.asarray(values, dtype=np.float32)
    if len(result) != len(scalar_node_feature_names()):
        raise AssertionError("scalar node feature schema mismatch")
    return result


def scalar_action_features(points: np.ndarray, action: SplitAction) -> np.ndarray:
    return np.asarray(
        (
            float(action.axis == 0),
            float(action.axis == 1),
            action.quantile,
            normalized_threshold(points, action),
            abs(action.left_count - action.right_count) / len(points),
        ),
        dtype=np.float32,
    )


def combined_scalar_features(points: np.ndarray, action: SplitAction) -> np.ndarray:
    return np.concatenate((scalar_node_features(points), scalar_action_features(points, action)))
