"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import json

import os

import shutil

import subprocess

import sys

import time

from pathlib import Path

import pandas as pd

from ..core.paths import project_root

from .protocol import PRIMARY_METHODS, load_config, resolved, sha256_file

QUERY_READY_PERSISTENCE = {
    "qmap_uniform_qmf": True,
    "postgis_gist": True,
    "lisa": False,
    "rsmi": False,
    "flood": False,
    "tsunami": True,
    "lmsfc": True,
    "bmtree": True,
}

def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _run(command, *, timeout: int, log: Path | None = None, env: dict | None = None):
    values = [str(value) for value in command]
    print("+", " ".join(values), flush=True)
    completed = subprocess.run(
        values,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=env,
    )
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            f"returncode={completed.returncode}\n\nSTDOUT\n{completed.stdout}\n\nSTDERR\n{completed.stderr}",
            encoding="utf-8",
        )
    return completed

def _psql(database: str, sql: str, *, tuples: bool = False, timeout: int = 3600) -> str:
    command = ["psql", "-v", "ON_ERROR_STOP=1", "-d", database]
    if tuples:
        command.extend(("-At", "-F", ","))
    command.extend(("-c", sql))
    completed = _run(command, timeout=timeout)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "psql command failed")
    return completed.stdout.strip()

def _verify_stage_a(config,output):
    from qmapli.repro import verify_stage_a
    verify_stage_a()

def _table_matches(database: str, table: str, metadata: dict) -> bool:
    sql = (
        "SELECT CASE WHEN to_regclass('public." + table + "') IS NULL THEN '0' ELSE "
        "(SELECT count(*)::text FROM " + table + ") END"
    )
    try:
        count = int(_psql(database, sql, tuples=True).splitlines()[-1])
    except (RuntimeError, ValueError, IndexError):
        return False
    return count == int(metadata["point_count"])

def _load_postgis_table(config: dict, metadata: dict, work: Path) -> None:
    database = config["postgresql"]["database"]
    table = config["postgresql"]["table"]
    if _table_matches(database, table, metadata):
        return
    sql = f"""
DROP TABLE IF EXISTS {table} CASCADE;
CREATE TABLE {table} (
    id BIGINT PRIMARY KEY,
    lon DOUBLE PRECISION NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    geom geometry(Point,4326) GENERATED ALWAYS AS
      (ST_SetSRID(ST_MakePoint(lon,lat),4326)) STORED
);
ALTER TABLE {table} ALTER COLUMN geom SET NOT NULL;
"""
    _psql(database, sql)
    copy_script = work / "load_points.sql"
    source = Path(metadata["raw_points_path"])
    copy_script.write_text(
        f"\\set ON_ERROR_STOP on\n\\copy {table}(id,lon,lat) FROM '{source}' WITH (FORMAT csv, HEADER true)\n",
        encoding="utf-8",
    )
    completed = _run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-d", database, "-f", copy_script],
        timeout=7200,
        log=work / "logs/load_postgis_table.log",
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "GeoLife PostgreSQL import failed")
    _psql(database, f"ANALYZE {table};")
    if not _table_matches(database, table, metadata):
        raise RuntimeError("PostgreSQL table row count differs from frozen dataset")

def _read_prepared(work: Path) -> dict:
    path = work / "prepare_status.json"
    if not path.is_file():
        raise RuntimeError("prepare phase has not completed")
    return json.loads(path.read_text(encoding="utf-8"))

def _sample_process_rss(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError):
        pass
    return 0

