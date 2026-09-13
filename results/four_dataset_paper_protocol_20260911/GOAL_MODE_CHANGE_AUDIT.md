# Goal-mode change audit — final paper reset

The user-declared paper protocol supersedes the heavy campaign. No production QMF file is reverted or edited. The old results directory remains diagnostic evidence and is not an input source for new method metrics.

| Files or feature | Disposition | Paper behavior |
|---|---|---|
| `data_cache/full/*/points_normalized.csv`, normalized manifests | KEEP | Immutable persistent cache, outside removable method/dataset workspaces. GeoLife is reused, never reconverted. |
| `scripts/full_eval/support.py` checkpoint and resource utilities | KEEP | Isolated paper copy preserves atomic phase commits, hashes, process RSS definition, and missing values. |
| `scripts/full_eval/cgroup_policy.py` | KEEP | Fixed shared 22/24 GiB parent, swap zero; both PostgreSQL and phase worker are verified descendants. |
| `scripts/full_eval/orchestrate.py` lifecycle improvements | KEEP | Paper controller requires numeric CSV/Markdown/rank/hash persistence before dataset cleanup. Persistent normalized data survives cleanup and reporting failure. |
| `scripts/full_eval/analyze.py`, `test_orchestration.py`, `test_recovery.py`, `recovery.py` | KEEP / ARCHIVE | Robust empty/blocked analysis and normalization recovery remain available unchanged. Paper numeric reporting reads authoritative method checkpoints directly, so empty result CSVs cannot cause pandas EmptyDataError. Historical recovery entrypoint is not invoked. |
| `scripts/memory_recovery/policy.py`, `host_guard.py`, `audit.py` | KEEP policy / ARCHIVE implementation | Paper monitor directly enforces 3.5 GiB MemAvailable reserve at 100 ms intervals. No dynamic cap or Goal helper imports. Trigger, RSS, cgroup counters and kernel evidence are recorded. |
| `scripts/memory_recovery/correctness_policy.py` | KEEP policy / ARCHIVE implementation | Sorted SetOp policy applies only to correctness sessions, preserving the exact bidirectional ID difference SQL. No change to query kernels or timed SQL. |
| `scripts/memory_recovery/mapped_build.py`, `engineered.py`, `equivalence.py`, `candidate_policy.py`, tests | ARCHIVE / DISABLE | Allocation adapter was isolated and used only in the small equivalence pilot, never activated in full production. Paper uses the original standalone QMF build. Pilot tree/index and 5000 exact results are retained as evidence, not paper metrics. |
| `scripts/memory_recovery/gate.py`, `retry.py`, `verification.py` | DISABLE / ARCHIVE | No queued QMF recovery, attestation decision, or recovery-authorization state machine controls paper execution. |
| `memory_recovery/goal_progress.json`, proposed candidate manifests and Goal wait states | DISABLE / ARCHIVE | Not read by paper controller or status. No Stage-A waiting state. Historical 37/37 attestation and current packaged R4/config hashes suffice, as directed. |
| `scripts/final_eval/{campaign,common,dataset,lifecycle,reporting}.py`, protocol and tests | ARCHIVE / DISABLE old entrypoint | Old controller stopped. Independent paper runner owns new checkpoints only. Four-dataset order and result-before-cleanup policy are retained. |
| `scripts/result_sidecar/{guardian,watcher,numeric,optional_analysis,publish}.py`, tests | ARCHIVE / DISABLE services | No guardian resumes old work. No watcher writes paper checkpoints. `run_paper_benchmark.sh --status` is read-only. Numeric reports cannot start benchmark processes. |
| `scripts/run_four_dataset_final.sh`, `guard_four_dataset_campaign.sh`, `watch_four_dataset_results.py` | DISABLE running services / ARCHIVE | Scripts remain unchanged for historical reproducibility; their old services were stopped. The new service never calls them. |
| `scripts/full_eval/worker.py`, `postgres_full.cpp`, old full/recovery protocol files; `run_four_dataset_full.sh`, `run_geolife_memfix.sh` | ARCHIVE old workload / KEEP frozen method semantics | Isolated paper copies change only split cardinalities, progress flushing and reference scope. QMF build function and correctness SQL are regression-tested identical to the original. Old 23,400-entry queries remain untouched. |
| All `__pycache__` and legacy test outputs | ARCHIVE | Not execution authority and not imported by the paper runner. |
| Standalone `src/` and `config/` | KEEP unchanged | Full before/after SHA manifest compared against the pre-reset production freeze. Top-K 4, H3 and 16,384 configurations remain frozen. |

Reverted: none. There was no unverified production QMF memory modification to restore. The heavy query protocol is replaced in a separate directory, rather than rewriting historical experiment code.

## Backup and safe stop

Backups were created before orchestration edits:

- `/var/tmp/qmf_before_paper_protocol_reset_20260911/orchestration.tar.gz` — SHA256 `8a87dc579537138b1cbc65f2316a2b2272dce83e00fb5ac567e1bb0120e64d7e`.
- `/var/tmp/qmf_before_paper_protocol_reset_20260911/result_manifests_checkpoints.tar.gz` — SHA256 `8dd2b9f901a6de6135ee283c4b3243c531b251a02e7b8e3aa96377556ad383da`.

Guardian/watcher and controlling services were stopped first. Backend 688816 was executing a read-only correctness SELECT; PostgreSQL `pg_cancel_backend` canceled that statement at a transactional boundary. The harness then exited and closed its 33,137-byte partial CSV at 18:30:03 on 2026-09-11. This is an administrative protocol reset, not a correctness or physical resource failure. Previously completed build/reference checkpoints remain unchanged. PostgreSQL was then shut down normally. No raw data, normalized cache, frozen old queries, old metrics, or completed benchmark evidence was deleted.

The already validated PostgreSQL GeoLife table may be relocated from the stopped runtime into the new runtime to avoid repeating data loading. Its old load evidence and exact target paths are recorded in `00_environment/database_relocation.json`. No old index-build measurements, correctness measurements or timing checkpoints are reused for the new protocol. GiST is rebuilt once for the new measured build.

## Paper preregistration

Each full dataset has 1000 train, 1000 validation, 1000 correctness, 300 warmup, and 3000 performance entries. Performance has 1000 entries each at target 0.01%, 0.1%, and 1%; all five timing repetitions are used. Build repetitions are exactly one. The original generic bounds/PCG64/aspect-ratio/float32-midpoint procedure and seed 20260910 are retained, with new split cardinalities. All four query files are generated and SHA-frozen before any new method result exists.

No exact-reference-count prepass exists. Exact truth/candidate ID comparisons and count-kernel checks run only on the 1000 correctness queries. Performance result counts remain raw observations, without a separate reference scan. Zero-result queries are retained. All eight methods receive the same frozen point order and matching train/validation workload. Size comparability remains the original persistent-method set, with explicit rank denominators. Correctness-invalid or resource-blocked methods remain visible and are excluded from winner rankings.

QMF_MEMORY_ENGINEERING_PRODUCTION_CHANGE = NO

QMF_ALGORITHM_CHANGED = NO
