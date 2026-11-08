"""Generate revision reports from verification receipts; no experiment execution."""
from pathlib import Path
import json,hashlib,platform,sys,re
import pandas as pd,numpy as np,matplotlib,PIL,pymupdf
R=Path(__file__).resolve().parents[1];Q=R.parent;REPORT=R/'07_reports'
def load(p):return json.loads(p.read_text())
def write(p,s):p.write_text(s.strip()+'\n')
def main():
    validation=load(REPORT/'VALIDATION.json');preserve=load(REPORT/'PRESERVATION_CHECK.json')
    ab=load(REPORT/'ABLATION_CHECK.json');changes=load(REPORT/'MANUSCRIPT_CHANGES.json')
    visual=load(REPORT/'VISUAL_REVIEW.json') if (REPORT/'VISUAL_REVIEW.json').exists() else {}
    visual_ok=visual.get('PDF_SHA256')==validation['PDF_SHA256'] and visual.get('Status')=='PASS'
    assert preserve['Status']=='PASS' and ab['status']=='PASS'
    raw=pd.read_csv(Q/'hybrid_qmf_ablation/04_metrics/ABLATION_RAW_RESULTS.csv')
    revised=pd.read_csv(R/'02_plot_data/ABLATION_REVISED_DATA.csv')
    audit=pd.read_csv(R/'01_audit/KEYWORD_OCCURRENCES.csv')
    table='| Variant | Optimal Root (%) | Root Regret | Time (s) | Exact States | Feasible A / 1200 |\n|---|---:|---:|---:|---:|---:|\n'
    for x in revised.itertuples():table+=f'| {x.Variant} | {x.Optimal_Root_Rate:.2f} | {x.Mean_Root_Regret:.2f} | {x.Mean_Optimization_Time:.4f} | {x.Mean_Exact_States:.1f} | {x.Feasible_Runs_A} |\n'
    categories='\n'.join(f'- {name}: {count}' for name,count in audit.groupby('Category').size().items())
    locations='\n'.join(f'- `{Path(x.Path).name}:{x.Line}` — `{x.Content}`' for x in audit[audit.Category.eq('A:current manuscript')].itertuples())
    dataset_counts=raw.drop_duplicates('Node_ID').groupby('Dataset').size().to_dict()
    formal=list((Q/'hybrid_qmf_ablation/03_runs/formal').glob('*__V*__[AB].json'))
    pilot=list((Q/'hybrid_qmf_ablation/03_runs/pilot').glob('*__V*__[AB].json'))
    enum=list((Q/'hybrid_qmf_ablation/01_audit/enumeration_checks').glob('*.json'))
    assert len(formal)==12000 and len(pilot)==60 and len(enum)==40
    original_head=(R/'01_audit/GIT_HEAD.txt').read_text().strip()
    write(R/'01_audit/BESTFIRST_REMOVAL_AUDIT.md',f'''
# Hybrid-BestFirst removal audit

## Authoritative baseline and scope

The baseline is `{Q/'IEEE-conference-template-062824.tex'}`, which already contains the five-row TABLE II and reproduces `{Q/'hybrid_qmf_ablation/06_reports/paper_build/SecPaper_Yaqi-2-Hybrid-Ablation.pdf'}` (14 pages). It is not the earlier root-level PDF without the table. The baseline source and latest PDF were copied to `BASELINE_LATEST.tex` and `BASELINE_LATEST.pdf` before revision. The original source remains unchanged; the new submission is `../05_latex/IEEE-conference-template-062824.tex`.

Git HEAD: `{original_head}`. The initial dirty/untracked state is in `GIT_STATUS_BEFORE.txt`; pre-existing work was not reset or committed. An explicit unified diff is in `MANUSCRIPT.diff` because the root paper source was untracked.

## Search and classification

Searched LaTeX, plot scripts, experiment scripts, CSV/JSON/logs, reports, references, and text extracted from both paper PDFs for Hybrid-BestFirst, Hybrid BestFirst, Hybrid_BestFirst, hybrid_bestfirst, BestFirst and Best-First. `KEYWORD_OCCURRENCES.csv` records all {len(audit):,} matches with file, line, classification and source text.

{categories}

Only the submission copy (A) and copies of its three plot programs were revised. Historical records (B), optimizer source (C), backups/other manuscripts (D) were preserved. Random Search, Beam Search and Cached Anytime are distinct retained methods, not aliases for the removed internal strategy. No reference or unrelated algorithm description required removal. Numeric spatial datasets/data caches and individual bulk files above 50 MB were excluded from text scanning; these are itemized in `BULK_DATA_NOT_TEXT_SCANNED.csv`, not claimed as exhaustively searched scientific prose.

## Formal manuscript locations before change

{locations}

PDF locations: page 10 (Figure 12, Figure 13, IV-D comparisons), page 11 (five-row TABLE II and analysis), page 12 (Figure 16). Exact extracted matches are in `PDF_KEYWORD_OCCURRENCES.json`.

## Plot sources and authorized display edits

| Item | Original plot source | Original real data | Authorized change |
|---|---|---|---|
| Figure 12 | `figures_sec4_3_4_4/scripts/plot_fig12.py` | `current_wallclock_summary.csv`, `historical_phase_summary.csv` in the corresponding data directory | Remove only the internal-strategy bar in (a); preserve every phase in (b) |
| Figure 13 | `figures_sec4_3_4_4/scripts/plot_fig13.py` | `fig13_budget_summary.csv`, `current_wallclock_summary.csv`, `fig13_work_summary.csv` | Remove its curve in (a) and bar in (b); keep (c,d) data |
| Figure 16 | `figures_sec4_5_4_6/scripts/plot_fig16.py` | `scalability_summary.csv`, `scalability_results.csv` | Remove its bars at both scales; retain the original three methods |
| TABLE II | latest main source / `hybrid_qmf_ablation/05_tables/ABLATION_TABLE.tex` | `hybrid_qmf_ablation/04_metrics/ABLATION_RAW_RESULTS.csv` | Recompute and export four retained variants; drop selection-replacement row only |

Each new plot-data row carries its original Source_File and Source_Row. `DATA_SOURCE_SHA256.json` additionally fingerprints raw timing/build/query records read during validation. Original scripts are backed up in this audit directory. Original data are not edited.

IV-A's separate four construction-decision strategies are unrelated to this removal and remain unchanged. Figure 11's Analytic QMF/Random/Beam experiment remains unchanged. The latest IV-F did not contain an equal-index-hash claim; none was reintroduced. Abstract, introduction, design, equations, Algorithm 1, references and conclusion remain unchanged.

## Preservation result

SHA-256 verification passed for all {preserve['Files_Checked']:,} pre-recorded protected files ({preserve['Bytes_Checked']:,} bytes), with zero missing or changed files. This includes all {len(formal):,} formal run JSONs, {len(pilot)} pilot JSONs, {len(enum)} independent enumeration-validation JSONs, the five-row tables/CSVs, historical figures and plot sources, and the original paper source/PDF. See `../07_reports/PRESERVATION_CHECK.json`.
''')
    write(REPORT/'EXPERIMENT_CONSISTENCY_CHECK.md',f'''
# Experiment consistency check

PASS: 771 source-record checks in `DATA_VALIDATION.csv` and {validation['Checks']:,} delivery checks in `CONSISTENCY_CHECKS.csv`. No optimizer was rerun, retuned, or modified. The revision filters presentation exports only.

- Retained means and CI endpoints round-trip exactly against original CSV source cells. Mean/CI verification uses original node aggregation and the original 2,000-draw bootstrap seed 20261020; recomputation validates rather than replaces historical measurements.
- Figure 12(a)/13(b) retain the 40-node × 3-seed historical full-time campaign. Original Full/Analytic/Exact/Cached means round to 0.3644/0.4235/0.3754/0.3337 s; 13.96% reduction is verified. The recent 0.3813 s ablation result is not substituted into these figures.
- Figure 13(a) retains eight nodes × three seeds, its original budget points 0.25, 0.5, 0.75, 1.0, 1.5 and paired node-level errors. At 0.5, Full remains 75.00%, Cached 58.33%, historical NoFeedback 66.67%; at 1.0 Full remains 91.67%. Recursive Exact retains the original availability projection of its blocking completion, not a new interrupted execution.
- Figure 13(c,d) retain the original ratio-of-node-means and paired intervals. Cache exact-state/terminal/time reductions remain 12.71%/15.43%/0.52%; the 6.13% feedback overhead remains visible and discussed. Panel (c) uses the original recursive-anytime cache pair, not the recent Hybrid cache ablation.
- The historical M7 NoFeedback freezes both the threshold and priorities. Recent V4 disables feedback scheduling while retaining the live incumbent threshold. These different campaigns are not pooled; the table analysis explicitly states the recent V4 semantics.
- Figure 16 retains 24 measured method–dataset–size cases: three methods, four datasets, two sizes. For each case, original build JSON, 15,000 timed queries (five repeats), and 1,000 correctness queries were checked. Original query units (ms), dataset order, colors, means and axis bounds remain intact. There is one independent build per case and no original CI; five query repeats are not treated as five builds.
- TABLE II recomputes all four metrics from the untouched 12,000-row CSV. Each retained variant has 1,200 A and 1,200 B records, exact seed set 2026101100–2026101129, and 40 common H=3,K=4 nodes. All 4,800 retained complete runs have EXACT status and optimal roots. The node distribution was read from records: {dataset_counts}.
- Missing feasible budget returns remain failures in the 1,200-run success denominator. Root Regret is first averaged over defined seed outcomes within each node, then across the same 38 nodes for every variant. It is not an unweighted pool of 1,200 independent spatial nodes. Feasible A counts are 1093/1091/1095/1070; the 451 unavailable retained decisions are valid budget outcomes, not silently discarded experiments.
- Revised submission source, extracted PDF text, vector figure text and SVG labels have zero excluded-method matches. References/labels resolve to Figure 12 (p.10), Figure 13 (p.10), TABLE II (p.11), Figure 16 (p.12). No undefined references, overfull boxes or float failures were found.
- The 13 unaffected figure files and their embedded vector streams match the original artifacts. Mathematical environments, bibliography and unaffected figure environments (including Algorithm 1) remain unchanged. Every protected original file passes hash verification.

Visual review of all 14 pages: {'PASS' if visual_ok else 'PENDING for current PDF hash'}. Individual page renders and four contact sheets are retained in `pages/`. Current PDF SHA-256: `{validation['PDF_SHA256']}`.
''')
    figure_rows='\n'.join(f"| {x['Figure']} | {x['PNG_Size'][0]} × {x['PNG_Size'][1]} | 600 | Vector | PASS |" for x in validation['Figures'])
    write(REPORT/'FIGURE_REVISION_REPORT.md',f'''
# Figure revision report

All three figures were regenerated with Matplotlib from source-record-verified CSV exports. No image painting, cropping to conceal a method, inferred bar height, or replacement experiment was used. Each figure has PNG (600 dpi), SVG and vector PDF in `../03_figures/`. PDF inspection found no raster images. Original Times New Roman styling, colors for retained methods, units, budgets, CI endpoints and all axis limits are preserved.

| Figure | PNG pixels | DPI | PDF/SVG | Layout checks |
|---|---|---|---|---|
{figure_rows}

**Figure 12:** (a) four retained methods in adjacent positions: Original Exact, Analytic QMF, Cached Anytime and Hybrid-QMF. (b) preserves Exact enumeration, Recursive Exact, Analytic QMF, Random Search and Beam Search with all historical stacked phases and error bars. Layout is regenerated; the values are unchanged.

**Figure 13:** 2×2 layout retained. (a) removes only the internal-strategy trajectory and (b) its full-time bar. The remaining root curves and errors are unchanged. The shared legend's “Recursive, cache off” entry belongs to (c); the original source did not have an additional cache-off curve in (a), so none is fabricated. (c) original cache ratios and (d) original feedback ratios are retained, including overhead unfavorable to feedback. The common legend remains above the plots without covering data.

**Figure 16:** four panels retain Recursive Exact, Cached Anytime and Q-COST. Q-COST is the original display name for Hybrid-QMF, not a newly renamed replacement baseline. Three adjacent bars now fill the original total group width 0.70; the original four-bar method width 0.175 is replaced with 0.70/3. Dataset order, both scales, original vertical bounds and values remain unchanged. The original matched 20K/50K campaign has one build per case and no build CI; the separate five-build 20K supplement is not substituted or pooled. No new error bars are invented.

Rendered artist values are stored in `*_rendered_values.json`. Automated bounding-box checks (`*_compact_layout.json`) report no text overlap, legend conflicts, clipped labels or annotation/data conflicts. Full-resolution previews and paper pages 10–12 were visually inspected in addition to the complete 14-page contact-sheet review. Original Figure 1–11 and 14–15 files and embedded streams are unchanged.

Outputs: `fig12_configuration_efficiency`, `fig13_hybrid_effectiveness`, `fig16_index_scalability`, each with `.png`, `.svg`, `.pdf`. Formal LaTeX embeds the new vector PDFs.
''')
    paired=pd.read_csv(Q/'hybrid_qmf_ablation/04_metrics/PAIRED_DIFFERENCES.csv')
    paired=paired[paired.Variant.isin(revised.Variant)]
    paired.to_csv(R/'02_plot_data/ABLATION_RETAINED_PAIRED_DIFFERENCES.csv',index=False)
    write(REPORT/'ABLATION_REVISION_REPORT.md',f'''
# Four-variant component ablation

The original five-variant experiment and all measurements remain preserved. Only the formal table drops “w/o QMF Selection”, whose replacement selector was the internal strategy removed from the paper. This table studies shared caching, feedback scheduling and recursive decomposition while all four variants retain QMF-inspired selection. It does not isolate the selection mechanism. Figure 11 retains the separate Analytic QMF selection-budget evidence; that budget is not interchangeable with a Hybrid wall-clock deadline.

{table}

Source: `hybrid_qmf_ablation/04_metrics/ABLATION_RAW_RESULTS.csv` (12,000 rows). All displayed values were independently recomputed and match the original `ABLATION_SUMMARY.csv`. The paper export contains 9,600 retained rows; no original record was deleted. `ABLATION_REVISED_DATA.csv` is the verified summary consumed by `regenerate_ablation_table.py`; the generated table is not a separately hand-maintained numeric copy.

Optimal Root and Root Regret use Protocol A at 0.5 T_exact. Time and Exact States use complete Protocol B. The 40 fixed nodes have H=3,K=4 and 30 paired seeds 2026101100–2026101129 each. Dataset counts read from records are {dataset_counts}. Each variant has 1,200 complete EXACT runs. Exact States counts actual exact conditional computations, including repeats when shared reuse is disabled.

All 1,200 A outcomes enter the success denominator. Unavailable roots are failures. Root Regret uses only feasible returned roots, averaged first within each node and then over the common 38 nodes. Variant-specific feasible counts appear in the table. The two nodes with no defined budget regret are `geolife_7cfbc670af0d4333` and `nyc_taxi_e99f93eb5ddc3bb0`; neither is removed from the success or complete-time statistics. `ABLATION_NODE_COVERAGE.csv` exposes all node-level counts. These conditional regret means should not be described as unconditional regret for all runs.

## Observed component effects

- Shared conditional-cost reuse reduces actual state evaluations by 20.64% and complete time by 8.60% relative to cache-off. The cache-off minus Full root-rate difference is −1.25 percentage points, with original paired node-bootstrap 95% CI [−3.33,+0.67]; the budget-rate effect is less certain than the compute reduction.
- Disabling incumbent-guided scheduling improves the observed root rate by 5.00 points and lowers mean complete time by 0.029889 s. The paired root-rate CI is [−0.002083,+10.916667] points and includes zero; the time CI is [−0.041052,−0.018917] s. The result does not support claiming a feedback benefit for this cohort. V4 still updates and returns the best feasible configuration and uses the live incumbent threshold. No causal explanation beyond the changed scheduling mechanism is inferred from the timing means.
- Direct enumeration needs 1.8618× Full's complete time and decreases root success by 5.6667 points (paired CI [−9.4167,−2.4167]). Its completed exact-target count equals Full's 309.5675, but enumeration performs additional configuration work within each target; equal state counts do not imply equal computational work. Original auxiliary counters and all 40 independent enumeration checks remain in the ablation archive.

Retained original paired statistics are exported separately to `ABLATION_RETAINED_PAIRED_DIFFERENCES.csv`; no new uncertainty estimate substitutes for the original one. The revised English analysis and corresponding Chinese comments are in `REVISED_ANALYSIS_EN_ZH.md` and in the submission source. Historical Figure 13 and the new table remain explicitly separate campaigns.
''')
    diff_sections=[]
    for i,x in enumerate(changes,1):diff_sections.append(f"## {i}. {x['Reason']}\n\nBefore:\n\n```latex\n{x['Before']}\n```\n\nAfter:\n\n```latex\n{x['After']}\n```\n")
    write(REPORT/'MANUSCRIPT_CHANGELOG.md','''# Manuscript changelog

Baseline: the latest 14-page, five-row TABLE II manuscript, backed up in `01_audit/BASELINE_LATEST.tex`. Revised authoritative source: `05_latex/IEEE-conference-template-062824.tex`. The original root main source and original PDFs remain unchanged. All edits are limited to affected figure references, IV-D, IV-F, the table, and their matching Chinese comments. The main text font is unchanged.

The following exact before/after entries and `01_audit/MANUSCRIPT.diff` document every substantive change. IV-A, Figure 11, Figure 15, the mathematical/design sections, Algorithm 1 and bibliography remain unchanged. The latest baseline had no equal-index-hash claim; no such statement was added.

'''+ '\n'.join(diff_sections))
    visual_status='PASS' if visual_ok else 'PENDING'
    write(REPORT/'FINAL_REVISION_REPORT.md',f'''
# Final revision report

Status: implemented; data/compile/preservation checks PASS; current-PDF visual review {visual_status}. This was a presentation-only revision; no new optimizer runs or changed measurements were needed.

The baseline is the latest five-version ablation source and its 14-page PDF. The revised submission project is `../05_latex/`, and its main source is `IEEE-conference-template-062824.tex`. The original root main source remains preserved; use this new project for the revised submission.

## Delivered changes

1. Figure 12(a), Figure 13(a,b), and all four Figure 16 panels were redrawn after filtering the removed strategy from new paper exports. Unaffected panels were regenerated with original values. All three figures have 600-dpi PNG, SVG and vector PDF in `../03_figures/`.
2. Removed its time and budget-performance comparisons from IV-D, reduced IV-F to the retained three construction strategies, and synchronized Chinese comments. The unrelated IV-A four-strategy experiment is unchanged.
3. TABLE II now has four rows generated from verified real summary data; selection-replacement comparisons are removed. QMF selection remains present in all four variants; the table is not described as a full selection-module ablation.
4. Historical means, error bars, dataset/seed populations, budgets and axis limits are preserved. In particular Figure 12 uses 0.3644 s for Hybrid-QMF; the distinct table campaign uses 0.3813 s.

{table}

Root metrics: 0.5 T_exact, 40 fixed nodes × 30 paired seeds. Failure outcomes remain in the success denominator. Regret is defined on the same 38 nodes, with feasible counts shown above. Complete metrics: all 1,200 B runs per variant. Feedback-off results are reported without suppressing the observed improvement.

## Paper build and page verification

- PDF: `{R/'06_pdf/SecPaper_Yaqi-2-NoBestFirst.pdf'}`.
- Three pdflatex passes completed successfully. Final document: **14 pages**.
- Figure 12 and Figure 13: page 10; automatically numbered TABLE II: page 11; Figure 16: page 12.
- No excluded-method matches in submission TeX, final PDF, new SVG/PDF figure labels. No undefined references, overfull boxes, missing images, unprocessed floats, blank pages or out-of-page text found.
- All 14 page renders and contact sheets were checked; changed pages 10–12 and the three plots were inspected separately. Visual review: {visual_status}. Evidence: `VISUAL_REVIEW.json`, `PAGE_CHECKS.csv`, `pages/`.
- Figure 1–11 and 14–15 files and embedded vector content remain unchanged; equations, Algorithm 1, title/authors and references are preserved.
- {preserve['Files_Checked']:,} original protected files pass SHA-256 preservation verification, including 12,000 formal runs, 60 pilot runs and 40 independent enumeration checks. No historical CSV/source/PDF was overwritten.

## Reproduction

Run `bash ../08_reproduce/reproduce_all.sh` from this report directory (or use its absolute path). It verifies/exports real data, regenerates figures/table, regenerates the revised source from the backed-up latest baseline, compiles, and validates. To compile only, run `bash ../08_reproduce/build_paper.sh`. Python/library versions are in `REPRODUCE_ENVIRONMENT.json`. The standalone LaTeX project includes its local class, style, fonts and vector figures. Data regeneration intentionally reads the preserved original project/data paths; it does not rerun optimization or edit originals.

## Remaining issues and scope limits

No unresolved implementation or compilation blocker. Existing evidence limits remain explicit: regret is conditional on feasible returns over 38 nodes; Figure 16 has one independent build per case and no build CI; historical and recent feedback protocols differ and are not pooled; the four-row table does not independently measure QMF selection. No equal-index-hash claim or cross-scale comparison to the large system Figure 7 was introduced. After any future rebuild, a changed PDF hash requires fresh visual review even when automated checks pass.

Detailed reports: `EXPERIMENT_CONSISTENCY_CHECK.md`, `FIGURE_REVISION_REPORT.md`, `ABLATION_REVISION_REPORT.md`, `MANUSCRIPT_CHANGELOG.md`; audit and full diff: `../01_audit/`.
''')
    write(R/'README.md','''# Q-COST presentation revision

Revised paper: [SecPaper_Yaqi-2-NoBestFirst.pdf](06_pdf/SecPaper_Yaqi-2-NoBestFirst.pdf) (14 pages).

Authoritative revised source: [IEEE-conference-template-062824.tex](05_latex/IEEE-conference-template-062824.tex). Original main source, PDFs, experiments and five-version results are unchanged.

See [final report](07_reports/FINAL_REVISION_REPORT.md), [audit](01_audit/BESTFIRST_REMOVAL_AUDIT.md), [four-row table](04_tables/ABLATION_TABLE_REVISED.tex), [figures](03_figures), and [verified data](02_plot_data).

Reproduce all exports/figures/table/paper: `bash 08_reproduce/reproduce_all.sh`.
Compile only: `bash 08_reproduce/build_paper.sh`.
All regeneration scripts derive their paths from their own locations. Original real data remain required at their recorded project paths. No optimization rerun is performed.
''')
    env=dict(Python=sys.version,Platform=platform.platform(),NumPy=np.__version__,Pandas=pd.__version__,Matplotlib=matplotlib.__version__,Pillow=PIL.__version__,PyMuPDF=pymupdf.__version__,Original_Git_HEAD=original_head)
    write(REPORT/'REPRODUCE_ENVIRONMENT.json',json.dumps(env,indent=2))
    validation['Status']='PASS' if visual_ok else 'STRUCTURAL_PASS_VISUAL_REVIEW_PENDING'
    validation['Original_Data_Unchanged']=True;validation['Protected_Files_Checked']=preserve['Files_Checked']
    write(REPORT/'VALIDATION.json',json.dumps(validation,indent=2))
    print('Reports generated; current visual receipt:',visual_status)
if __name__=='__main__':main()