def _build_postgis(config: dict, work: Path) -> list[dict]:
    database = config["postgresql"]["database"]
    table = config["postgresql"]["table"]
    rows = []
    repetitions = int(config["benchmark"]["build_repetitions"])
    for repetition in range(repetitions):
        application = f"qmap_postgis_build_{repetition}"
        sql = (
            f"SET application_name='{application}'; DROP INDEX IF EXISTS {table}_gist; "
            f"CREATE INDEX {table}_gist ON {table} USING GIST (geom); ANALYZE {table};"
        )
        started = time.perf_counter()
        process = subprocess.Popen(
            ["psql", "-v", "ON_ERROR_STOP=1", "-d", database, "-c", sql],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        backend_pid = 0
        peak_kib = 0
        while process.poll() is None:
            peak_kib = max(peak_kib, _sample_process_rss(process.pid))
            if not backend_pid:
                lookup = subprocess.run(
                    ["psql", "-At", "-d", database, "-c",
                     f"SELECT pid FROM pg_stat_activity WHERE application_name='{application}' LIMIT 1"],
                    text=True, capture_output=True, check=False,
                )
                try:
                    backend_pid = int(lookup.stdout.strip())
                except ValueError:
                    backend_pid = 0
            if backend_pid:
                peak_kib = max(peak_kib, _sample_process_rss(backend_pid) + _sample_process_rss(process.pid))
            time.sleep(0.02)
        stdout, stderr = process.communicate()
        elapsed = time.perf_counter() - started
        status = "BUILT" if process.returncode == 0 else "INVALID_BUILD"
        size = None
        if status == "BUILT":
            size = int(_psql(database, f"SELECT pg_relation_size('{table}_gist')", tuples=True).splitlines()[-1])
        rows.append(
            {
                "method": "PostGIS-GiST", "runtime_method": "postgis_gist",
                "repetition": repetition, "status": status, "build_seconds": elapsed,
                "serialized_bytes": size, "reported_index_bytes": size,
                "peak_rss_kib": peak_kib, "query_ready_persistence": True,
                "index_path": f"postgresql://{database}/{table}_gist",
                "reason": stderr.strip() if process.returncode else "",
            }
        )
        (work / "logs").mkdir(parents=True, exist_ok=True)
        (work / f"logs/build_postgis_{repetition}.log").write_text(
            f"STDOUT\n{stdout}\nSTDERR\n{stderr}", encoding="utf-8"
        )
    return rows

def _build_qmf(config: dict, prepared: dict, work: Path, index_root: Path) -> list[dict]:
    rows = []
    qmf = config["qmf"]
    query_dir = work / "queries"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root() / "src/common/python")
    for repetition in range(int(config["benchmark"]["build_repetitions"])):
        directory = work / "build/qmf" / f"rep{repetition}"
        directory.mkdir(parents=True, exist_ok=True)
        index = directory / "qmap_uniform_qmf.idx"
        metadata_path = directory / "metadata.json"
        index.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        command = (
            sys.executable, "-m", "qmapli.wg_qmf.build_static_qw_index",
            "--mode", "uniform_qmf", "--r4-checkpoint", resolved(qmf["r4_checkpoint"]),
            "--points", prepared["dataset"]["normalized_points_path"],
            "--train-queries", query_dir / "train_normalized.csv",
            "--index", index, "--metadata", metadata_path,
            "--context-seed", int(config["queries"]["generator_seed"]),
            "--beta-leaf", qmf["beta_leaf"], "--beta-point", qmf["beta_point"],
            "--max-depth", qmf["max_depth"], "--min-leaf-size", qmf["min_leaf_size"],
            "--max-leaves", qmf["max_leaves"], "--budget-factor", qmf["budget_sqrt_factor"],
        )
        try:
            completed = _run(
                command,
                timeout=int(config["benchmark"]["build_timeout_seconds"]),
                log=work / f"logs/build_qmf_{repetition}.log",
                env=env,
            )
        except subprocess.TimeoutExpired as error:
            rows.append(
                {
                    "method": "QMF-Index", "runtime_method": "qmap_uniform_qmf",
                    "repetition": repetition, "status": "BUILD_RESOURCE_BLOCKED",
                    "reason": f"pre-registered timeout after {error.timeout} seconds",
                }
            )
            break
        if completed.returncode or not index.is_file() or not metadata_path.is_file():
            rows.append(
                {"method": "QMF-Index", "runtime_method": "qmap_uniform_qmf",
                 "repetition": repetition, "status": "INVALID_BUILD", "reason": completed.stderr.strip()}
            )
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("online_quantum_search") or metadata.get("online_python_controller"):
            raise RuntimeError("QMF online execution invariant failed")
        rows.append(
            {
                "method": "QMF-Index", "runtime_method": "qmap_uniform_qmf",
                "repetition": repetition, "status": "BUILT",
                "build_seconds": metadata["index_build_seconds"],
                "serialized_bytes": metadata["serialized_bytes"],
                "reported_index_bytes": metadata["serialized_bytes"],
                "peak_rss_kib": metadata["peak_rss_kib"],
                "query_ready_persistence": True, "index_path": str(index),
                "metadata_path": str(metadata_path), "reason": "",
            }
        )
        if repetition == 0:
            shutil.copy2(index, index_root / "qmap_uniform_qmf.idx")
    return rows

