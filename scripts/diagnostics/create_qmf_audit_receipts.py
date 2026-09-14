#!/usr/bin/env python3
"""Bind audited source changes to tests and frozen 100 MiB equivalence evidence."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "scripts/paper_eval"
sys.path.insert(0, str(PAPER))

import run
import support as s


AUDIT = ROOT / "results/qmf_build_audit_cleanup_20260914"
EXPECTED_TREE = "a7c540d4d5f8e1b34e7508d2be921741203cc13667403fa8b7df587e03696230"
EXPECTED_INDEX = "12bbd47ef650888b67e042002d794e75de64ec5d91c0c2476eded5d85e577282"
EXPECTED_LEAF = "f114efb06770bc520743c3770fcb2ac95c710f58b6cea02748454b6eff7348fb"


def changed(expected, current):
    return {path: {"before": expected.get(path), "after": current.get(path)}
            for path in sorted(set(expected) | set(current))
            if expected.get(path) != current.get(path)}


def main() -> int:
    production_tests = AUDIT / "QMF_MEMORY_TESTS_20260914.xml"
    controller_tests = AUDIT / "PAPER_EVAL_TESTS_20260914.xml"
    if not run.passing_test_xml(production_tests) or not run.passing_test_xml(controller_tests):
        raise RuntimeError("passing test XML evidence is required")
    evidence = AUDIT / "equivalence/100mib"
    tree = s.sha(evidence / "tree_decision_manifest.csv")
    index = s.sha(evidence / "qmap_uniform_qmf.idx")
    metadata = s.read_json(evidence / "metadata.json")
    if (tree, index, metadata.get("leaf_membership_sha256")) != (
            EXPECTED_TREE, EXPECTED_INDEX, EXPECTED_LEAF):
        raise RuntimeError("100 MiB equivalence artifact differs from the frozen reference")

    original_path = s.OUT / "00_environment/production_source_before.json"
    original = s.read_json(original_path)
    current = run.source_manifest()
    production = {
        "amendment": "QMF memory ownership and observability implementation, 2026-09-14",
        "original_manifest_sha256": s.sha(original_path),
        "changed_production_files": changed(original, current),
        "current_production_source_manifest": current,
        "tests_sha256": s.sha(production_tests),
        "standalone_100m_tree_sha256": tree,
        "standalone_100m_index_sha256": index,
        "standalone_100m_leaf_assignment_sha256": metadata["leaf_membership_sha256"],
        "qmf_core_algorithm_changed": False,
        "dataset_changed": False,
        "query_protocol_changed": False,
        "memory_policy_changed": False,
        "cpu_protocol_changed": False,
        "full_scale_run_started": False,
    }
    s.atomic_json(AUDIT / "QMF_MEMORY_IMPLEMENTATION_SOURCE_20260914.json", production)

    frozen = s.read_json(s.OUT / "00_environment/paper_source_freeze.json")
    controller = {
        "amendment": "paper controller single-source configuration and unified CLI",
        "prior_control_manifests": [frozen],
        "current_source_manifest": {
            path.name: s.sha(path) for path in PAPER.iterdir()
            if path.suffix in (".py", ".cpp")
        },
        "tests_sha256": s.sha(controller_tests),
        "qmf_algorithm_changed": False,
        "dataset_changed": False,
        "query_protocol_changed": False,
        "memory_policy_changed": False,
        "auto_run_started": False,
    }
    s.atomic_json(AUDIT / "PAPER_CONTROLLER_SOURCE_20260914.json", controller)
    print(json.dumps({
        "production_changed_files": len(production["changed_production_files"]),
        "controller_files": len(controller["current_source_manifest"]),
        "tree_sha256": tree,
        "index_sha256": index,
        "leaf_assignment_sha256": metadata["leaf_membership_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
