"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

QUANTILES = (0.25, 0.375, 0.50, 0.625, 0.75)

@dataclass(frozen=True)
class SplitAction:
    axis: int
    quantile: float
    threshold: float
    left_count: int
    right_count: int
    valid: bool

    @property
    def key(self) -> str:
        return f"{'x' if self.axis == 0 else 'y'}_q{self.quantile:g}"

    def as_dict(self) -> dict[str, object]:
        return {
            "action": self.key,
            "axis": "x" if self.axis == 0 else "y",
            "quantile": self.quantile,
            "threshold": self.threshold,
            "left_count": self.left_count,
            "right_count": self.right_count,
            "valid": self.valid,
        }

def enumerate_actions(points: np.ndarray, minimum_fraction: float = 0.05) -> list[SplitAction]:
    points = np.asarray(points, dtype=np.float64)
    count = len(points)
    if count == 0:
        return []
    actions = []
    for axis in (0, 1):
        seen: set[float] = set()
        for quantile in QUANTILES:
            threshold = float(np.quantile(points[:, axis], quantile, method="linear"))
            left = int(np.count_nonzero(points[:, axis] <= threshold))
            right = count - left
            valid = (
                threshold not in seen
                and left > 0
                and right > 0
                and left >= minimum_fraction * count
                and right >= minimum_fraction * count
            )
            seen.add(threshold)
            actions.append(SplitAction(axis, quantile, threshold, left, right, valid))
    return actions

def split_positions(points: np.ndarray, action: SplitAction) -> tuple[np.ndarray, np.ndarray]:
    if not action.valid:
        raise ValueError(f"cannot apply invalid action {action.key}")
    values = np.asarray(points)[:, action.axis]
    return np.flatnonzero(values <= action.threshold), np.flatnonzero(values > action.threshold)
