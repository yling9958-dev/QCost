# QMF Full-Build Call Graph

```text
scripts/run_paper_benchmark.sh
  -> scripts/paper_eval/run.py
     -> foreground / resume / repair dispatch
     -> scripts/paper_eval/orchestrate.py::run_method
        -> build_one(dataset, qmap_uniform_qmf, repetition=0)
        -> monitor(worker("qmf", ...), shared_build_timeout=43200)
           -> systemd worker under qmf-paper.slice
              -> scripts/paper_eval/worker.py::qmf
                 -> qmapli.wg_qmf.build_static_qw_index.main
                    -> point_io.read_points
                       -> pandas CSV parser in bounded chunks
                       -> canonical float64 XY + int64 ID arrays
                    -> load frozen 1000-query training array
                    -> wg_qmf.index.build_qw_static_index
                       -> FrozenR4Prior
                       -> root HybridPrefixNode with implicit identity membership
                       -> priority-ordered recursive node loop
                          -> current-node coordinate gather/view
                          -> intersect training queries
                          -> _select_joint_root_action
                             -> configuration.enumerate_joint_configurations
                                -> enumerate_actions (fixed quantiles)
                                -> R4 score_actions / node_action_features
                                -> H=3 recursive split summaries
                                -> Top-K=4 plan combination, capped at 16384
                             -> cost_oracle.evaluate_subtree_costs
                             -> search.uniform_qmf (fixed budget/seed)
                          -> commit selected root split only
                             -> root positions become child global indices directly
                          -> enqueue children
                       -> PrefixHybridIndex.build(static_export=True)
                          -> DFS storage ordering
                          -> reordered query-ready point and ID arrays
                          -> stable dual-axis suffix ordering per leaf
                       -> compact static index serialization
                    -> metadata JSON
                 -> tree decision manifest (O(nodes), not O(points))
        -> correctness: exact 1000 frozen queries
        -> warmup: 300 frozen queries
        -> performance: 3000 frozen queries x 5 repetitions
        -> final method receipt and report
```

The paper worker does not load the full points independently before calling the
QMF builder. The QMF build path is Python/NumPy/Torch until compact static-index
serialization. `StaticQMapIndex::build(const std::vector<Point>&)` deliberately
throws; C++ only enters through `StaticQMapIndex::load` after the Python artifact
exists. It loads the compact float32 X/Y, uint32 IDs, nodes and suffix positions
for PostgreSQL query execution. It is therefore not a second full point builder
during the measured Python build and cannot explain the pre-serialization peak.
