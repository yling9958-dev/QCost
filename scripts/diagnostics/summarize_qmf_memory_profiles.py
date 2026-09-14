#!/usr/bin/env python3
"""Create immutable audit tables from completed QMF prefix profiles."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "results/qmf_build_audit_cleanup_20260914"
BEFORE = Path("/var/tmp/qmf-memory-profiles-20260913/baseline")
AFTER = AUDIT / "profiles/after"
SIZES = ((1_000_000, "1m"), (5_000_000, "5m"), (10_000_000, "10m"),
         (25_000_000, "25m"), (50_000_000, "50m"))


def elapsed_seconds(value: str) -> float:
    parts = [float(item) for item in value.split(":" )]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(value)


def time_record(folder: Path) -> dict[str, object]:
    path = folder / "time.txt"
    if not path.is_file() or not path.stat().st_size:
        return {"status": "NOT_RUN"}
    text = path.read_text(encoding="utf-8")
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    elapsed = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([^\n]+)", text)
    if not rss or not elapsed:
        return {"status": "INCOMPLETE"}
    return {
        "status": "PASS",
        "build_seconds": elapsed_seconds(elapsed.group(1).strip()),
        "peak_RSS_MiB": int(rss.group(1)) / 1024,
    }


def trace_record(folder: Path) -> dict[str, object]:
    path = folder / "QMF_MEMORY_STAGE_TRACE.csv"
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    maximum = max(int(row["rss_peak_bytes"]) for row in rows)
    index = next(i for i, row in enumerate(rows) if int(row["rss_peak_bytes"]) == maximum)
    row = rows[index]
    phase = row["phase"]
    if phase.startswith("after_") and index:
        phase = f"between_{rows[index - 1]['phase']}_and_{phase}"
    return {
        "peak_stage": phase,
        "peak_trace_RSS_MiB": maximum / 2**20,
        "host_min_MemAvailable_GiB": min(
            int(value["host_mem_available"]) for value in rows
            if value["host_mem_available"]
        ) / 2**30,
    }


def rows(root: Path, include_trace: bool) -> list[dict[str, object]]:
    result = []
    for count, slug in SIZES:
        record = {"N": count, **time_record(root / slug)}
        if include_trace and record["status"] == "PASS":
            record.update(trace_record(root / slug))
            evidence = root / slug / "evidence.json"
            if evidence.is_file():
                value = json.loads(evidence.read_text())
                record.update(
                    tree_digest=value["canonical_tree_sha256"],
                    index_digest=value["index_sha256"],
                    leaf_assignment_digest=value["leaf_membership_sha256"],
                    tree_equivalent=value.get("comparison", {}).get("tree_unchanged"),
                    index_equivalent=value.get("comparison", {}).get("index_unchanged"),
                    leaf_assignment_equivalent=value.get("comparison", {}).get(
                        "leaf_assignment_unchanged"
                    ),
                )
        result.append(record)
    return result


def write_csv(path: Path, values: list[dict[str, object]]) -> None:
    fields = []
    for row in values:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(values)


def combine_traces() -> None:
    output = AUDIT / "QMF_MEMORY_STAGE_TRACE.csv"
    writer = None
    with output.open("w", newline="", encoding="utf-8") as destination:
        for count, slug in SIZES:
            path = AFTER / slug / "QMF_MEMORY_STAGE_TRACE.csv"
            if not path.is_file():
                continue
            with path.open(newline="", encoding="utf-8") as source:
                reader = csv.DictReader(source)
                if writer is None:
                    writer = csv.DictWriter(destination,
                                            fieldnames=["profile_points", *reader.fieldnames])
                    writer.writeheader()
                for row in reader:
                    writer.writerow({"profile_points": count, **row})


def main() -> int:
    before = rows(BEFORE, False)
    after = rows(AFTER, True)
    write_csv(AUDIT / "QMF_MEMORY_SCALING_BEFORE.csv", before)
    write_csv(AUDIT / "QMF_MEMORY_SCALING_AFTER.csv", after)
    measured = [row for row in after if row["status"] == "PASS"]
    if len(measured) >= 2:
        x = np.asarray([row["N"] for row in measured], dtype=np.float64)
        y = np.asarray([row["peak_RSS_MiB"] for row in measured], dtype=np.float64)
        slope, intercept = np.polyfit(x, y, 1)
        predictions = {str(size): float(intercept + slope * size)
                       for size in (181_000_000, 183_000_000, 204_986_702)}
        (AUDIT / "QMF_MEMORY_MODEL_20260914.json").write_text(json.dumps({
            "model": "descriptive ordinary least squares: Peak_RSS_MiB = intercept + slope * N",
            "profile_points": [int(value) for value in x],
            "slope_MiB_per_point": float(slope),
            "intercept_MiB": float(intercept),
            "predictions_MiB": predictions,
            "scientific_scope": "engineering admission model only; not an asymptotic claim",
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    combine_traces()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
