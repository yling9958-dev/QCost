# CLEANUP COMPLETE

The only current paper result source is `results/four_dataset_paper_protocol_20260911/`. The benchmark and repair were inactive before cleanup and remain inactive. No benchmark was stopped, started, resumed or interrupted. The user read-only status watcher remains active.

## Current paper mainline

Repository: `/media/lingyaqi/Lenovo F510/QMF`

Results: `/media/lingyaqi/Lenovo F510/QMF/results/four_dataset_paper_protocol_20260911`

Runner: `scripts/run_paper_benchmark.sh`

Controller: `scripts/paper_eval/`

Four full datasets; eight methods; seven primary metrics. 1,000 training, 1,000 validation, 1,000 correctness, 300 warmup and 3,000 performance queries per dataset; five timing repetitions and one build repetition. Scientific protocol and algorithm implementations are unchanged.

## Preservation

| Check | Result |
|---|---|
| Active benchmark interrupted | NO; inactive before and after |
| Current results preserved | YES; 352 existing files checked by SHA256 |
| Raw datasets preserved | YES; existing SHA records unchanged; bytes/mtime unchanged |
| Normalized datasets preserved | YES; persistent cache untouched, bytes/mtime unchanged |
| Frozen queries preserved | YES; all four SHA/cardinality gates passed |
| Current repair runtime preserved | YES; no mutation under current runtime |
| QMF algorithm changed | NO; production source/config hashes unchanged |
| Active Goal-mode controller | NO |
| Experiment swap | 0 before and after |

## Changes and dependency exceptions

`run.py` now reads production and dataset manifests from the current result root. The completed one-time database/load migration from historical results was retired. Current binary links must already resolve; missing dependencies fail explicitly. `finish_repair.py` recognizes the new tested control-source receipt. Original experiment and repair source manifests were preserved. No benchmark phase, scientific metric, query, correctness receipt or existing checkpoint changed. See `cleanup_control_source_20260912.json` and the archived exact orchestration patch.

| Path | Classification | Reason |
|---|---|
| scripts/paper_eval | CURRENT_DEPENDENCY / KEEP | Current controller and repair |
| scripts/full_eval/worker.py; postgres_full.cpp | TEST_ONLY / KEEP | Unchanged frozen function/SQL comparisons |
| Remaining former scripts/full_eval modules | HISTORICAL_ONLY / ARCHIVE | No current import |
| scripts/final_eval; memory_recovery; result_sidecar | HISTORICAL_ONLY / ARCHIVE | Removed from active scripts; no current import |
| /var/tmp/qmf-geolife-full-memfix-20260911 | CURRENT_DEPENDENCY / KEEP | Current build, baseline, extension and source symlinks resolve here |
| /var/tmp/qmf-repro-input; /var/tmp/qmf-repro-native | KEEP | Conservative preservation of pilot input and reproduction binaries |
| .pytest_cache | KEEP | Small test cache; not exclusively a failed campaign artifact |

Historical result roots are compact archives under `archive/cleanup_20260912/historical_results/`. Historical entry points, guardians and Goal-mode helpers are under `archive/code_history_20260912/scripts/`. Older source/delivery provenance is under `archive/cleanup_20260912/root_history/`. All are HISTORICAL_DIAGNOSTIC_ONLY; none is an automatic paper result/ranking/resume input. The remaining guardian names in current code only guard against an already-active old service; they do not launch one.

## Recoverable quarantine and disk accounting

Files archived = 814

Files quarantined = 17134

Files permanently deleted = 0

Archived originals were withdrawn only after zstd integrity verification, tar byte comparison and a fresh active-path check. Each archive retains original paths, file metadata, SHA256 and before/after process evidence. Recovery instructions are in `archive/README.md`. No broad wildcard deletion or cache flush was used.

Disk before (the 25 compressed source artifacts) = 18.240761 GiB

Disk after (archives plus SHA/receipts) = 5.259521 GiB

Disk reclaimed for those artifacts = 12.981239 GiB

New audit/documentation allocation = 0.009521 GiB

Estimated net reclaimed including audit files = 12.971718 GiB

Same-filesystem moves to code/root history reclaim no disk and are excluded from this savings calculation. The net estimate excludes directory-allocation changes and the small final report written after accounting. The full requested `du`/`df` snapshots are `CLEANUP_DISK_BEFORE.txt` and `CLEANUP_DISK_AFTER.txt`; their naive totals are not directly comparable because root-level history moved into the snapshot scope.

## Units and validation

Recorded failure receipts/journals and reset only `qmf-four-full-20260910.service`, `qmf-paper-worker-709593-32.service` and `qmf-worker-688779.service`, after verifying failed state, MainPID=0 and empty cgroups. Active system slices, the unrelated system PostgreSQL and the user status watcher were not stopped.

59 regression tests passed, including current-only manifest reads, source-integrity rejection, unchanged scientific code/protocol and missing-dependency behavior. Both frozen fixture tests also passed after moving historical code. The current status command still reports GeoLife 8 attempted / 5 valid, scientifically incomplete. Cleanup did not rerun or relabel any method.

## Remaining top-level directories

- `.pytest_cache/`
- `QMF_PostGIS_100M_Repro_20260910/`
- `archive/`
- `data_cache/`
- `dataest/`
- `dist/`
- `results/`
- `scripts/`

QMF_ALGORITHM_CHANGED = NO
