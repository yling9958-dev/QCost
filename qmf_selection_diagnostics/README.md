# QMF selection diagnostics

Read [final report](06_reports/QMF_SELECTION_FINAL_REPORT.md), [frozen protocol](01_code_audit/FROZEN_PROTOCOL.md), and [code audit](01_code_audit/QMF_SELECTION_AUDIT.md).

Paper: [compiled PDF](06_reports/paper_build/SecPaper_Yaqi-2-QMF-Selection.pdf); [main source](07_latex/IEEE-conference-template-062824.tex); [Table III](04_tables/QMF_SELECTION_TABLE.tex).

All current Table II and Figure 1–16 are retained. New figures and data are in `05_figures/` and `03_metrics/`. Raw real trajectories are in `02_raw_logs/formal/`.

Reproduce with `bash 08_reproduce/reproduce_all.sh`; build only with `bash 08_reproduce/build_paper.sh`. Original source data paths and the recorded Python environment are required. Resume skips completed checksummed records; do not overwrite old checkpoints to rerun. Future PDFs require renewed visual inspection.
