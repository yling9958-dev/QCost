#!/usr/bin/env python3
"""Verify the immutable combined query file and frozen split cardinalities."""

import csv
import hashlib
from collections import Counter
from pathlib import Path


EXPECTED_SHA = "50c6e29f5a24188814a82a6f1541be5a64a5a9a7d3923659c3f289b02d0f4259"
EXPECTED_SPLITS = {
    "train": 1200,
    "validation": 1200,
    "correctness": 5000,
    "warmup": 1000,
    "performance": 15000,
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    path = root / "queries/geolife_100m_queries.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA:
        raise SystemExit("QUERY_SHA_MISMATCH")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    counts = Counter(row["split"] for row in rows)
    if len(rows) != 23400 or counts != Counter(EXPECTED_SPLITS):
        raise SystemExit(f"QUERY_STRUCTURE_MISMATCH: rows={len(rows)} splits={dict(counts)}")
    print("QUERY_VERIFICATION = PASS")


if __name__ == "__main__":
    main()
