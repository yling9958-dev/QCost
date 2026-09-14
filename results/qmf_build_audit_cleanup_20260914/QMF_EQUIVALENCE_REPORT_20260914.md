# QMF Implementation Equivalence Report

## Frozen 100 MiB reproduction

The current implementation rebuilt the real 4,197,223-point standalone input
with its frozen training query file. This was a diagnostic build, not a paper
measurement.

| Gate | Frozen value | Current value | Result |
|---|---|---|---|
| raw tree manifest SHA256 | `a7c540d4d5f8e1b34e7508d2be921741203cc13667403fa8b7df587e03696230` | same | PASS |
| static index SHA256 | `12bbd47ef650888b67e042002d794e75de64ec5d91c0c2476eded5d85e577282` | same | PASS |
| leaf membership SHA256 | `f114efb06770bc520743c3770fcb2ac95c710f58b6cea02748454b6eff7348fb` | same | PASS |
| build elapsed | not a bitwise gate | 281.06 s | OBSERVED |
| peak RSS | not a bitwise gate | 788.82 MiB | OBSERVED |
| swap | 0 required | 0 | PASS |

Because the complete persisted static index is byte-identical and the native
query source is byte-identical, its frozen query behavior is identical. The
native exactness unit test additionally compares returned IDs with brute-force
IDs. The historical 40,000/40,000 result is not claimed as rerun here.

## Prefix equivalence and scaling

For 1M, 5M, 10M, and 25M deterministic prefixes, all three outputs match the
original pre-optimization baseline: canonical tree digest, complete index SHA,
and leaf membership digest. The original 50M baseline did not finish; the final
50M result instead matches the completed root-view intermediate for all three
outputs.

## Algorithm and protocol gates

`search.py`, cost oracle, cached oracle, quantum semantics, R4 prior, candidate
actions, frozen config and R4 checkpoint are byte-identical to the pre-change
manifest. The H3 enumerator differs only by object-lifetime `del` statements,
verified by its AST gate. Tests confirm H=3, Top-K=4, budget factor, exact query
IDs, online quantum disabled, and static persistence behavior.

No dataset, query, repetitions, correctness rule, CPU policy, memory policy,
QMF scientific parameter, or existing formal PASS artifact changed.

## Acceptance

- 100M equivalence: PASS (the project's 100 MiB reproduction).
- Tree digest unchanged: YES.
- Index digest unchanged: YES.
- Leaf assignment unchanged: YES.
- Query results unchanged: YES.
- Full 181M result measured: NO.
