# Current QMF paper benchmark

The only current paper result source is
[`results/four_dataset_paper_protocol_20260911/`](results/four_dataset_paper_protocol_20260911/).

The runner is [`scripts/run_paper_benchmark.sh`](scripts/run_paper_benchmark.sh);
the controller, repair tooling and read-only status output are in
[`scripts/paper_eval/`](scripts/paper_eval/).

```bash
bash scripts/run_paper_benchmark.sh --status
```

The frozen protocol uses four full datasets, in order: GeoLife, Gowalla, NYC Taxi,
and Skewed 2D. It evaluates QMF-Index, PostGIS GiST, LISA, Flood, Tsunami, LMSFC,
BMTree and Boost R*-tree with seven primary metrics: build time, index size,
mean latency, P95, P99, QPS and peak memory. Correctness is a validity gate.

Per dataset: 1,000 training, 1,000 validation, 1,000 correctness, 300 warmup and
3,000 performance queries; five timing repetitions and one build repetition.
The shared PostgreSQL/worker budget remains 22 GiB MemoryHigh, 24 GiB MemoryMax,
zero experiment swap, and a 3.5 GiB host emergency reserve.

Raw datasets remain in `dataest/`; persistent normalized data remains in
`data_cache/full/`. Production QMF and baseline sources remain in
`QMF_PostGIS_100M_Repro_20260910/`. Cleanup does not change their algorithms.

The current runtime `/var/tmp/qmf-paper-protocol-20260911/` must be preserved,
including while GeoLife repair is held. Its common binary/source links currently
resolve into `/var/tmp/qmf-geolife-full-memfix-20260911/common/`; that older-named
directory is a **current dependency**, not disposable scratch.

Historical experiments are archived under `archive/` and are
**HISTORICAL_DIAGNOSTIC_ONLY**. They are not current paper result, ranking or
resume inputs. No Goal-mode controller or guardian is needed by the mainline.
The two files left in `scripts/full_eval/` are unchanged test fixtures only.

The cleanup report is
[`CLEANUP_REPORT_20260912.md`](results/four_dataset_paper_protocol_20260911/00_environment/CLEANUP_REPORT_20260912.md).
Do not interpret an attempted dataset as scientifically complete; `--status`
reports attempted and valid method counts separately.
