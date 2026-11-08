"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import csv

import hashlib

import json

import math

from pathlib import Path

import numpy as np

import pandas as pd

from .protocol import SELECTIVITY_GROUPS, resolved, sha256_file

def _sha256_prefix(path: Path, byte_count: int) -> str:
    digest = hashlib.sha256()
    remaining = int(byte_count)
    with path.open("rb") as handle:
        while remaining:
            block = handle.read(min(8 * 1024 * 1024, remaining))
            if not block:
                raise ValueError("selected prefix exceeds source file")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()

def select_geolife_prefix(config: dict, work_root: Path) -> dict:
    """Copy complete source records up to the frozen raw byte target.

    The source row ordinal is the immutable point ID. A raw-coordinate file is
    retained for PostgreSQL and a shared normalized file is used by every
    learned index. Neither selection nor normalization depends on a method.
    """

    source = resolved(config["dataset"]["source"])
    target = int(config["dataset"]["target_raw_bytes"])
    work_root.mkdir(parents=True, exist_ok=True)
    raw_points = work_root / "points_raw.csv"
    normalized_points = work_root / "points_normalized.csv"
    metadata_path = work_root / "dataset_metadata.json"
    if raw_points.is_file() and normalized_points.is_file() and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("source_path") == str(source)
            and metadata.get("target_raw_bytes") == target
            and metadata.get("raw_points_sha256") == sha256_file(raw_points)
            and metadata.get("normalized_points_sha256") == sha256_file(normalized_points)
        ):
            return metadata

    selected_bytes = 0
    count = 0
    xmin = ymin = math.inf
    xmax = ymax = -math.inf
    coordinate_digest = hashlib.sha256()
    with source.open("rb") as input_handle, raw_points.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        header = input_handle.readline()
        selected_bytes += len(header)
        writer = csv.writer(output_handle, lineterminator="\n")
        writer.writerow(("id", "lon", "lat"))
        while True:
            line = input_handle.readline()
            if not line or selected_bytes + len(line) > target:
                break
            try:
                x_text, y_text = line.decode("ascii").strip().split(",")[:2]
                x = float(x_text)
                y = float(y_text)
            except (UnicodeDecodeError, ValueError) as error:
                raise ValueError(f"invalid GeoLife row at source ordinal {count}") from error
            writer.writerow((count, x_text, y_text))
            coordinate_digest.update(line)
            selected_bytes += len(line)
            count += 1
            xmin, xmax = min(xmin, x), max(xmax, x)
            ymin, ymax = min(ymin, y), max(ymax, y)
    if count == 0 or not (xmin < xmax and ymin < ymax):
        raise ValueError("deterministic GeoLife selection is empty or degenerate")

    frame = pd.read_csv(raw_points, dtype={"id": np.uint32, "lon": np.float64, "lat": np.float64})
    unique_ids = int(frame["id"].nunique())
    if unique_ids != count:
        raise ValueError("source-ordinal ID mapping is not unique")
    unique_coordinates = int(frame[["lon", "lat"]].drop_duplicates().shape[0])
    xscale = xmax - xmin
    yscale = ymax - ymin
    normalized = pd.DataFrame(
        {
            "id": frame["id"],
            "x": ((frame["lon"] - xmin) / xscale).astype(np.float64),
            "y": ((frame["lat"] - ymin) / yscale).astype(np.float64),
        }
    )
    normalized.to_csv(normalized_points, index=False, lineterminator="\n", float_format="%.17g")
    metadata = {
        "dataset_id": "geolife_100m",
        "interpretation": config["dataset"]["interpretation"],
        "source_path": str(source),
        "source_file_bytes": source.stat().st_size,
        "source_file_sha256": sha256_file(source),
        "target_raw_bytes": target,
        "selected_raw_bytes": selected_bytes,
        "selected_prefix_sha256": _sha256_prefix(source, selected_bytes),
        "selected_coordinate_lines_sha256": coordinate_digest.hexdigest(),
        "point_count": count,
        "unique_point_id_count": unique_ids,
        "unique_coordinate_count": unique_coordinates,
        "longitude_min": xmin,
        "longitude_max": xmax,
        "latitude_min": ymin,
        "latitude_max": ymax,
        "selection_procedure": config["dataset"]["selection"],
        "id_mapping": config["dataset"]["id_mapping"],
        "normalization": config["dataset"]["learned_index_preprocessing"],
        "raw_points_path": str(raw_points),
        "raw_points_sha256": sha256_file(raw_points),
        "normalized_points_path": str(normalized_points),
        "normalized_points_sha256": sha256_file(normalized_points),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata
