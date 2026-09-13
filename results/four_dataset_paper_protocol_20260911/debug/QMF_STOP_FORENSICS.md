# QMF stop forensics

Classification: HOST_SAFETY_STOP. QMF_24G_EXHAUSTION_PROVEN = NO. QMF_HOST_PRESSURE_OBSERVED = YES.

The stop was issued at 2026-09-11 19:21:31–32 +0800 during build. The receipt explicitly records the fixed MemAvailable < 3.5 GiB condition. Observed QMF peak RSS was 11,340.26171875 MiB; parent peak was 13996240896 bytes (13.035015 GiB), with final sampled current 13134249984 bytes. memory.high = 23622320128; memory.max = 25769803776; high/max/oom/oom_kill events were all zero. Experiment swap was zero.

Exact triggering MemAvailable, MemTotal, instantaneous worker RSS, PostgreSQL RSS/PSS, and outside-process ownership were not persisted. The last periodic CSV sample had MemAvailable 5,209,817,088 bytes, before the later trigger; it is not the stop-time value. The exact trigger value is therefore N/A, with the strict upper bound 3,758,096,384 bytes supported by the code and receipt. Current host measurements are reported separately and do not explain historical ownership by themselves.

No 11.3 GiB production hard cap was found. The source and kernel evidence both show the 24 GiB hard cap. Future monitor failures record the complete triggering sample and per-process snapshot before termination.
