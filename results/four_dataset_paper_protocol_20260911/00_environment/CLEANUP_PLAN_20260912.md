# Cleanup plan — 2026-09-12

Current benchmark and repair are inactive at inspection; the read-only status watcher remains protected. No benchmark service is stopped, started, or resumed by cleanup.

Archives are HISTORICAL_DIAGNOSTIC_ONLY. No scientific artifacts are rewritten. Quarantined runtime trees are compressed, compared against their sources, then withdrawn only after a fresh active-reference check. Removal of a verified archived original is recoverable, not permanent evidence deletion.

## KEEP

| Path | Allocated bytes | Reason | Active reference | Current paper dependency |
|---|---:|---|---|---|
| /media/lingyaqi/Lenovo F510/QMF/dataest | 18086100992 | Four full raw datasets | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/data_cache/full | 17893425152 | Persistent normalized data | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/results/four_dataset_paper_protocol_20260911 | 111673344 | Only authoritative current paper results; all existing bytes protected | NO | YES |
| /var/tmp/qmf-paper-protocol-20260911 | 64492474368 | Current clusters, checkpoints, binaries, scratch and repair runtime retained even while inactive | NO | YES |
| /var/tmp/qmf-geolife-full-memfix-20260911 | 2240684032 | CURRENT_DEPENDENCY: five current binary/source symlink targets; preserve entire tree | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/scripts/paper_eval | 3670016 | CURRENT_DEPENDENCY: current controller; only historical manifest references may change while no controller is active | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/scripts/run_paper_benchmark.sh | 262144 | KEEP_ACTIVE: read-only user watch invokes this runner | YES / protected | YES |
| /media/lingyaqi/Lenovo F510/QMF/scripts/full_eval/worker.py | 262144 | TEST_ONLY: frozen QMF function comparison | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/scripts/full_eval/postgres_full.cpp | 262144 | TEST_ONLY: frozen correctness SQL comparison | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/QMF_PostGIS_100M_Repro_20260910 | 157286400 | Authoritative production package and all baseline source | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/dist | 27525120 | Standalone reproduction distribution and SHA records | NO | YES |
| /var/tmp/qmf-repro-input | 104865792 | Frozen 100MiB reproduction input; conservative keep | NO | NO |
| /var/tmp/qmf-repro-native | 50167808 | Conservative keep of reproduction binaries | NO | NO |

## ARCHIVE

| Path | Allocated bytes | Reason | Active reference | Current paper dependency |
|---|---:|---|---|---|
| /media/lingyaqi/Lenovo F510/QMF/results/four_dataset_final_20260911 | 185335808 | HISTORICAL_DIAGNOSTIC_ONLY; preserve complete evidence in compact archive | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/results/four_dataset_full_20260910 | 44302336 | HISTORICAL_DIAGNOSTIC_ONLY; preserve complete evidence in compact archive | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/results/geolife_full_memfix_20260911 | 53215232 | HISTORICAL_DIAGNOSTIC_ONLY; preserve complete evidence in compact archive | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/QMF_PostGIS_100M_Repro_20260909 | 50069504 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/QMF_PostGIS_100M_Repro_20260909.zip | 2097152 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/QMF_PostGIS_100M_Repro_20260909.zip.sha256 | 262144 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/QMF_PostGIS_100M_Repro_20260909_DELIVERY_REPORT.md | 262144 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/GEOLIFE_FULL_4P2G_RECOVERY_EVALUATION_20260911.md | 262144 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/REPRODUCTION_20260910.md | 262144 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/STANDALONE_AUDIT_BEFORE.md | 262144 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/STANDALONE_REPRODUCTION_REPORT_20260910.md | 262144 | Historical source/delivery/report provenance; preserve bytes and SHA records | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/final_eval | 4456448 | HISTORICAL_ONLY; no current import | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/memory_recovery | 8388608 | HISTORICAL_ONLY; no current import | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/result_sidecar | 4194304 | HISTORICAL_ONLY; no current import | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/full_eval | 4980736 | Archive old controller; retain only two TEST_ONLY source fixtures in place | NO | YES |
| /media/lingyaqi/Lenovo F510/QMF/scripts/run_four_dataset_final.sh | 262144 | HISTORICAL_ONLY entry point; remove from active scripts directory | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/run_four_dataset_full.sh | 262144 | HISTORICAL_ONLY entry point; remove from active scripts directory | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/run_geolife_memfix.sh | 262144 | HISTORICAL_ONLY entry point; remove from active scripts directory | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/guard_four_dataset_campaign.sh | 262144 | HISTORICAL_ONLY entry point; remove from active scripts directory | NO | NO |
| /media/lingyaqi/Lenovo F510/QMF/scripts/watch_four_dataset_results.py | 262144 | HISTORICAL_ONLY entry point; remove from active scripts directory | NO | NO |

## QUARANTINE

| Path | Allocated bytes | Reason | Active reference | Current paper dependency |
|---|---:|---|---|---|
| /var/tmp/qmf-final-zip-runtime-20260910 | 2104508416 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-final-zip-runtime-prepackage-script-fix | 2103066624 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-final-zip-test | 111738880 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-final-zip-test-prepackage-script-fix | 111738880 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-four-dataset-final-20260911 | 8192 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-four-dataset-full-20260910 | 1186455552 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-memory-equivalence-20260911 | 28672 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-public-zip-test | 6881280 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-public-zip-test-prepackage-script-fix | 6881280 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-recovery-clean-test-20260910-U1ofRK | 104865792 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-recovery-validation.LZX8yw | 104861696 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-repro-20260910 | 5004324864 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-repro-accepted-runtime | 2123427840 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-repro-clean-runtime | 1990799360 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-repro-final-runtime | 2103631872 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-standalone-generated-cache-20260910 | 57344 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-standalone-isolated-test | 111730688 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-standalone-runtime-20260910 | 2103136256 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf-standalone-unit-20260910 | 20480 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf_before_paper_protocol_reset_20260911 | 409600 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf_repro_clean_test | 24436736 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |
| /var/tmp/qmf_analyze_failure_20260911.log | 4096 | Inactive superseded runtime/test/backup; recoverable archive required | NO | NO |

## SAFE_TO_DELETE

| Path | Allocated bytes | Reason | Active reference | Current paper dependency |
|---|---:|---|---|---|
| None | 0 | No permanent deletion approved; archive/quarantine first | NO | NO |
