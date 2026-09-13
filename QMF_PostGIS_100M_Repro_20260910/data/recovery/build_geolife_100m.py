#!/usr/bin/env python3
"""Reconstruct the frozen GeoLife prefix from the official 1.3 archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile


ARCHIVE_BYTES = 313164406
ARCHIVE_SHA256 = "1107c5ac064d0a23c8d021a8736a77e53abc75b227062e6260342c6a8d86bdb6"
ORDER_COUNT = 18670
ORDER_SHA256 = "6abad47d6979fb785a388b577583e30923f82b196a4cfe238dc40bba247f5df9"
TARGET_BYTES = 104857600
SELECTED_BYTES = 104857576
SELECTED_SHA256 = "56a07a638db478485ba5e78ff45bc7300987ef45d7d4a319666a5dabbcaa555e"
POINT_COUNT = 4197223
UNIQUE_COORDINATES = 3956264
ARCHIVE_PREFIX = "Geolife Trajectories 1.3/"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_order(path: Path) -> list[str]:
    if sha256_file(path) != ORDER_SHA256:
        raise ValueError("trajectory order SHA256 mismatch")
    order = path.read_text(encoding="utf-8").splitlines()
    if len(order) != ORDER_COUNT or len(set(order)) != ORDER_COUNT:
        raise ValueError("trajectory order count/uniqueness mismatch")
    return order


def verify(path: Path) -> dict[str, object]:
    if path.stat().st_size != SELECTED_BYTES:
        raise ValueError("selected dataset byte count mismatch")
    digest = sha256_file(path)
    if digest != SELECTED_SHA256:
        raise ValueError("selected dataset SHA256 mismatch")

    count = 0
    coordinates: set[bytes] = set()
    xmin = ymin = math.inf
    xmax = ymax = -math.inf
    with path.open("rb") as handle:
        if handle.readline() != b"x,y\n":
            raise ValueError("selected dataset header mismatch")
        for line in handle:
            if not line.endswith(b"\n"):
                raise ValueError("selected dataset contains an incomplete record")
            fields = line[:-1].split(b",")
            if len(fields) != 2:
                raise ValueError("selected dataset row shape mismatch")
            x, y = map(float, fields)
            count += 1
            coordinates.add(line[:-1])
            xmin, xmax = min(xmin, x), max(xmax, x)
            ymin, ymax = min(ymin, y), max(ymax, y)
    if count != POINT_COUNT or len(coordinates) != UNIQUE_COORDINATES:
        raise ValueError("selected dataset count mismatch")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest,
        "point_count": count,
        "unique_point_id_count": count,
        "unique_coordinate_count": len(coordinates),
        "longitude_min": xmin,
        "longitude_max": xmax,
        "latitude_min": ymin,
        "latitude_max": ymax,
    }


def reconstruct(archive: Path, order_path: Path, output: Path) -> dict[str, object]:
    if archive.stat().st_size != ARCHIVE_BYTES or sha256_file(archive) != ARCHIVE_SHA256:
        raise ValueError("official GeoLife archive size/SHA256 mismatch")
    order = load_order(order_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        return verify(output)

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=output.name + ".", suffix=".part", dir=output.parent, delete=False
        ) as destination, zipfile.ZipFile(archive) as source:
            temporary = Path(destination.name)
            destination.write(b"x,y\n")
            selected_bytes = 4
            point_count = 0
            finished = False
            for relative_name in order:
                member = ARCHIVE_PREFIX + relative_name
                with source.open(member) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                    reader = csv.reader(text)
                    for _ in range(6):
                        next(reader, None)
                    for row in reader:
                        if len(row) < 2 or not row[0] or not row[1]:
                            continue
                        latitude, longitude = float(row[0]), float(row[1])
                        if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
                            continue
                        encoded = f"{longitude:.8f},{latitude:.8f}\n".encode("ascii")
                        if selected_bytes + len(encoded) > TARGET_BYTES:
                            finished = True
                            break
                        destination.write(encoded)
                        selected_bytes += len(encoded)
                        point_count += 1
                if finished:
                    break
            destination.flush()
            os.fsync(destination.fileno())
        if selected_bytes != SELECTED_BYTES or point_count != POINT_COUNT:
            raise ValueError("reconstructed prefix byte/row count mismatch")
        if sha256_file(temporary) != SELECTED_SHA256:
            raise ValueError("reconstructed prefix SHA256 mismatch")
        os.replace(temporary, output)
        temporary = None
        return verify(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--order", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify_only:
        result = verify(arguments.output)
    else:
        if arguments.archive is None or arguments.order is None:
            parser.error("--archive and --order are required for reconstruction")
        result = reconstruct(arguments.archive, arguments.order, arguments.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
