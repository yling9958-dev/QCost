# Build timeout protocol amendment — 2026-09-13

This is an experimental infrastructure timeout protocol amendment. It does not
change algorithms, input data, query workloads, correctness gates or metrics.

Old Build timeout: **14400 s (4 hours)**.

New Build timeout: **43200 s (12 hours)**, finite and uniform.

Scope: all eight formal paper benchmark methods, across all four full datasets:
QMF-Index, PostGIS GiST, LISA, Flood, Tsunami, LMSFC, BMTree and Boost R*-tree.
There is no QMF-specific exception.

Reason: full-scale 181M–205M point experiments demonstrated that the previous
4-hour infrastructure timeout can terminate an otherwise active build before
completion. The latest GeoLife QMF receipt records
`Predeclared phase timeout 14400s`; it does not establish an algorithm error,
OOM, or exhaustion of the 24 GiB hard limit.

Fairness: the new timeout applies uniformly to all methods. Existing PASS
methods completed under the stricter 14400 s limit and are retained unchanged.
No existing result is rerun, overwritten or selected again by this amendment.
No new performance claim follows merely from changing the timeout.

## Audited call chain

- `scripts/run_paper_benchmark.sh` only forwards CLI arguments to `run.py`.
- `phase_timeouts.py:TIMEOUTS_S` is the single source of formal phase limits.
  `run.PROTOCOL['timeouts_s']` and `orchestrate.TIMEOUTS_S` reference that same
  object; correctness and timing remain 43200 s.
- `run.foreground()` and `repair_geolife.attempt()` both use
  `orchestrate.run_method()` → `build_one()` → `monitor()`.
- QMF, all compiled baselines and BMTree model export explicitly pass the
  shared formal build limit. BMTree's subsequent index subprocess accounts
  for elapsed model-export time against the same total monitored build budget.
  Build-time and peak-memory measurement formulas are unchanged.
- The first PostGIS build reuses `postgis_reference.done`. Its reference GiST
  construction is charged as the formal PostGIS Build measurement, so its SQL
  call also uses 43200 s. Any later PostGIS build path uses the same limit.
  This is the necessary shared reference/formal-build exception identified by
  the source audit; leaving it at 14400 s would give PostGIS a different cap.
- Generic `monitor()` and `sql()` defaults remain 14400 s. Normalize, full-table
  load (including restoration adoption), and unrelated auxiliary operations
  retain their existing limits. Compile/query preparation and shorter SQL
  limits are unchanged. No project-wide replacement of 14400 was performed.
- At the new cap, the monitor still records `BUILD_FAILED` with the explicit
  reason `Predeclared phase timeout 43200s`. Timeout is not relabeled as an
  algorithm exception or memory exhaustion.

## Protocol and resume provenance

The original `00_environment/protocol.json` is preserved byte-for-byte as the
historical declaration. The companion
`BUILD_TIMEOUT_PROTOCOL_AMENDMENT_20260913.json` records its SHA256 and the full
effective protocol. Resume accepts only this exact build-timeout difference;
changes to workload, memory settings or other frozen fields still fail the gate.

GeoLife repair validates this amendment before execution and records the formal
build timeout in each new attempt's provenance. Existing failed receipts remain
unchanged now and will be preserved by the already-tested supersession logic
when the user explicitly launches a new retry.

The five scientifically valid methods remain skipped: PostGIS GiST, LISA,
Tsunami, LMSFC and BMTree. The retry queue remains exactly QMF-Index → Flood →
Boost R*-tree. The old QMF timeout and the two HOST_SAFETY_STOP outcomes remain
retry-eligible, not scientifically complete.

Before each method, existing admission checks still require no stale benchmark
worker/PostgreSQL 55445, experiment swap zero, and MemAvailable ≥24 GiB. Low
available memory causes waiting, not a method failure.

## Integrity and validation evidence

- `BUILD_TIMEOUT_PASS_SHA_BEFORE_20260913.json` and
  `BUILD_TIMEOUT_PASS_SHA_AFTER_20260913.json`: SHA256 verification of all
  PASS-associated artifacts, including measurements, timing and correctness.
- `build_timeout_tests_20260913.xml`: complete `scripts/paper_eval` regression
  suite, including all eight build dispatches, actual timeout-monitor behavior,
  old-timeout retry, PASS preservation, exact retry queue and import-without-run.
- `build_timeout_control_source_20260913.json`: tested orchestration source
  receipt, extending the existing source audit without rewriting old receipts.
- `archive/build_timeout_amendment_20260913/`: before snapshot, exact code diff,
  and verification of every pre-existing current result file, production
  source/config hashes, and raw/normalized file sizes and timestamps.

QMF algorithm changed: NO

Dataset changed: NO

Query protocol changed: NO

Correctness gate changed: NO

Resource limit changed: NO

MemoryHigh = 22 GiB; MemoryMax = 24 GiB; MemorySwapMax = 0;
host emergency reserve = 3.5 GiB.

AUTO_RUN_STARTED = NO. No repair, campaign, database or method is launched by
this modification, its tests or its audit.
