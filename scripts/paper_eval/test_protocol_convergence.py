"""The formal runner imports one immutable protocol definition."""

from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cgroup_policy
import orchestrate
import paper_protocol as protocol
import report
import run
import support
import worker


def test_protocol_frozen():
    assert protocol.QUERY_COUNTS == {
        "train": 1000, "validation": 1000, "correctness": 1000,
        "warmup": 300, "performance": 3000, "total": 6300,
    }
    assert protocol.PERFORMANCE_REPETITIONS == 5
    assert protocol.BUILD_REPETITIONS == 1
    assert protocol.PROTOCOL["qmf_memory_engineering_production_change"] is True
    assert protocol.PROTOCOL["qmf_algorithm_changed"] is False
    assert protocol.DATASETS == tuple(item[0] for item in protocol.DATASET_SPECS)
    assert len(protocol.DATASETS) == 4 and len(protocol.METHODS) == 8
    assert len(protocol.METRICS) == 7


def test_single_protocol_source_identity():
    assert support.METHODS is protocol.METHODS
    assert support.METRICS is protocol.METRICS
    assert support.RUN is protocol.RUNTIME_ROOT
    assert support.OUT is protocol.RESULT_ROOT
    assert run.PROTOCOL is protocol.PROTOCOL
    assert run.TIMEOUTS_S is protocol.TIMEOUTS_S
    assert orchestrate.TIMEOUTS_S is protocol.TIMEOUTS_S
    assert worker.QUERY_COUNTS is protocol.QUERY_COUNTS
    assert report.QUERY_COUNTS is protocol.QUERY_COUNTS
    assert report.PERFORMANCE_REPETITIONS == protocol.PERFORMANCE_REPETITIONS


def test_build_timeout_uniform():
    assert protocol.TIMEOUTS_S["build"] == 43200
    assert not hasattr(protocol, "QMF_BUILD_TIMEOUT")


def test_memory_policy_frozen():
    assert protocol.MEMORY_HIGH == 22 * protocol.GIB
    assert protocol.MEMORY_MAX == 24 * protocol.GIB
    assert protocol.MEMORY_SWAP_MAX == 0
    assert protocol.HOST_EMERGENCY_RESERVE == 7 * protocol.GIB // 2
    assert cgroup_policy.MEMORY_HIGH == protocol.MEMORY_HIGH
    assert cgroup_policy.MEMORY_MAX == protocol.MEMORY_MAX


def test_status_taxonomy_frozen():
    expected = {
        "PASS", "HOST_SAFETY_STOP", "CGROUP_MEMORY_MAX", "OOM_KILLED",
        "SWAP_INVALID", "BUILD_FAILED", "CORRECTNESS_FAILED", "WARMUP_FAILED",
        "TIMING_FAILED", "FINALIZATION_FAILED", "REPORTING_FAILED", "TIMEOUT",
    }
    assert protocol.STATUSES == expected
    assert protocol.RETRY_ELIGIBLE_STATUSES == expected - {"PASS"}


def test_unified_cli_dry_run_does_not_start_service(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run attempted an external process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    run.dry_run_plan()
    output = capsys.readouterr().out
    assert '"will_start_service": false' in output
    assert '"performance": 3000' in output
