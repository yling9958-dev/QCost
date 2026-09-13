# GeoLife repair decisions — 2026-09-12

GeoLife has eight attempted methods and four scientifically valid methods. LISA, Tsunami, LMSFC and BMTree pass complete 1000-query correctness and all five 3000-query timing repetitions. Their measurements, raw compressed timings and phase checkpoints are protected by a SHA manifest and are not rerun.

| Method | Corrected terminal cause | Failed phase | Evidence |
|---|---|---|---|
| QMF | HOST_SAFETY_STOP | build | Fixed MemAvailable < 3.5 GiB guard; max/oom/oom_kill = 0; shared peak 13,996,240,896 bytes. Exact triggering MemAvailable was not persisted. |
| PostGIS GiST | OOM_KILLED | timing | systemd-oomd killed the PostgreSQL service at 2026-09-11 21:40:18. Desktop user@1000 pressure was 62.31% > 50% for >20 seconds. Partial first-repetition latency file proves warmup had finished. |
| Flood | HOST_SAFETY_STOP | correctness | MemAvailable reserve breach; max/oom/oom_kill = 0. MemoryHigh events indicate throttling, not hard-limit exhaustion. |
| Boost R*-tree | OOM_KILLED | build | systemd-oomd killed worker qmf-paper-worker-709593-23 at 2026-09-12 04:44:05. Desktop user@1000 pressure was 62.44% > 50% for >20 seconds. Kernel max/oom/oom_kill remained zero. |

`systemd-oomd` is a userspace pressure policy, distinct from the kernel cgroup hard limit. The new experiment workers and dedicated PostgreSQL run as the same unprivileged user inside a system-owned `qmf-paper.slice`, outside the desktop `user@1000.service` pressure ancestor. This is scoped to benchmark infrastructure. The user/session OOM policy, browsers, desktop and system PostgreSQL are unchanged. The slice still enforces MemoryHigh 22 GiB, MemoryMax 24 GiB, MemorySwapMax 0; the 100 ms monitor retains the 3.5 GiB MemAvailable reserve. ManagedOOMPreference=omit is applied to benchmark units; the system-owned cgroups satisfy the installed systemd 249 ownership requirement. No increase in method memory, swap, concurrency or query workers occurs.

