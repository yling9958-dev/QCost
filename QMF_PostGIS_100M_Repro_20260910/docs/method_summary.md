# Frozen Method

Uniform Quantum Minimum Finding over H3 joint subtrees after workload-aware
Stage-A Top-K=4 pruning, up to 16384 configurations. Receding-horizon commit of
the selected root action only. Original costs, seeds and stopping rules remain.

The quantum search is an offline abstract-oracle simulation. Online PostgreSQL
calls only the static C++ index, never Python/QMF/VQC. This is a unified PostgreSQL
execution interface, not a native PostgreSQL Index AM.

Supported reference claims: best Mean/P95/P99/QPS among eight runnable methods;
smallest query-ready persistent representation among five comparable methods;
unchanged logical tree during the preceding system optimization.

Not supported: QPU advantage, end-to-end quantum speedup, empirical asymptotic
quadratic speedup, smallest index among all eight, fastest build or lowest memory.
