#!/usr/bin/env python3
"""Summarize one QMF diagnostic build without modifying its artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_tree(path: Path) -> tuple[str, int]:
    with path.open(newline="", encoding="utf-8") as handle:
        source = list(csv.DictReader(handle))
    parents = {int(row["node_id"]): int(row["parent_id"]) for row in source}

    def depth(node_id: int) -> int:
        value = 0
        while parents[node_id] >= 0:
            node_id = parents[node_id]
            value += 1
        return value

    rows = []
    for row in source:
        node_id = int(row["node_id"])
        left = int(row.get("left_child", row.get("left", -1)))
        right = int(row.get("right_child", row.get("right", -1)))
        rows.append({
            "node_id": node_id,
            "parent_id": int(row["parent_id"]),
            "depth": int(row.get("depth") or depth(node_id)),
            "axis": int(row["axis"]),
            "threshold": row["threshold"],
            "left": left,
            "right": right,
            "start": int(row.get("point_start", row.get("start", 0))),
            "end": int(row.get("point_end", row.get("end", 0))),
            "bbox": row["bbox"],
        })
    payload = json.dumps(sorted(rows, key=lambda row: row["node_id"]),
                         sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest(), len(rows)


def time_evidence(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    maximum = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    elapsed = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([^\n]+)", text)
    return {
        "maximum_rss_kib": int(maximum.group(1)) if maximum else None,
        "elapsed_text": elapsed.group(1).strip() if elapsed else None,
    }


def trace_evidence(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"trace_available": False}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    sampled_peak = max(rows, key=lambda row: int(row["rss_bytes"]))
    cumulative_peak = max(int(row["rss_peak_bytes"]) for row in rows)
    peak_index = next(index for index, row in enumerate(rows)
                      if int(row["rss_peak_bytes"]) == cumulative_peak)
    peak_row = rows[peak_index]
    bounded_phase = peak_row["phase"]
    if bounded_phase.startswith("after_") and peak_index:
        prior = rows[peak_index - 1]["phase"]
        bounded_phase = f"between_{prior}_and_{bounded_phase}"
    return {
        "trace_available": True,
        "sample_count": len(rows),
        "peak_stage": bounded_phase,
        "peak_rss_bytes": cumulative_peak,
        "sampled_current_rss_peak_bytes": int(sampled_peak["rss_bytes"]),
        "sampled_current_rss_peak_stage": sampled_peak["phase"],
        "peak_pss_bytes": int(sampled_peak["pss_bytes"]) if sampled_peak["pss_bytes"] else None,
        "host_min_mem_available_bytes": min(
            int(row["host_mem_available"])
            for row in rows if row["host_mem_available"]
        ),
    }


def summarize(folder: Path) -> dict[str, object]:
    tree_digest, node_count = canonical_tree(folder / "tree_decision_manifest.csv")
    membership_path = folder / "leaf_membership.sha256"
    if membership_path.is_file():
        membership = membership_path.read_text().strip()
    else:
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        membership = metadata["leaf_membership_sha256"]
    evidence = {
        "folder": str(folder.resolve()),
        "index_bytes": (folder / "qmap_uniform_qmf.idx").stat().st_size,
        "index_sha256": sha256(folder / "qmap_uniform_qmf.idx"),
        "canonical_tree_sha256": tree_digest,
        "node_count": node_count,
        "leaf_membership_sha256": membership,
    }
    evidence.update(time_evidence(folder / "time.txt"))
    evidence.update(trace_evidence(folder / "QMF_MEMORY_STAGE_TRACE.csv"))
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    observed = summarize(args.profile)
    if args.compare:
        reference = summarize(args.compare)
        observed["comparison"] = {
            "reference": str(args.compare.resolve()),
            "index_unchanged": observed["index_sha256"] == reference["index_sha256"],
            "tree_unchanged": observed["canonical_tree_sha256"] == reference["canonical_tree_sha256"],
            "leaf_assignment_unchanged": (
                observed["leaf_membership_sha256"] == reference["leaf_membership_sha256"]
            ),
        }
    rendered = json.dumps(observed, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
