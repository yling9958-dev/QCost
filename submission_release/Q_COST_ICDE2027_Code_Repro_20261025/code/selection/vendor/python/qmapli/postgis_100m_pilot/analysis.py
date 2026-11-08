"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import json

from pathlib import Path

import numpy as np

import pandas as pd

from .protocol import PRIMARY_METHODS, PRIMARY_METRICS, load_config, resolved

DISPLAY_ORDER = tuple(display for display, _runtime in PRIMARY_METHODS)

def percentage_improvement(qmf: float, baseline: float, direction: str) -> float:
    if not np.isfinite(qmf) or not np.isfinite(baseline) or baseline == 0:
        return np.nan
    if direction == "lower":
        return 100.0 * (baseline - qmf) / baseline
    if direction == "higher":
        return 100.0 * (qmf - baseline) / baseline
    raise ValueError(direction)

def metric_ranks(values: pd.Series, direction: str) -> pd.Series:
    return values.rank(method="min", ascending=direction == "lower", na_option="keep")

def _aggregate_query(frame: pd.DataFrame) -> dict[str, float]:
    values = frame.latency_ns.to_numpy(dtype=np.float64)
    return {
        "MeanLatency_ms": float(values.mean() / 1e6),
        "P95Latency_ms": float(np.quantile(values, 0.95) / 1e6),
        "P99Latency_ms": float(np.quantile(values, 0.99) / 1e6),
        "QPS": float(1e9 / values.mean()),
    }

def _bootstrap_statistic(values: np.ndarray, metric: str) -> float:
    if metric == "MeanLatency_ms":
        return float(values.mean() / 1e6)
    if metric == "P95Latency_ms":
        return float(np.quantile(values, 0.95) / 1e6)
    if metric == "P99Latency_ms":
        return float(np.quantile(values, 0.99) / 1e6)
    if metric == "QPS":
        return float(1e9 / values.mean())
    raise ValueError(metric)

def paired_query_ci(
    raw: pd.DataFrame,
    left_runtime: str,
    right_runtime: str,
    metric: str,
    *,
    samples: int,
    seed: int,
) -> tuple[float, float, float, int]:
    columns = ["repetition", "query_id", "latency_ns"]
    left = raw[raw.method == left_runtime][columns].rename(columns={"latency_ns": "left"})
    right = raw[raw.method == right_runtime][columns].rename(columns={"latency_ns": "right"})
    paired = left.merge(right, on=["repetition", "query_id"], validate="one_to_one")
    if paired.empty:
        return np.nan, np.nan, np.nan, 0
    left_values = paired.left.to_numpy(dtype=np.float64)
    right_values = paired.right.to_numpy(dtype=np.float64)
    observed = _bootstrap_statistic(left_values, metric) - _bootstrap_statistic(right_values, metric)
    per_run = []
    for _repetition, group in paired.groupby("repetition", sort=True):
        per_run.append(
            _bootstrap_statistic(group.left.to_numpy(dtype=np.float64), metric)
            - _bootstrap_statistic(group.right.to_numpy(dtype=np.float64), metric)
        )
    per_run = np.asarray(per_run, dtype=np.float64)
    rng = np.random.default_rng(seed)
    statistics = rng.choice(
        per_run, size=(samples, len(per_run)), replace=True
    ).mean(axis=1)
    low, high = np.quantile(statistics, (0.025, 0.975))
    return float(observed), float(low), float(high), len(per_run)

def _status_maps(output: Path) -> tuple[dict[str, str], dict[str, str]]:
    build = pd.read_csv(output / "baseline_build_status.csv")
    run = pd.read_csv(output / "benchmark_run_status.csv")
    build_status = {}
    run_status = {}
    for display, runtime in PRIMARY_METHODS:
        rows = build[build.runtime_method == runtime]
        build_status[runtime] = "BUILT" if len(rows) >= 3 and (rows.status == "BUILT").all() else (
            str(rows.iloc[0].status) if len(rows) else "NOT_BUILT"
        )
        query = run[run.runtime_method == runtime]
        run_status[runtime] = str(query.iloc[0].status) if len(query) else build_status[runtime]
    return build_status, run_status

