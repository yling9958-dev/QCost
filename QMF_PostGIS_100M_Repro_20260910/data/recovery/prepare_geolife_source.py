#!/usr/bin/env python3
"""Validate the locked official archive and historical trajectory order."""

import argparse
import json
from pathlib import Path

from build_geolife_100m import (
    ARCHIVE_BYTES,
    ARCHIVE_SHA256,
    ORDER_COUNT,
    ORDER_SHA256,
    load_order,
    sha256_file,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--order", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.archive.stat().st_size != ARCHIVE_BYTES:
        raise ValueError("official GeoLife archive byte count mismatch")
    if sha256_file(arguments.archive) != ARCHIVE_SHA256:
        raise ValueError("official GeoLife archive SHA256 mismatch")
    order = load_order(arguments.order)
    print(json.dumps({
        "archive_bytes": ARCHIVE_BYTES,
        "archive_sha256": ARCHIVE_SHA256,
        "trajectory_order_count": len(order),
        "trajectory_order_sha256": ORDER_SHA256,
        "status": "SOURCE_VERIFICATION_PASS",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
