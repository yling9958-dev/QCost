# Cost-model weight audit

Read-only source audit plus arithmetic over already saved H3/K4 cost arrays.
No experiments, model fitting, query execution, or index construction are run.
Original code, coefficients, results, manuscript, and figures are preserved.

```bash
cd '/media/lingyaqi/Lenovo F510/QMF'
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  '/media/lingyaqi/Lenovo F510/QMF-Motivation-Study/.venv/bin/python' -B \
  cost_model_weight_audit_20261021/scripts/audit_weights.py
```

Derived audit outputs are regenerated only in this new directory.

- `reports/COST_MODEL_WEIGHT_AUDIT.md`: source evidence, units, bounds, results and proposed next steps.
- `reports/COST_MODEL_REVISION_EN_ZH.tex`: standalone wording suggestion.
- `data/node_weight_ablation.csv`: all 43 nodes; no filtering by outcome.
- `data/root_weight_ablation.csv`: per-root original and scan-only optima.
- `data/audit_summary.json`: exact values, software versions and script hash.
- `data/source_sha256_before.json`, `data/source_sha256_after.json`: 151 protected input hashes.
- `reports/run.log`: actual computation output.

The original candidate order, cost tables and root mappings are read from
`QMF-Motivation-Study/results/nodes`. Calibration metadata and the original
6,144 observations are checked independently. All 267,446 stored costs match
the frozen two-term expression exactly. Removing the leaf term preserves all
43 optimum sets, while equal-scan tie ordering changes in 21 nodes.