Reference: [systemd 249 resource-control specification](https://raw.githubusercontent.com/systemd/systemd/v249/man/systemd.resource-control.xml), ManagedOOMPreference and ancestor pressure behavior. The installed manual documents the root-ownership requirement, so merely setting omit on user-owned units was not treated as an effective repair.

At the current pre-retry audit, approximately 24.9 GiB MemAvailable and 4.7 GiB observable outside-experiment PSS were measured. A clean QMF retry under the unchanged algorithm is reasonable, with resource protection active; success is not guaranteed. Historical ownership cannot be inferred from this current snapshot.

## Lifecycle and recovery

The forward campaign was already stopped at inspection. Gowalla's PostgreSQL cluster is shut down cleanly and remains on disk. Its complete repetitions 1–3 and partial fourth repetition are preserved. No NYC Taxi worker is started. `GEOLIFE_REPAIR_HOLD.json` prevents the normal start/resume entrypoint from advancing while repair is active.

The old GeoLife cleanup ran DROP TABLE at 2026-09-12 04:44:06, deleting its GiST and full SQL table. No reusable full-GeoLife SQL/index backup was found. The normalized artifact and original 1389.09-second build/1000-exact correctness checkpoints survive. A separate GeoLife repair PostgreSQL cluster must restore the SQL table and identical GiST construction; restoration costs and representation size are recorded separately. This is necessary because runtime artifacts were deleted, not because the terminal label changed. The original successful measured build is preserved and excluded from re-execution as a measurement. QMF is retried next, then Flood, then Boost. No valid baseline is repeated.

Status taxonomy: PASS, HOST_SAFETY_STOP, CGROUP_MEMORY_MAX, OOM_KILLED, SWAP_INVALID, BUILD_FAILED, CORRECTNESS_FAILED, WARMUP_FAILED, TIMING_FAILED, FINALIZATION_FAILED, REPORTING_FAILED. Each result also records failed_phase and reason. Timeouts retain their explicit reason and receive their actual phase's failure status. No unsupported hard-limit claim is made from a process's RSS or MemoryHigh events.

Scientific completion now requires eight valid methods with complete retained correctness/timing evidence and applicable seven metrics. Attempted datasets and scientifically complete datasets are separate. Incomplete datasets cannot drop their PostgreSQL table or advance to the next dataset. Failed method index files survive cleanup. Reporting remains downstream and cannot launch the campaign.

The repair fixes a descriptive environment string that incorrectly said 1000 warmup / 11000 performance; the executable harness, frozen queries and measured PASS rows used 300 warmup / 3000 performance. No query file, binary query kernel, QMF builder, R4 model, or protocol parameter is changed.

## Controller validation and handoff

The updated controller has 53 passing regression tests, recorded in `repair_tests.xml`. Tests include the distinct statuses, old versus new cgroup events, stale timing files that must not masquerade as current warmup completion, failed-phase preservation, incomplete-dataset retention, preserving the attempted count and successful PostGIS phases during retry, retaining repaired valid-method counts across resume, reattaching to an existing load without launching another worker, refusing forward handoff after an incomplete or interrupted repair, and reusing a validated restored GiST whose physical layout differs. `repair_source_verification.json` records the before/after source scope and unchanged production/query evidence. A method without a final receipt is nonterminal `INCOMPLETE` when build evidence exists; this does not claim it is actively running while its dataset is paused.

Normalized GeoLife verification passed before the SQL restoration began. While final controller edge-case checks were being installed, COPY had already started in worker `qmf-paper-worker-2850541-6.service` at 10:43:14. The controller was stopped at about 10:43:30; that independently managed COPY worker and PostgreSQL continued. At 10:44:49 the updated controller reattached to the same worker and resumed host-reserve monitoring. No COPY, index build, correctness query, or timing repetition was duplicated. During the brief monitor handoff, the fixed kernel cgroup limits remained active, no new max/oom/oom_kill event occurred, and observed available RAM was approximately 24.5 GiB. This is restoration setup only, not a measured method phase. The original monitor samples and controller status are preserved in `load_resources_before_handoff.csv` and `load_controller_handoff.json`.

The desktop and system PostgreSQL remain untouched. Normal forward progression stays held until GeoLife has eight scientifically valid methods. The durable repair runs PostGIS timing, QMF, Flood, and Boost in that order and publishes each result independently of the Codex connection.

The old, empty user-manager `qmf-paper.slice` and `qmf.slice` were stopped after verifying all descendant `cgroup.procs` files were empty. No normalized data, PostgreSQL cluster, result artifact or Linux global page cache was deleted. A later privileged process audit is saved separately in `HOST_MEMORY_CONSUMERS_PRIVILEGED.json`; it reports approximately 5.9 GiB total outside-experiment PSS and 24.5 GiB MemAvailable at that observation, including system processes whose PSS was inaccessible in the first audit. Neither current snapshot reconstructs historical QMF stop-time ownership.

Status: `bash scripts/run_paper_benchmark.sh --status`. The repair service is `qmf-paper-geolife-repair-20260912.service`. If it exits on an infrastructure issue, inspect `repair_interruption.json` before resuming with `python3 -B scripts/paper_eval/repair_geolife.py`; valid phases are retained and finished resource-failed attempts are not blindly repeated. The normal campaign start/resume entrypoint remains held during this repair.

After the repair service exits, one `ExecStopPost` invocation of `finish_repair.py` may hand execution back to the paper campaign. It requires a successful controller exit, eight valid methods, valid persisted GeoLife files, the tested control-source manifest, unchanged production/queries/protected evidence, no active experiment descendants, and zero experiment swap. It preserves the restored GeoLife SQL cluster on disk, records active-resource cleanup, archives the old controller-source freeze before accepting the audited infrastructure changes, and resumes Gowalla at its unfinished phases. Any failed gate leaves forward advancement held. This is a single completion hook, with no restart or polling loop. Installing the hook did not restart the running repair controller or GiST worker.

## GiST restoration acceptance

The full 181,000,000-row COPY and subsequent exact count succeeded. The GiST restoration also succeeded, in 1423.84 seconds, with 10,240,180,224 bytes. The original successful build was 1389.09 seconds with 10,347,552,768 bytes. Both measurements remain available in their original receipts and `runtime_restored.json`.

An initially over-strict equality check paused the controller before any timing on the restored index. Review of [PostgreSQL 14.24 gistutil.c](https://raw.githubusercontent.com/postgres/postgres/REL_14_24/src/backend/access/gist/gistutil.c) shows that `gistchoose` uses random decisions for equal insertion penalties. Physical layout, and therefore size, need not repeat byte-for-byte for identical input. The old layout and its PRNG state are unavailable, so this explains why exact size identity is not a valid acceptance requirement; it does not reconstruct the specific sequence of historical random choices.

The acceptance gate instead verifies the frozen input and normalized artifact, the completed full row count, identity bounds 0–180999999, the expected GiST definition, `indisvalid`/`indisready`, and the observed size against the new restoration receipt. No seed, PostgreSQL build option, query, or algorithm is changed. The original exact correctness receipt is reused for the identical frozen dataset, IDs, PostgreSQL/PostGIS implementation and query semantics; no claim is made that those 1000 queries were newly executed on the restored layout.

Primary Build Time retains the original preselected successful measurement, as requested before restoration performance was observed. Primary Index Size records the actual current query-ready relation. Timing will describe that restored relation. The report explicitly distinguishes these measurement instances, and preserves the restoration cost and original size as diagnostics. No second restoration build is scheduled. A transient-unit resume issue was also fixed: an existing failed unit is started directly, avoiding garbage collection caused by resetting it before start.

QMF_ALGORITHM_CHANGED = NO

DATASET_SIZE_CHANGED = NO

QUERY_PROTOCOL_CHANGED = NO

OLD_11_3G_PRODUCTION_LIMIT_FOUND = NO

HOST_SAFETY_STOP_DISTINGUISHED_FROM_CGROUP_LIMIT = YES

MISSING_RESULTS_FABRICATED = NO
