# Hybrid-QMF five-variant ablation — completed

12,000 formal runs (40 nodes × 30 paired seeds × 5 variants × 2 protocols), 60 pilot runs and 40 independent original-enumerator correctness checks completed. All 6,000 full optimizations return legal exact optima. No historical timing or budget-quality rows were mixed into the new measurements. Original nodes, model, exact references and Figure 13 frozen T_exact were reused.

| Variant | Optimal Root (%) | Root Regret | Time (s) | Exact States |
|---|---:|---:|---:|---:|
| Full Hybrid-QMF | 71.50 | 63.66 | 0.3813 | 309.6 |
| w/o QMF Selection | 74.50 | 47.83 | 0.3783 | 310.8 |
| w/o Shared Cache | 70.25 | 78.46 | 0.4171 | 390.1 |
| w/o Incumbent Feedback | 76.50 | 62.47 | 0.3514 | 282.5 |
| w/o Recursive Decomposition | 65.83 | 97.75 | 0.7098 | 309.6 |

Root quality uses 0.5T_exact; time/states use full optimization. Unavailable roots count as failures. Regret is defined only for returned roots: 38 of 40 nodes, with feasible counts 1093/1099/1091/1095/1070 out of 1200 in row order. Fixed-node means and paired confidence intervals are in `04_metrics/`. Actual formal seeds are 2026101100–2026101129, reused from Figure 11's original records.

- Final paper PDF: [SecPaper_Yaqi-2-Hybrid-Ablation.pdf](06_reports/paper_build/SecPaper_Yaqi-2-Hybrid-Ablation.pdf), 14 pages, automatic TABLE II on page 11.
- [Final report](06_reports/ABLATION_FINAL_REPORT.md) and [protocol](06_reports/ABLATION_PROTOCOL.md).
- [Table LaTeX](05_tables/ABLATION_TABLE.tex) and [bilingual analysis](06_reports/ABLATION_ANALYSIS_EN_ZH.md).
- [Raw consolidated CSV](04_metrics/ABLATION_RAW_RESULTS.csv), [summary](04_metrics/ABLATION_SUMMARY.csv), [dataset summary](04_metrics/ABLATION_BY_DATASET.csv), [paired differences](04_metrics/PAIRED_DIFFERENCES.csv).
- [Source audit](01_audit/EXISTING_RESULTS_AUDIT.md), [validation](06_reports/ABLATION_VALIDATION.md), [PDF checks](06_reports/PAPER_BUILD_VALIDATION.md).
- `03_runs/formal/`: 12,000 immutable original JSON records. `03_runs/pilot/`: separate pilot. Full terminal logs are retained.
- `01_audit/`: original paper/source backups, input/reference archive, Git status, source diffs, dependency/source hashes and historical reuse records.

Run `bash hybrid_qmf_ablation/ABLATION_REPRODUCE.sh` from the QMF directory to validate/resume the existing frozen campaign and rebuild artifacts. It skips completed runs, refuses mismatched optimizer code/environment, and does not overwrite raw checkpoints. A fully fresh campaign requires a separate output directory; preserve these measurement records. `ABLATION_COMPILE.sh` rebuilds the paper using local dependencies.

This cohort does not demonstrate a quality advantage for QMF selection or feedback scheduling. Shared caching reduces exact work by 20.64% and time by 8.60%; direct enumeration takes 1.86× Full time. See the paired node-level CIs before drawing general conclusions. Figure 1–16 and all historical results are preserved; the supplied original PDF is unchanged.
