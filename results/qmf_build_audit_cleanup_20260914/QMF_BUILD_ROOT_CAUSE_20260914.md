# QMF Full-Build Root Cause

## Established facts

The historical full GeoLife attempt reached 21,579.6 MiB and was stopped by
the host reserve guard. Its cgroup recorded no `memory.max`, OOM, or OOM-kill
event. A later implementation-amended attempt ran for 11,230 sampled seconds
until an authorized SIGTERM and did not complete. Its process RSS peaked at
18,816,774,144 bytes (17.52 GiB) during the first 19 minutes, then trended down
to about 6.5-7 GiB as recursive node sizes decreased. It was active, had zero
experiment swap, and was not stopped by the 12-hour timeout.

The pre-20260913 implementation amplified memory through a full pandas frame,
canonical XY/ID arrays, root/node coordinate gathers, membership/permutation
arrays, H3 dense child subsets, feature temporaries, reordered query storage,
and redundant suffix arrays. The already-audited 20260913 ownership amendment
removed the whole-frame lifetime, chunked the largest density temporary,
released committed parent memberships, and omitted training-only suffix data.

## Primary remaining cause before this task's implementation change

At the root, `points[node.point_indices]` still materializes a second full
`N x 2` float64 coordinate array even though the root membership is the identity
permutation. H3 then evaluates dense child subsets and NumPy quantile/statistic
workspaces while canonical XY, IDs, root membership, and the root gather remain
live. The algorithm requires the same dense values and exact reductions, but it
does not require the identity root gather to own a second copy.

At root split commit, two local-position arrays and two global-index arrays are
also transiently materialized even though local positions already equal global
positions for the identity root. This is implementation ownership duplication.

## Measured peak stage

The added stage trace directly brackets the peak in every completed profile:

```text
before_h3_candidate_generation(root)
  -> enumerate actions, R4 features, dense H3 child subsets and index positions
  -> after_h3_candidate_generation(root)
```

The final 1M, 5M, 10M, 25M, and 50M peaks were respectively 560.43, 875.23,
1242.09, 2417.73, and 4312.18 MiB. Later recursive nodes and query-ready layout
did not exceed the root H3 high-water mark. Memory fell with node size and did
not accumulate with the 127 committed internal nodes. This rules out a late
serialization peak and a monotonic tree-membership leak for the measured
scales.

Two complete, non-algorithmic root copies were established:

- `points[root_indices]` duplicated the canonical full float64 XY array.
- `np.arange(N, int64)` represented an identity membership that H3 never
  needed and root split positions already encode.

The root XY gather and root identity membership were removed. At the measured
peak, the long-lived full XY count changed from two to one and the top-level
full-dataset int64 index count changed from two to one. H3 still owns temporary
left/right subsets and positions whose aggregate size depends on the active
recursion path; those are real implementation costs but are not additional
long-lived full canonical stores.

The five-point descriptive OLS fit predicts 14,354.94 MiB at 181M points,
14,508.17 MiB at 183M, and 16,192.75 MiB at 204,986,702. These are admission
estimates, not full-scale measurements or asymptotic claims.

## Python versus C++

The measured peak occurs in Python/NumPy H3 enumeration. The C++ static index
builder is not called on this path: its `build(vector<Point>)` entry rejects
construction, while C++ loads the already serialized compact artifact for
query execution. Page-cache bytes are recorded separately from process RSS/PSS
and are not counted as QMF Python heap.

This is an implementation problem, not evidence that H, Top-K, the QMF budget,
the oracle, or the cost function must change.
