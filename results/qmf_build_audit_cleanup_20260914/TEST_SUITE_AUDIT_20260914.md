# Paper-Eval Test Suite Audit

Initial collection: 111 tests. Final paper-eval collection: 116 tests.

| Category | Existing coverage | Decision |
|---|---|---|
| Unit | status classification, resource helpers, query generation | KEEP |
| Protocol | query counts, build timeout, memory policy, source freeze | KEEP |
| Equivalence | point I/O, tree/splits, static index, leaf membership | KEEP and extend root-view gate |
| Regression | empty results, PASS protection, retry generations | KEEP |
| Integration | real controller dispatch to mocked worker boundary | KEEP |
| Historical repair | old handoff and evidence supersession | KEEP until unified CLI replacement is proven |

Final verification:

- `scripts/paper_eval`: 116 passed.
- frozen standalone package: 20 passed, 4 skipped because no complete quick
  PostgreSQL runtime was started.
- frozen 100 MiB build: exact tree/index/leaf digests, 281.06 s, 788.82 MiB,
  swap 0.

Scientific gates were retained and expanded. Bytecode writing is disabled
during tests because generated `__pycache__` files inside frozen source would
invalidate the source-manifest gate.
