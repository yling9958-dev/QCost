# Current Paper Execution Path

- Repository: `/media/lingyaqi/Lenovo F510/QMF`
- Formal shell entry: `scripts/run_paper_benchmark.sh`
- Controller package: `scripts/paper_eval/`
- Formal results: `results/four_dataset_paper_protocol_20260911/`
- Formal runtime: `/var/tmp/qmf-paper-protocol-20260911/`
- Protocol source: `scripts/paper_eval/paper_protocol.py`
- QMF source: `QMF_PostGIS_100M_Repro_20260910/src/common/python/qmapli/`
- PostgreSQL extension and baseline source: `QMF_PostGIS_100M_Repro_20260910/src/`
- Persistent normalized cache: `data_cache/full/<dataset>/points_normalized.csv`

The only intended user-facing entry is `scripts/run_paper_benchmark.sh`. Python
modules under `scripts/paper_eval` are controller internals and tests, not
separate remembered commands. The converged CLI owns `--status`, `--resume`,
`--repair DATASET`, `--method METHOD`, and `--dry-run`. There is no automatic
post-repair campaign launcher; forward progress is an explicit checkpoint-safe
`--resume` action.

Formal phases remain:

```text
prepare -> verify dataset -> verify frozen queries -> build -> correctness
        -> warmup -> timing x5 -> finalize -> report
```

The 100 MiB reproduction, 8-core diagnostic, memory scaling prefixes, archived
campaigns, and recovery provenance are not formal result inputs.
