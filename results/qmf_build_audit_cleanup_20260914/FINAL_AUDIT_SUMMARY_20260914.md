# Final Audit Summary

- Active paper run: NO.
- Root cause found: YES. The measured peak is inside root H3 candidate
  generation, where historical whole-file/input ownership, a full root XY
  gather, root identity membership, H3 dense subsets, and NumPy feature/sort
  temporaries overlapped.
- Full XY stores at the peak: 2 before, 1 after.
- Full-index-equivalent arrays at root split commit: 3 before, 1 after. During
  root H3, the long-lived top-level index equivalents changed from 2 to 1.
- Historical full GeoLife peak: 21,579.6 MiB.
- Final 50M engineering profile peak: 4,312.18 MiB.
- Descriptive five-point prediction at 181M: 14,354.94 MiB.
- Peak bracket in every final profile: after root
  `before_h3_candidate_generation` and before root
  `after_h3_candidate_generation`.
- Frozen 100 MiB reproduction: exact tree, static index, and leaf-assignment
  SHA matches.
- Existing PASS evidence: 111 files, byte-for-byte unchanged.
- Tests: 116 paper-eval passed; 20 standalone passed and 4 environment-bound
  tests skipped. The 18 focused QMF tests are included in the 116 paper tests.
- QMF core algorithm, H=3, Top-K=4, budget, cost, CPU protocol, datasets,
  queries, and 22/24 GiB no-swap policy: unchanged.

The 181M estimate clears the predeclared 18 GiB engineering admission target,
so a controlled formal QMF-only GeoLife retry is supported. It remains a
prediction, not a result. Only that future full run may establish full-scale
build time, peak memory, index size, correctness, and query metrics.

Recommended command, intentionally not executed by this audit:

```bash
bash scripts/run_paper_benchmark.sh --repair GeoLife --method QMF
```