def _prepare_bmtree(work: Path, points: Path, train: Path, repetition: int, timeout: int) -> tuple[Path, float, int]:
    source_result = _run(["bash", project_root() / "scripts/prepare_bmtree_worktree.sh"], timeout=600)
    if source_result.returncode:
        raise RuntimeError(source_result.stderr.strip() or "BMTree worktree unavailable")
    source = Path(source_result.stdout.strip().splitlines()[-1])
    directory = work / "build/bmtree" / f"rep{repetition}"
    directory.mkdir(parents=True, exist_ok=True)
    model = directory / "bmtree.model"
    metadata = directory / "bmtree_model.json"
    rss_path = directory / "export_peak_rss_kib.txt"
    model.unlink(missing_ok=True)
    metadata.unlink(missing_ok=True)
    rss_path.unlink(missing_ok=True)
    started = time.perf_counter()
    completed = _run(
        ["/usr/bin/time", "-f", "%M", "-o", rss_path,
         sys.executable, project_root() / "scripts/export_bmtree_model.py",
         "--source", source, "--points", points, "--train-queries", train,
         "--output", model, "--metadata", metadata, "--seed", 1],
        timeout=timeout,
        log=work / f"logs/build_bmtree_model_{repetition}.log",
    )
    elapsed = time.perf_counter() - started
    if completed.returncode or not model.is_file():
        raise RuntimeError(completed.stderr.strip() or "BMTree official model export failed")
    try:
        peak_rss_kib = int(rss_path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        peak_rss_kib = 0
    return model, elapsed, peak_rss_kib

def _build_baseline(
    runtime: str, display: str, repetition: int, config: dict, prepared: dict,
    work: Path, index_root: Path,
) -> dict:
    build_root = Path(os.environ.get(
        "QMAP_BUILD_ROOT", Path(os.environ["QMF_RUNTIME"]) / "build"
    ))
    directory = work / "build" / runtime / f"rep{repetition}"
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / f"{runtime}.idx"
    result = directory / "build.csv"
    index.unlink(missing_ok=True)
    result.unlink(missing_ok=True)
    train = work / "queries/train_normalized.csv"
    validation = work / "queries/validation_normalized.csv"
    command: list[object] = [
        build_root / "bin/qmap_build_index", "--method", runtime,
        "--points", prepared["dataset"]["normalized_points_path"],
        "--train-queries", train, "--validation-queries", validation,
        "--index", index, "--output", result,
    ]
    method_specific_seconds = 0.0
    method_specific_peak_kib = 0
    if runtime == "bmtree":
        model, method_specific_seconds, method_specific_peak_kib = _prepare_bmtree(
            work, Path(prepared["dataset"]["normalized_points_path"]), train, repetition,
            int(config["benchmark"]["build_timeout_seconds"]),
        )
        command.extend(("--bmtree-model", model))
    if runtime == "rsmi":
        model_prefix = work / "build/rsmi/models" / f"rep{repetition}"
        model_prefix.parent.mkdir(parents=True, exist_ok=True)
        command.extend(("--rsmi-model-prefix", model_prefix))
    timeout = int(config["benchmark"][
        "rsmi_build_timeout_seconds" if runtime == "rsmi" else "build_timeout_seconds"
    ])
    completed = _run(command, timeout=timeout, log=work / f"logs/build_{runtime}_{repetition}.log")
    if completed.returncode or not result.is_file() or not index.is_file():
        return {
            "method": display, "runtime_method": runtime, "repetition": repetition,
            "status": "INVALID_BUILD", "reason": completed.stderr.strip() or "build output missing",
        }
    values = pd.read_csv(result).iloc[0]
    row = {
        "method": display, "runtime_method": runtime, "repetition": repetition,
        "status": "BUILT", "build_seconds": float(values.total_ns) / 1e9 + method_specific_seconds,
        "serialized_bytes": int(values.file_bytes),
        "reported_index_bytes": int(values.reported_index_bytes),
        "peak_rss_kib": max(int(values.peak_rss_kib), method_specific_peak_kib),
        "query_ready_persistence": QUERY_READY_PERSISTENCE[runtime],
        "index_path": str(index), "reason": "",
    }
    if repetition == 0:
        shutil.copy2(index, index_root / f"{runtime}.idx")
    return row

def _write_build_tables(output: Path, rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "baseline_build_status.csv", index=False)
    frame.to_csv(output / "build_time.csv", index=False)
    sizes = frame.copy()
    if not sizes.empty:
        sizes["index_size_metric_bytes"] = sizes.apply(
            lambda row: (
                row.get("serialized_bytes")
                if pd.notna(row.get("query_ready_persistence"))
                and bool(row.get("query_ready_persistence"))
                else None
            ),
            axis=1,
        )
    sizes.to_csv(output / "index_size.csv", index=False)
    return frame

def build(config: dict) -> pd.DataFrame:
    output = resolved(config["paths"]["output"])
    work = resolved(config["paths"]["work_root"])
    _verify_stage_a(config, output)
    prepared = _read_prepared(work)
    index_root = work / "indexes"
    index_root.mkdir(parents=True, exist_ok=True)
    rows = []
    rows.extend(_build_postgis(config, work))
    _write_build_tables(output, rows)
    rows.extend(_build_qmf(config, prepared, work, index_root))
    _write_build_tables(output, rows)
    for display, runtime in PRIMARY_METHODS:
        if runtime in ("postgis_gist", "qmap_uniform_qmf"):
            continue
        for repetition in range(int(config["benchmark"]["build_repetitions"])):
            try:
                row = _build_baseline(runtime, display, repetition, config, prepared, work, index_root)
            except subprocess.TimeoutExpired as error:
                row = {
                    "method": display, "runtime_method": runtime, "repetition": repetition,
                    "status": "BUILD_RESOURCE_BLOCKED",
                    "reason": f"pre-registered timeout after {error.timeout} seconds",
                }
            except Exception as error:
                row = {
                    "method": display, "runtime_method": runtime, "repetition": repetition,
                    "status": "INVALID_BUILD", "reason": str(error),
                }
            rows.append(row)
            _write_build_tables(output, rows)
            if row["status"] != "BUILT":
                break
    frame = _write_build_tables(output, rows)
    qmf_rows = []
    qmf_metadata = frame[
        (frame.runtime_method == "qmap_uniform_qmf") & (frame.status == "BUILT")
    ].get("metadata_path", pd.Series(dtype=str)).dropna()
    for value_path in qmf_metadata:
        path = Path(value_path)
        value = json.loads(path.read_text(encoding="utf-8"))
        total = float(value["index_build_seconds"])
        components = {
            "stage_a_scoring_seconds": float(value["prior_scoring_seconds"]),
            "configuration_generation_seconds": float(value["configuration_generation_seconds"]),
            "oracle_generation_seconds": float(value["oracle_cost_seconds"]),
            "qmf_simulator_seconds": float(value["quantum_search_simulator_seconds"]),
        }
        components["tree_materialization_seconds"] = max(total - sum(components.values()), 0.0)
        qmf_rows.append({"repetition": int(path.parent.name[3:]), "total_build_seconds": total, **components})
    pd.DataFrame(qmf_rows, columns=(
        "repetition", "total_build_seconds", "stage_a_scoring_seconds",
        "configuration_generation_seconds", "oracle_generation_seconds",
        "qmf_simulator_seconds", "tree_materialization_seconds",
    )).to_csv(output / "qmf_offline_breakdown.csv", index=False)
    return frame

def _valid_builds(output: Path) -> dict[str, str]:
    frame = pd.read_csv(output / "baseline_build_status.csv")
    statuses = {}
    for display, runtime in PRIMARY_METHODS:
        rows = frame[frame.runtime_method == runtime]
        statuses[runtime] = "BUILT" if len(rows) >= 3 and (rows.status == "BUILT").all() else (
            str(rows.iloc[0].status) if len(rows) else "NOT_BUILT"
        )
    return statuses

def benchmark(config: dict) -> None:
    output = resolved(config["paths"]["output"])
    work = resolved(config["paths"]["work_root"])
    _verify_stage_a(config, output)
    prepared = _read_prepared(work)
    statuses = _valid_builds(output)
    build_root = Path(os.environ.get(
        "QMAP_BUILD_ROOT", Path(os.environ["QMF_RUNTIME"]) / "build"
    ))
    executable = build_root / "bin/qmap_postgres_pilot"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    cpu = min(os.sched_getaffinity(0))
    query_file = resolved(config["paths"]["query_csv"])
    if sha256_file(query_file) != prepared["queries"]["combined_sha256"]:
        raise RuntimeError("frozen query SHA differs from the prepared protocol")
    raw_frames = []
    correctness_frames = []
    summaries = []
    for display, runtime in PRIMARY_METHODS:
        method_work = work / "benchmark" / runtime
        method_work.mkdir(parents=True, exist_ok=True)
        if statuses[runtime] != "BUILT":
            summaries.append({
                "method": display, "runtime_method": runtime, "status": statuses[runtime],
                "reason": "three complete frozen-data builds were not available",
            })
            _write_benchmark_tables(output, correctness_frames, raw_frames, summaries)
            continue
        correctness_path = method_work / "correctness.csv"
        latency_path = method_work / "latency.csv"
        summary_path = method_work / "summary.csv"
        for path in (correctness_path, latency_path, summary_path):
            path.unlink(missing_ok=True)
        command = [
            "taskset", "-c", cpu, executable,
            "--conninfo", f"dbname={config['postgresql']['database']} application_name=qmap_pilot_{runtime}",
            "--method", runtime, "--table", config["postgresql"]["table"],
            "--queries", query_file, "--repetitions", config["benchmark"]["query_repetitions"],
            "--index-root", work / "indexes",
            "--source-xmin", prepared["dataset"]["longitude_min"],
            "--source-xmax", prepared["dataset"]["longitude_max"],
            "--source-ymin", prepared["dataset"]["latitude_min"],
            "--source-ymax", prepared["dataset"]["latitude_max"],
            "--correctness-output", correctness_path,
            "--latency-output", latency_path,
            "--summary-output", summary_path,
        ]
        try:
            completed = _run(
                command,
                timeout=int(config["benchmark"]["query_timeout_seconds"]),
                log=work / f"logs/benchmark_{runtime}.log",
            )
            if completed.returncode or not all(path.is_file() for path in (correctness_path, latency_path, summary_path)):
                raise RuntimeError(completed.stderr.strip() or "benchmark output missing")
            correctness = pd.read_csv(correctness_path)
            latency = pd.read_csv(latency_path)
            summary = pd.read_csv(summary_path)
            correctness["method_display"] = display
            latency["method_display"] = display
            summary["method_display"] = display
            summary["runtime_method"] = runtime
            summary["status"] = "VALID" if (
                len(correctness) == 5000 and int(correctness.missing.sum()) == 0
                and int(correctness.extra.sum()) == 0 and int(correctness.exact.sum()) == 5000
            ) else "INVALID_CORRECTNESS"
            correctness_frames.append(correctness)
            raw_frames.append(latency)
            summaries.extend(summary.to_dict("records"))
        except Exception as error:
            summaries.append({
                "method": display, "runtime_method": runtime,
                "status": "INVALID_BENCHMARK", "reason": str(error),
            })
        _write_benchmark_tables(output, correctness_frames, raw_frames, summaries)
    _write_benchmark_tables(output, correctness_frames, raw_frames, summaries)

def _write_benchmark_tables(
    output: Path, correctness_frames: list[pd.DataFrame],
    raw_frames: list[pd.DataFrame], summaries: list[dict],
) -> None:
    if correctness_frames:
        pd.concat(correctness_frames, ignore_index=True).to_csv(output / "correctness_results.csv", index=False)
    else:
        pd.DataFrame(columns=(
            "method", "query_id", "selectivity_group", "truth_count", "result_count",
            "missing", "extra", "exact", "method_display",
        )).to_csv(output / "correctness_results.csv", index=False)
    if raw_frames:
        pd.concat(raw_frames, ignore_index=True).to_csv(output / "query_latency_raw.csv", index=False)
    else:
        pd.DataFrame(columns=(
            "method", "repetition", "ordinal", "query_id", "selectivity_group",
            "latency_ns", "result_count", "method_display",
        )).to_csv(output / "query_latency_raw.csv", index=False)
    pd.DataFrame(summaries).to_csv(output / "benchmark_run_status.csv", index=False)
