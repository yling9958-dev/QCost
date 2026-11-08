# Q-COST Random Frontier Selection ablation

This is the new five-row component ablation. The selection-off row means **uniform random frontier selection**, implemented by the original M4 branch. No old BestFirst result is reused for it.

- [Scientific report](QMF_RANDOM_ABLATION_REPORT.md)
- [New Random raw measurements](QMF_RANDOM_ABLATION_RAW.csv)
- [Five-row verified summary](QMF_RANDOM_ABLATION_SUMMARY.csv)
- [Generated table](ABLATION_TABLE_FIVE_VARIANTS.tex)
- [Updated paper PDF](06_pdf/SecPaper_Yaqi-2-Random-Ablation.pdf)
- [Latest main source](05_latex/IEEE-conference-template-062824.tex)
- [Build and consistency checks](07_reports/LATEX_BUILD_AND_CONSISTENCY.md)

All current Figure 1–16 and original four-row measurements are preserved. Run `bash 08_reproduce/reproduce_all.sh`; build only with `bash 08_reproduce/build_paper.sh`. Existing checkpoints resume without overwrite. Archived raw data remain at their original paths. New JSON logs are in `03_runs/formal/`; contemporaneous Full controls are in its `controls/` subdirectory and are excluded from the primary table.
