"""Optional process/cgroup memory snapshots for build diagnostics."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import time
import tracemalloc


FIELDS = (
    "timestamp", "elapsed_s", "phase", "node_id", "node_depth", "node_points",
    "completed_nodes", "planned_max_nodes", "rss_bytes", "rss_peak_bytes",
    "pss_bytes", "process_tree_rss_bytes", "python_heap_bytes",
    "python_heap_peak_bytes", "cgroup_path", "cgroup_memory_current",
    "cgroup_memory_peak", "cgroup_anon", "cgroup_file", "cgroup_swap_current",
    "host_mem_available", "details_json",
)


def _status(pid="self"):
    result = {}
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmPeak:")):
                key, value, *_ = line.split()
                result[key.rstrip(":")] = int(value) * 1024
    except OSError:
        pass
    return result


def _pss():
    try:
        for line in Path("/proc/self/smaps_rollup").read_text().splitlines():
            if line.startswith("Pss:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _process_tree_rss():
    records = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            records[int(entry.name)] = int(fields[1])
        except (OSError, ValueError, IndexError):
            continue
    root = __import__("os").getpid()
    descendants = {root}
    changed = True
    while changed:
        changed = False
        for pid, parent in records.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sum(_status(pid).get("VmRSS", 0) for pid in descendants)


def _mem_available():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _cgroup():
    path = ""
    try:
        for line in Path("/proc/self/cgroup").read_text().splitlines():
            hierarchy, _controllers, value = line.split(":", 2)
            if hierarchy == "0":
                path = value
                break
    except OSError:
        return path, {}
    root = Path("/sys/fs/cgroup") / path.lstrip("/")
    values = {}
    for name in ("memory.current", "memory.peak", "memory.swap.current"):
        try:
            values[name] = int((root / name).read_text().strip())
        except (OSError, ValueError):
            values[name] = 0
    try:
        values.update({f"stat.{key}": int(value) for key, value in
                       (line.split() for line in (root / "memory.stat").read_text().splitlines())})
    except (OSError, ValueError):
        pass
    return path, values


class MemoryStageTrace:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        with self.path.open("w", newline="") as handle:
            csv.DictWriter(handle, fieldnames=FIELDS).writeheader()

    def emit(self, phase, *, node_id="", node_depth="", node_points="",
             completed_nodes="", planned_max_nodes="", **details):
        status = _status()
        cgroup_path, cgroup = _cgroup()
        python_current = python_peak = 0
        if tracemalloc.is_tracing():
            python_current, python_peak = tracemalloc.get_traced_memory()
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": f"{time.monotonic() - self.started:.6f}",
            "phase": phase,
            "node_id": node_id,
            "node_depth": node_depth,
            "node_points": node_points,
            "completed_nodes": completed_nodes,
            "planned_max_nodes": planned_max_nodes,
            "rss_bytes": status.get("VmRSS", 0),
            "rss_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "pss_bytes": _pss(),
            "process_tree_rss_bytes": _process_tree_rss(),
            "python_heap_bytes": python_current,
            "python_heap_peak_bytes": python_peak,
            "cgroup_path": cgroup_path,
            "cgroup_memory_current": cgroup.get("memory.current", 0),
            "cgroup_memory_peak": cgroup.get("memory.peak", 0),
            "cgroup_anon": cgroup.get("stat.anon", 0),
            "cgroup_file": cgroup.get("stat.file", 0),
            "cgroup_swap_current": cgroup.get("memory.swap.current", 0),
            "host_mem_available": _mem_available(),
            "details_json": json.dumps(details, sort_keys=True, separators=(",", ":")),
        }
        with self.path.open("a", newline="") as handle:
            csv.DictWriter(handle, fieldnames=FIELDS).writerow(row)
