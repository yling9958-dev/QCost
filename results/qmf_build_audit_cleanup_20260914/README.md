# QMF Full-Build Audit and Paper-Runner Convergence

This directory is engineering and audit evidence. It is not a paper-result
root and none of its diagnostic measurements enter the formal 8-method table.

The audit started from commit `4cb969689f3e175d338256542ba975cfc3995a4a` on
branch `audit/qmf-build-rootcause-cleanup-20260914`, with the pre-existing dirty
worktree preserved. No paper worker, repair controller, dedicated PostgreSQL
55445 server, Flood build, or R-tree build was active when modification began.
The unrelated system PostgreSQL 14 cluster was left untouched.

Phase A established the call graph, historical memory curve, object ledger,
formal execution path, protected-result manifest, and refactoring boundary.
Subsequent files in this directory distinguish measured evidence from modeled
or inferred values.

Final engineering result: the peak is directly measured inside root H3
candidate generation. Chunked input/lifetime work plus removal of the full root
XY gather and root identity-index array reduced 25M peak RSS from 4816.49 to
2417.73 MiB. The final five-point model predicts 14,354.94 MiB at 181M. The
frozen 100 MiB tree, index, and leaf-assignment digests are exact matches.

Scientific invariants:

- QMF H=3, Top-K=4, search budget, oracle, cost, candidate order, split rules,
  seed, tie breaking, leaf policy, and online query kernel remain frozen.
- The paper datasets, query workload, repetitions, correctness gate, CPU
  protocol, and 22/24 GiB no-swap memory policy remain frozen.
- Existing PASS artifacts for PostGIS GiST, LISA, Tsunami, LMSFC, and BMTree
  are protected by a 111-file byte/hash manifest.
- Full GeoLife is not launched by this audit.

The formal runner is still `scripts/run_paper_benchmark.sh`; all profile data
under this audit root is engineering evidence only.

See `FINAL_AUDIT_SUMMARY_20260914.md` for the bounded acceptance decision and
the single recommended command, which this audit did not execute.