def _correctness_summary(output: Path, run_status: dict[str, str]) -> pd.DataFrame:
    path = output / "correctness_results.csv"
    raw = pd.read_csv(path) if path.is_file() and path.stat().st_size else pd.DataFrame()
    rows = []
    for display, runtime in PRIMARY_METHODS:
        frame = raw[raw.method == runtime] if "method" in raw else pd.DataFrame()
        missing = int(frame.missing.sum()) if len(frame) else np.nan
        extra = int(frame.extra.sum()) if len(frame) else np.nan
        exact = int(frame.exact.sum()) if len(frame) else 0
        valid = len(frame) == 5000 and missing == 0 and extra == 0 and exact == 5000
        rows.append(
            {
                "Method": display, "runtime_method": runtime,
                "queries": len(frame), "exact_matches": exact,
                "missing_ids": missing, "extra_ids": extra,
                "precision": 1.0 if valid else np.nan,
                "recall": 1.0 if valid else np.nan,
                "Correctness": "VALID" if valid else run_status[runtime],
            }
        )
    summary = pd.DataFrame(rows)
    summary.to_csv(output / "correctness_summary.csv", index=False)
    return summary

def _query_tables(output: Path, correctness: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = output / "query_latency_raw.csv"
    try:
        raw = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raw = pd.DataFrame()
    valid_runtime = set(correctness[correctness.Correctness == "VALID"].runtime_method)
    rows = []
    selectivity_rows = []
    for display, runtime in PRIMARY_METHODS:
        frame = raw[raw.method == runtime] if "method" in raw else pd.DataFrame()
        if runtime not in valid_runtime or len(frame) != 75_000 or frame.repetition.nunique() != 5:
            rows.append({"Method": display, "runtime_method": runtime, "scope": "aggregate"})
            continue
        rows.append({
            "Method": display, "runtime_method": runtime, "scope": "aggregate",
            "repetition": "ALL", "observations": len(frame), **_aggregate_query(frame),
        })
        for repetition, group in frame.groupby("repetition", sort=True):
            rows.append({
                "Method": display, "runtime_method": runtime, "scope": "repetition",
                "repetition": int(repetition), "observations": len(group), **_aggregate_query(group),
            })
        for selectivity, group in frame.groupby("selectivity_group", sort=True):
            selectivity_rows.append({
                "Method": display, "runtime_method": runtime,
                "selectivity_group": selectivity, "observations": len(group), **_aggregate_query(group),
            })
    metrics = pd.DataFrame(rows)
    selectivity = pd.DataFrame(selectivity_rows)
    metrics.to_csv(output / "query_metrics.csv", index=False)
    selectivity.to_csv(output / "selectivity_metrics.csv", index=False)
    return metrics, selectivity

def _fairness(output: Path) -> pd.DataFrame:
    run = pd.read_csv(output / "benchmark_run_status.csv")
    rows = []
    for display, runtime in PRIMARY_METHODS:
        frame = run[run.runtime_method == runtime]
        if frame.empty or frame.iloc[0].status != "VALID":
            rows.append({
                "Method": display, "runtime_method": runtime,
                "status": frame.iloc[0].status if len(frame) else "NOT_RUN",
            })
            continue
        if runtime == "postgis_gist":
            counters = {key: 0 for key in (
                "query_rebuild_count", "query_reload_count", "query_training_count",
                "query_external_process_count", "query_python_count", "query_quantum_count",
            )}
            counters["load_count"] = 1
        else:
            counters = json.loads(frame.iloc[0].fairness_json)
        valid = all(int(counters.get(key, -1)) == 0 for key in (
            "query_rebuild_count", "query_reload_count", "query_training_count",
            "query_external_process_count", "query_python_count", "query_quantum_count",
        ))
        rows.append({
            "Method": display, "runtime_method": runtime,
            "status": "PASS" if valid else "FAIL", **counters,
        })
    result = pd.DataFrame(rows)
    result.to_csv(output / "postgresql_fairness_audit.csv", index=False)
    return result

def _primary_table(
    output: Path, correctness: pd.DataFrame, query: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    build = pd.read_csv(output / "baseline_build_status.csv")
    run = pd.read_csv(output / "benchmark_run_status.csv")
    aggregate = query[query.scope == "aggregate"].set_index("runtime_method")
    rows = []
    for display, runtime in PRIMARY_METHODS:
        built = build[(build.runtime_method == runtime) & (build.status == "BUILT")]
        correct = correctness[correctness.runtime_method == runtime].iloc[0]
        query_row = aggregate.loc[runtime] if runtime in aggregate.index else pd.Series(dtype=float)
        query_ready = bool(
            len(built)
            and built.query_ready_persistence.map(
                lambda value: value is True or str(value).lower() == "true"
            ).all()
        )
        query_peak = run[run.runtime_method == runtime].get("total_peak_rss_kib", pd.Series(dtype=float))
        build_peak = built.get("peak_rss_kib", pd.Series(dtype=float))
        peak_values = pd.concat((query_peak, build_peak), ignore_index=True).dropna()
        rows.append(
            {
                "Method": display,
                "BuildTime_s": float(built.build_seconds.mean()) if len(built) >= 3 else np.nan,
                "IndexSize_MiB": float(built.serialized_bytes.mean() / 2**20) if query_ready else np.nan,
                "MeanLatency_ms": query_row.get("MeanLatency_ms", np.nan),
                "P95Latency_ms": query_row.get("P95Latency_ms", np.nan),
                "P99Latency_ms": query_row.get("P99Latency_ms", np.nan),
                "QPS": query_row.get("QPS", np.nan),
                "PeakMemory_MiB": float(peak_values.max() / 1024) if len(peak_values) else np.nan,
                "Correctness": correct.Correctness,
            }
        )
    primary = pd.DataFrame(rows)
    for metric, direction in PRIMARY_METRICS:
        values = primary[metric].where(primary.Correctness == "VALID")
        primary[f"Rank_{metric.replace('Latency_ms', '').replace('Time_s', '').replace('IndexSize_MiB', 'Size').replace('PeakMemory_MiB', 'Memory')}"] = metric_ranks(values, direction)
    primary = primary.rename(columns={
        "Rank_Build": "Rank_Build", "Rank_Mean": "Rank_Mean",
        "Rank_P95": "Rank_P95", "Rank_P99": "Rank_P99",
        "Rank_QPS": "Rank_QPS", "Rank_Size": "Rank_Size", "Rank_Memory": "Rank_Memory",
    })
    expected = [
        "Method", "BuildTime_s", "IndexSize_MiB", "MeanLatency_ms", "P95Latency_ms",
        "P99Latency_ms", "QPS", "PeakMemory_MiB", "Correctness", "Rank_Build",
        "Rank_Size", "Rank_Mean", "Rank_P95", "Rank_P99", "Rank_QPS", "Rank_Memory",
    ]
    primary = primary[expected]
    primary.to_csv(output / "primary_7_metric_table.csv", index=False)
    ranking_rows = []
    for metric, direction in PRIMARY_METRICS:
        rank_column = {
            "BuildTime_s": "Rank_Build", "IndexSize_MiB": "Rank_Size",
            "MeanLatency_ms": "Rank_Mean", "P95Latency_ms": "Rank_P95",
            "P99Latency_ms": "Rank_P99", "QPS": "Rank_QPS",
            "PeakMemory_MiB": "Rank_Memory",
        }[metric]
        for row in primary.itertuples(index=False):
            ranking_rows.append({
                "metric": metric, "direction": direction, "Method": row.Method,
                "value": getattr(row, metric), "rank": getattr(row, rank_column),
                "correctness": row.Correctness,
            })
    ranking = pd.DataFrame(ranking_rows)
    ranking.to_csv(output / "primary_7_metric_ranking.csv", index=False)
    percentages = []
    qmf = primary[primary.Method == "QMF-Index"].iloc[0]
    for baseline in primary[primary.Method != "QMF-Index"].itertuples(index=False):
        for metric, direction in PRIMARY_METRICS:
            percentages.append({
                "baseline": baseline.Method, "metric": metric,
                "qmf_value": qmf[metric], "baseline_value": getattr(baseline, metric),
                "improvement_percent": percentage_improvement(qmf[metric], getattr(baseline, metric), direction),
            })
    percentage = pd.DataFrame(percentages)
    percentage.to_csv(output / "qmf_percentage_vs_baselines.csv", index=False)
    return primary, ranking, percentage
