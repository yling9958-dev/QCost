"""Oracle-independent root-grouped local node bank."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .distributions import RootDataset


@dataclass(frozen=True)
class SpatialNode:
    dataset: str
    distribution_type: str
    root_seed: int
    root_id: str
    node_id: str
    points: np.ndarray
    generation_method: str
    model_split: str

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        lower = self.points.min(axis=0)
        upper = self.points.max(axis=0)
        return float(lower[0]), float(lower[1]), float(upper[0]), float(upper[1])

    def metadata(self) -> dict[str, object]:
        xmin, ymin, xmax, ymax = self.bbox
        return {
            "dataset": self.dataset,
            "distribution_type": self.distribution_type,
            "root_seed": self.root_seed,
            "root_id": self.root_id,
            "node_id": self.node_id,
            "point_count": len(self.points),
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
            "generation_method": self.generation_method,
            "model_split": self.model_split,
        }


def _model_split(root_seed: int) -> str:
    if int(root_seed) <= 3:
        return "train"
    return "validation" if int(root_seed) == 4 else "test"


def _subset_digest(indices: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(indices, dtype="<i8").tobytes()).hexdigest()


def build_node_bank(
    roots: list[RootDataset],
    *,
    minimum_points: int = 1500,
    maximum_points: int = 12000,
    local_windows: int = 3,
    seed: int = 20260817,
    enforce_target: bool = True,
) -> list[SpatialNode]:
    nodes: list[SpatialNode] = []
    for root_index, root in enumerate(roots):
        points = np.asarray(root.points, dtype=np.float64)
        if not minimum_points <= len(points) <= maximum_points:
            raise ValueError(f"root {root.root_id} has unsupported size {len(points)}")
        split = _model_split(root.root_seed)
        candidates: list[tuple[np.ndarray, str]] = [
            (np.arange(len(points), dtype=np.int64), "root")
        ]
        lower, upper = points.min(axis=0), points.max(axis=0)
        midpoint = (lower + upper) / 2.0
        for x_side in (0, 1):
            for y_side in (0, 1):
                mask = (
                    ((points[:, 0] <= midpoint[0]) if x_side == 0 else (points[:, 0] > midpoint[0]))
                    & ((points[:, 1] <= midpoint[1]) if y_side == 0 else (points[:, 1] > midpoint[1]))
                )
                candidates.append((np.flatnonzero(mask), f"quadtree_depth1_q{x_side}{y_side}"))
        span = np.maximum(upper - lower, 1e-12)
        normalized = (points - lower) / span
        rng = np.random.default_rng(int(seed) + root_index * 1009 + root.root_seed)
        centers = rng.uniform(0.20, 0.80, size=(int(local_windows), 2))
        for window_index, center in enumerate(centers):
            positions = np.empty(0, dtype=np.int64)
            for half_width in (0.24, 0.32, 0.42, 0.50):
                positions = np.flatnonzero(np.all(np.abs(normalized - center) <= half_width, axis=1))
                if len(positions) >= minimum_points:
                    break
            candidates.append((positions, f"fixed_axis_window_{window_index}"))
        seen: set[str] = set()
        accepted = 0
        for positions, method in candidates:
            positions = np.asarray(positions, dtype=np.int64)
            if len(positions) < minimum_points:
                continue
            if len(positions) > maximum_points:
                positions = positions[:maximum_points]
            digest = _subset_digest(positions)
            if digest in seen:
                continue
            seen.add(digest)
            accepted += 1
            nodes.append(
                SpatialNode(
                    dataset=root.dataset,
                    distribution_type=root.distribution_type,
                    root_seed=root.root_seed,
                    root_id=root.root_id,
                    node_id=f"{root.root_id}:n{accepted:02d}",
                    points=np.asarray(points[positions], dtype=np.float64),
                    generation_method=method,
                    model_split=split,
                )
            )
    if enforce_target and not 300 <= len(nodes) <= 500:
        raise RuntimeError(f"node bank size {len(nodes)} is outside the pre-registered 300-500 range")
    return nodes


def node_bank_frame(nodes: list[SpatialNode]) -> pd.DataFrame:
    return pd.DataFrame([node.metadata() for node in nodes])
