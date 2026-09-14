# QMF Memory Implementation Optimization

## Scope

The work changes ownership, lifetime and observability only. H=3, Top-K=4,
the 16,384 configuration cap, R4 scorer, uniform-QMF search, budget, oracle,
cost, candidate ordering, root commit, leaf policy, precision and persistence
semantics are unchanged.

## Implemented ownership changes

1. The normalized CSV is parsed in one-million-row chunks into one
   preallocated float64 `N x 2` point array and one int64 ID array. The full
   pandas DataFrame and its conversion intermediates no longer coexist with
   the build.
2. The root MBR and root evaluation use the canonical point array as a view.
   The identity membership no longer triggers `points[root_indices]`, removing
   one full float64 XY copy.
3. At the root split, local positions already are global positions. They are
   transferred directly to the two children rather than gathered through the
   identity root membership, removing one transient full int64 index copy.
4. The root's identity membership is now implicit during build. The old
   `np.arange(N, int64)` array is never present during H3; a deliberately
   unsplit single-leaf root materializes it only at layout time.
5. A committed internal node releases its obsolete membership immediately.
   Leaves alone retain membership until query-ready layout.
6. Static export releases canonical build storage as soon as reordered
   query-ready point/ID storage exists. It omits suffix value/order arrays that
   compact format v2 never serializes and releases each leaf membership after
   its suffix is built.
7. The 4x4 density feature is accumulated in bounded chunks instead of
   retaining a normalized full-node XY temporary.
8. Explicit deletes shorten H3 dense-subset lifetime after a branch summary is
   complete. No garbage collection is used as the ownership mechanism.
9. Serialization already writes fixed 65,536-element chunks and remains
   unchanged.

## Directly measured effect

With identical prefix data and the frozen full-GeoLife training workload:

| N | Original peak | Root-view intermediate | Final peak | Final reduction |
|---:|---:|---:|---:|---:|
| 1M | 660.73 MiB | 568.25 MiB | 560.43 MiB | 15.2% |
| 5M | 1344.86 MiB | 912.80 MiB | 875.23 MiB | 34.9% |
| 10M | 2214.55 MiB | 1318.66 MiB | 1242.09 MiB | 43.9% |
| 25M | 4816.49 MiB | 2607.97 MiB | 2417.73 MiB | 49.8% |
| 50M | not completed | 4693.77 MiB | 4312.18 MiB | N/A |

For 1M through 25M, persisted index bytes, canonicalized tree decisions and
leaf membership hashes are identical to the original baseline. The 50M output
is identical to the root-view intermediate because the original 50M baseline
did not complete. The frozen 100 MiB reproduction independently matches its
raw tree, index, and leaf-assignment SHA values exactly. The observed linear
reductions therefore isolate ownership rather than a scientific change.

## Remaining ownership

H3 still materializes dense left/right subsets recursively. Replacing them with
indirection would alter reduction order and is high risk, so it was not done in
this audit. Query-ready layout necessarily owns a reordered float64 point array,
int64 IDs and two stable int64 suffix permutations until serialization. Those
later arrays do not determine the measured H3 peak in current prefix profiles.

The 181M prediction is 14,354.94 MiB. It clears the predeclared 18 GiB admission
target, but only a future formal full run can report the actual GeoLife peak.
