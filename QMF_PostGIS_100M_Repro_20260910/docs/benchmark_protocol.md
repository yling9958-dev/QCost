# Frozen Seven-Metric Protocol

Methods: QMF, PostGIS GiST, LISA, Flood, Tsunami, LMSFC, BMTree, Boost packed R*-tree.
Shared data and raw/normalized query rectangles; no query generation in this package.
23,400 frozen rows: 1200 train, 1200 validation, 5000 correctness, 1000 warmup,
15000 performance (5000 each S1=0.0001, S2=0.001, S3=0.01).

Three complete build repetitions, five complete timing repetitions. Prepared
count calls measure performance; complete sorted ID sets establish correctness.
One client/worker, client CPU affinity pinned as in the frozen harness, same
server scheduling policy for all methods. No per-query build/load/model inference.

Seven metrics: mean full BuildTime_s; query-ready serialized IndexSize_MiB;
pooled MeanLatency_ms, P95Latency_ms, P99Latency_ms; QPS=1e9/mean latency_ns;
PeakMemory_MiB=max(build process peak, client+backend query high-water peak).
Shared/inherited memory accounting limitations are unchanged.

Use all repetitions, not the fastest. Correctness requires 5000/5000 with zero
missing/extra for each method. SQL adapter and C++ exact/count checks remain.
No new ranking definition or eighth primary metric is introduced.
