"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import hashlib

from pathlib import Path

import yaml

from ..core.paths import project_root

PRIMARY_METHODS = (
    ("QMF-Index", "qmap_uniform_qmf"),
    ("PostGIS-GiST", "postgis_gist"),
    ("LISA", "lisa"),
    ("Flood", "flood"),
    ("Tsunami", "tsunami"),
    ("LMSFC", "lmsfc"),
    ("BMTree", "bmtree"),
    ("Boost-R*-tree", "rtree"),
)

PRIMARY_METRICS = (
    ("BuildTime_s", "lower"),
    ("IndexSize_MiB", "lower"),
    ("MeanLatency_ms", "lower"),
    ("P95Latency_ms", "lower"),
    ("P99Latency_ms", "lower"),
    ("QPS", "higher"),
    ("PeakMemory_MiB", "lower"),
)

SELECTIVITY_GROUPS = ("S1", "S2", "S3")

def load_config(path: Path | None = None) -> dict:
    root = project_root()
    source = Path(path) if path else root / "config/benchmark_config.yaml"
    with source.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    actual = tuple((row["display"], row["runtime"]) for row in config["benchmark"]["methods"])
    if actual != PRIMARY_METHODS:
        raise ValueError("pilot method suite no longer matches the frozen eight-method protocol")
    if int(config["benchmark"]["measured_queries"]) != 15_000:
        raise ValueError("pilot measured query count must remain 15000")
    if config["queries"].get("center_selection") != "deterministic_sampled_data_points":
        raise ValueError("pilot query centers must remain bound to frozen data points")
    if config["queries"].get("selectivity_definition") != "target_point_fraction_via_exact_kth_neighbor_rectangle":
        raise ValueError("pilot selectivity must remain a frozen target point fraction")
    if config["queries"].get("boundary_policy") != "midpoint_between_adjacent_float32_coordinate_levels":
        raise ValueError("pilot boundaries must remain separated from stored float coordinates")
    return config

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def resolved(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else project_root() / value
