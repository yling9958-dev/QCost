"""Four-way workload query generation with content-hash isolation."""

from __future__ import annotations

import hashlib

import numpy as np


WORKLOADS = (
    "uniform",
    "hotspot_left",
    "hotspot_right",
    "hotspot_top",
    "hotspot_bottom",
    "horizontal_window",
    "vertical_window",
    "mixed_hotspot",
)
SELECTIVITY_RANGES = {"small": (0.0005, 0.003), "medium": (0.005, 0.03)}
QUERY_SPLITS = ("context", "oracle", "validation", "test")


def rectangle_sha256(rectangle: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(rectangle, dtype="<f8").tobytes()).hexdigest()


def _centers(rng, bounds, workload, count):
    xmin, ymin, xmax, ymax = bounds
    width, height = xmax - xmin, ymax - ymin
    if workload == "uniform":
        return rng.uniform((xmin, ymin), (xmax, ymax), size=(count, 2))
    if workload == "mixed_hotspot":
        anchors = np.asarray(((0.2, 0.75), (0.8, 0.25), (0.3, 0.3)))
        relative = anchors[rng.integers(0, len(anchors), count)] + rng.normal(0, 0.07, (count, 2))
    else:
        anchor = {
            "hotspot_left": (0.18, 0.50),
            "hotspot_right": (0.82, 0.50),
            "hotspot_top": (0.50, 0.82),
            "hotspot_bottom": (0.50, 0.18),
            "horizontal_window": (0.50, 0.50),
            "vertical_window": (0.50, 0.50),
        }[workload]
        relative = rng.normal(anchor, (0.08, 0.08), size=(count, 2))
    relative = np.clip(relative, 0.02, 0.98)
    return np.column_stack((xmin + relative[:, 0] * width, ymin + relative[:, 1] * height))


def _generate(
    bounds,
    *,
    workload: str,
    selectivity: str,
    count: int,
    seed: int,
    used: set[str],
) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    xmin, ymin, xmax, ymax = bounds
    span = np.asarray((max(xmax - xmin, 1e-12), max(ymax - ymin, 1e-12)))
    rows = []
    attempts = 0
    while len(rows) < count:
        attempts += 1
        if attempts > count * 100:
            raise RuntimeError("unable to generate unique query rectangles")
        center = _centers(rng, bounds, workload, 1)[0]
        area = rng.uniform(*SELECTIVITY_RANGES[selectivity])
        aspect = 6.0 if workload == "horizontal_window" else (1 / 6 if workload == "vertical_window" else 1.0)
        dimensions = np.asarray((np.sqrt(area * aspect), np.sqrt(area / aspect))) * span
        lower = np.maximum(center - dimensions / 2, (xmin, ymin))
        upper = np.minimum(center + dimensions / 2, (xmax, ymax))
        rectangle = np.asarray((lower[0], lower[1], upper[0], upper[1]), dtype=np.float64)
        digest = rectangle_sha256(rectangle)
        if digest in used:
            continue
        used.add(digest)
        rows.append(rectangle)
    return np.vstack(rows)


def isolated_query_splits(bounds, *, workload: str, count: int, seed: int):
    if count % 2:
        raise ValueError("query count must be even to balance selectivity ranges")
    used: set[str] = set()
    outputs = {}
    hashes = {}
    per_range = count // 2
    for split_index, split in enumerate(QUERY_SPLITS):
        rows = []
        split_hashes = set()
        for range_index, selectivity in enumerate(("small", "medium")):
            values = _generate(
                bounds,
                workload=workload,
                selectivity=selectivity,
                count=per_range,
                seed=int(seed) + split_index * 1_000_003 + range_index * 10_007,
                used=used,
            )
            rows.append(values)
            split_hashes.update(rectangle_sha256(row) for row in values)
        outputs[split] = np.vstack(rows)
        hashes[split] = split_hashes
    for left_index, left in enumerate(QUERY_SPLITS):
        for right in QUERY_SPLITS[left_index + 1 :]:
            if hashes[left] & hashes[right]:
                raise AssertionError(f"query leakage between {left} and {right}")
    outputs["hashes"] = hashes
    return outputs


def aggregate_hash(values: set[str]) -> str:
    payload = "\n".join(sorted(values)).encode("ascii")
    return hashlib.sha256(payload).hexdigest()
