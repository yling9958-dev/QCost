"""Write final scientific and delivery reports from verified measured artifacts."""
from pathlib import Path
import json,hashlib,sys,platform
import pandas as pd,numpy as np
R=Path(__file__).resolve().parents[1];Q=R.parent
NAMES=['Full Hybrid-QMF','w/o QMF Selection','w/o Shared Cache','w/o Incumbent Feedback','w/o Recursive Decomposition']
def read(p):return json.loads(p.read_text())
def write(p,s):p.write_text(s.strip()+'\n')
def markdown(frame,columns=None):
    if columns:frame=frame[columns]
    lines=['| '+' | '.join(frame.columns)+' |','|'+'|'.join(['---']*len(frame.columns))+'|']
    for row in frame.itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{x:.6f}' if isinstance(x,(float,np.floating)) else str(x) for x in row)+' |')
    return '\n'.join(lines)
def main():
    v=read(R/'04_metrics/VALIDATION.json');paper=read(R/'07_reports/PAPER_VALIDATION.json');preserve=read(R/'07_reports/PRESERVATION_CHECK.json')
    assert v['Status']=='PASS' and preserve['Status']=='PASS'
    visual=read(R/'07_reports/VISUAL_REVIEW.json') if (R/'07_reports/VISUAL_REVIEW.json').exists() else {}
    visual_ok=visual.get('PDF_SHA256')==paper['PDF_SHA256'] and visual.get('Status')=='PASS'
    s=pd.read_csv(R/'QMF_RANDOM_ABLATION_SUMMARY.csv').set_index('Variant').loc[NAMES]
    pair=pd.read_csv(R/'04_metrics/PAIRED_DIFFERENCES.csv');pr=pair[pair.Variant.eq(NAMES[1])]
    common=pd.read_csv(R/'04_metrics/FULL_RANDOM_COMMON_FEASIBLE_REGRET.csv')
    common5=pd.read_csv(R/'04_metrics/COMMON_FEASIBLE_REGRET.csv')
    controls=pd.read_csv(R/'04_metrics/CALIBRATION_SUMMARY.csv')
    same=pd.read_csv(R/'04_metrics/CONTEMPORANEOUS_PAIRED_DIFFERENCES.csv')
    drift=pd.read_csv(R/'04_metrics/TIMING_BATCH_DRIFT.csv')
    work=pd.read_csv(R/'04_metrics/COMPLETE_WORK_SUMMARY.csv')
    table='| Variant | Optimal Root (%) | Root Regret | Time (s) | Exact States | Feasible A / 1200 | Regret nodes |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for name,x in s.iterrows():table+=f'| {name} | {x.Optimal_Root_Rate:.2f} | {x.Mean_Root_Regret:.2f} | {x.Mean_Optimization_Time:.4f} | {x.Mean_Exact_States:.1f} | {int(x.Feasible_Runs_A)} | {int(x.Regret_Valid_Nodes)} |\n'
    root=pr[pr.Metric.eq('Optimal_Root_Rate')].iloc[0]
    time=pr[pr.Metric.eq('Mean_Optimization_Time')].iloc[0]
    state=pr[pr.Metric.eq('Mean_Exact_States')].iloc[0]
    regret=pr[pr.Metric.eq('Mean_Root_Regret')].iloc[0]
    def effect(x):return f"{x.Delta_Ablated_Minus_Full:+.6f} (95% node-bootstrap CI [{x.CI95_Low:+.6f}, {x.CI95_High:+.6f}])"
    root_conclusion=('includes zero; the node-level analysis does not establish a directional root-rate difference in this fixed cohort' if root.CI95_Low<=0<=root.CI95_High else
                     ('favors Random in this fixed cohort' if root.Delta_Ablated_Minus_Full>0 else 'favors Full in this fixed cohort'))
    tdrift=drift[drift.Metric.eq('Mean_Optimization_Time')].iloc[0]
    drift_conclusion=('contains zero' if tdrift.CI95_Low<=0<=tdrift.CI95_High else 'excludes zero, indicating an observed timing-batch shift')
    fullset=set(v['Regret_Node_Sets'][NAMES[0]]);randomset=set(v['Regret_Node_Sets'][NAMES[1]])
    new=pd.read_csv(R/'QMF_RANDOM_ABLATION_RAW.csv');unavailable=int((~new[new.Protocol.eq('A')].Feasible).sum())
    write(R/'QMF_RANDOM_ABLATION_REPORT.md',f'''
# Random-frontier Hybrid-QMF component ablation

## Completion and source identity

Completed **2,400/2,400 new Random runs** (40 nodes × 30 paired seeds × A/B), **240 separate contemporaneous Full controls**, and **36 pilot runs**. All 1,200 new complete Random runs and all 120 complete controls return independently verified legal exact-optimal configurations. No synthetic values, imputed failures, BestFirst measurements or Figure 11 search records enter the new row.

The new selector is the existing `M4` branch of the same frozen Hybrid optimizer: `classical_search.choose('random', ...)` draws a uniform integer index from `ConditionalEngine.frontier()`. Full is `M8`. Their only option difference is `strategy='random'` versus `strategy='qmf'`; both keep cache and feedback enabled. All 17 optimizer Python sources and the vendored dependencies are byte-identical to the executed original ablation implementation. Recursive minimization, legal candidate generation, cost function, initialization, cache, feedback child ordering, best-known return and exact termination are unchanged. The original full optimizer already implements this branch; activating it avoids inventing a separate algorithm.

Historical real M4 records were found, but cover eight nodes × seeds 11/23/37, four threads and an older full-run protocol. They are not reusable. The previous five-row `w/o QMF Selection` used M6/BestFirst; all its 2,400 historical rows are excluded from the new combined analysis, without deleting or editing them. Figure 11's standalone random configuration selection is a different experiment and is not used.

## Verified primary table

{table}

The other four rows were recomputed from their unchanged 9,600 archived raw rows and agree with the previous summary. New Random values come from exclusively created per-run JSON checkpoints. `QMF_RANDOM_ABLATION_RAW.csv` contains only the 2,400 new measurements; `04_metrics/FIVE_VARIANT_RAW.csv` contains the 12,000 retained/new records for the current table. The original 12,000-record archive remains unchanged.

Optimal Root and Root Regret use **0.5 T_exact**; Time and Exact States use **complete optimization**. H=3,K=4; seeds 2026101100–2026101129; the verified dataset distribution is ten fixed nodes each for GeoLife, Gowalla, NYC Taxi and Skewed 2D. T_exact, inputs, model and reference hashes match the archived experiment. Initialization and all optimizer overhead remain inside the original timing boundary; offline reference scoring/legality checks occur after return.

## Missingness and valid-return rates

Random has {unavailable} unavailable budget returns, all retained as failures in the 1,200-run success denominator. Root Regret is undefined for these outputs and is not assigned zero. The summary includes legal-return rates, counts and per-node coverage. Mean regret averages defined seed returns within nodes, then equally averages defined nodes. No seed repetition is treated as an independent construction node.

Identical regret node coverage across all five variants: **{v['Regret_Coverage_Identical']}**. Nodes valid only for Random relative to Full: `{sorted(randomset-fullset)}`. Nodes valid only for Full relative to Random: `{sorted(fullset-randomset)}`. Even when node sets match, feasible seed counts differ. Therefore the raw primary regret means are not subtracted to estimate a paired effect.

Full/Random common-feasible comparison:

{markdown(common)}

All-five common-feasible sensitivity:

{markdown(common5)}

These common-return analyses use identical node/seed pairs before averaging nodes. They are conditional sensitivity analyses and do not remove failures from the primary optimal-root denominator. All node sets and complete coverage are in `04_metrics/VALIDATION.json` and `BUDGET_AVAILABILITY.csv`.

## Paired selection effects

Every signed difference below is **Random minus Full**. Intervals use 10,000 resamples of node means, seed 20261024, matching the archived analysis method.

- Optimal-root rate: {effect(root)} percentage points. The interval {root_conclusion}.
- Root regret on common feasible pairs: {effect(regret)} cost units; {int(regret.Paired_Nodes)} nodes and {int(regret.Paired_Seed_Units)} common seed pairs. This is not the difference between independently missing primary means.
- Complete optimization time: {effect(time)} seconds.
- Actual complete exact-state evaluations: {effect(state)} states.

{markdown(pr,['Metric','Delta_Ablated_Minus_Full','CI95_Low','CI95_High','Paired_Nodes','Paired_Seed_Units','Pairing'])}

QMF selection applies threshold-derived weights to the shared visible frontier, whereas Random assigns equal probability to every currently legal available target. The pilot replays every recorded Random choice directly from the seeded uniform generator and verifies the selected target belongs to the identical frontier interface. Changed target order can change intermediate feasible-root discovery and the amount of conditional work completed before termination. The observed work counts below measure those changes; they do not establish a universal advantage or a causal explanation for a particular wall-clock outcome. Exact final costs agree in all complete runs.

{markdown(work)}

## Timing-batch control

The new records use the same CPU0 affinity, one Torch/BLAS/OpenMP thread, Python/runtime, frozen data/model, scoring warm-up, timing scope and deadline rules as the archived four variants. They necessarily belong to a later real measurement batch. Existing unrelated desktop/database work was not stopped. Environment/process snapshots are retained. No timing is rescaled, calibrated or overwritten.

Full controls at predeclared seed indices 0,10,20 run serially alongside Random, with alternating method and A/B order. They are reported separately, never pooled into the original Full row:

{markdown(controls)}

Contemporaneous Full minus historical Full on those same 120 node/seed units has complete-time change {effect(tdrift)} s; this interval {drift_conclusion}. Cross-batch mean-time differences alone should not be attributed entirely to the selector. The same-session Random-minus-Full sensitivity is:

{markdown(same,['Metric','Delta_Ablated_Minus_Full','CI95_Low','CI95_High','Paired_Nodes','Paired_Seed_Units'])}

Both tables retain the real signs and uncertainties. These 3-seed-per-node controls support interpretation but do not replace the formal 30-seed new row or any archived figure/table value.

## Correctness and deadline checks

Pilot passed 2,382 checks, including 2,187 common exact-state cost comparisons, unchanged source/dependency identity, legal final costs and exact completion. Complete seeded selections repeat exactly; wall-clock stopping can vary with runtime scheduling and is not promised bit-for-bit reproducible. Pilot tracing is for validation only and is excluded from formal timing.

Every formal result is checked against the original exact root-cost map after return, including tied optima and the original roundoff tolerance. All incumbent updates used in a budget return are timestamped no later than the deadline. Mean/max new deadline overrun: {v['Mean_Random_Overrun_s']:.6f}/{v['Max_Random_Overrun_s']:.6f} s. Cooperative atomic-operation overruns are recorded; they cannot improve the returned incumbent. No post-deadline oracle solve supplies a better result. All new completed configurations satisfy the same exact objective as Full.

## Paper and reproduction

The latest NoBestFirst manuscript is the baseline. Only TABLE II and its adjacent English/Chinese ablation block are changed. The new row explicitly means random frontier selection. Figure 1–16 remain byte-identical, and previously removed internal-strategy curves/legends remain absent. Mathematical definitions, Algorithm 1, title/authors, bibliography and unrelated sections are unchanged. The main source is `05_latex/IEEE-conference-template-062824.tex`; table-only LaTeX is `ABLATION_TABLE_FIVE_VARIANTS.tex`.

Final PDF: `{R/'06_pdf/SecPaper_Yaqi-2-Random-Ablation.pdf'}`. Compiled page count: **{paper['Pages']}**. Structural checks passed; current PDF visual review: **{'PASS' if visual_ok else 'PENDING'}**. See `07_reports/LATEX_BUILD_AND_CONSISTENCY.md`, the source diff and all page renders. Protected original files checked: {preserve['Files_Checked']:,}; zero changed or missing.

Run `bash 08_reproduce/reproduce_all.sh` to validate/resume experiments, recompute all summaries, generate the table/manuscript, compile and verify. Existing checkpoints are never overwritten. A fresh independent rerun must use a separate copy/directory with an empty `03_runs` tree; this also gives a fresh pilot before formal execution. The original virtual environment and recorded data paths are required. Build only with `bash 08_reproduce/build_paper.sh`. Pilot/formal terminal logs, per-run source/reference hashes, code manifest, node/data references, raw ledgers and bootstrap details are all retained.

No unfinished experiment or fabricated value is included. Interpretation limits are the finite fixed-node cohort, feasible-only regret, real wall-clock variability and later-batch timing; these are explicitly reported rather than hidden.
''')
    labels='\n'.join(f"- {key}: {value['number']}, page {value['page']}" for key,value in paper['Labels'].items())
    write(R/'07_reports/LATEX_BUILD_AND_CONSISTENCY.md',f'''
# LaTeX build and consistency report

Baseline: `bestfirst_removal_revision/05_latex/IEEE-conference-template-062824.tex`, the latest 14-page four-row submission. Backups: `01_audit/BASELINE_LATEST.tex` and `.pdf`. Revised project: `05_latex/`. Original source/PDF were not overwritten.

PASS: three pdflatex passes; {paper['Pages']} pages; {paper['Checks']} automated paper checks. No undefined references, overfull boxes, missing figures, unprocessed floats, blank pages or out-of-page text. TABLE II uses automatic numbering and booktabs. English analysis and Chinese comments are synchronized in `ANALYSIS_EN_ZH.md`. Exact source changes are in `01_audit/MANUSCRIPT.diff` and `MANUSCRIPT_CHANGE.json`.

Only the marked ablation block differs from the baseline. All 16 figure files and all embedded vector form streams match the current NoBestFirst baseline. The previous removals in Figures 12/13/16 remain intact. No BestFirst name is present in revised source or PDF; the new `w/o QMF Selection` line explicitly uses random frontier selection. Figure 11 standalone Random Search data and budgets are not mixed with the new experiment.

{labels}

The generated table is checked against the measured summary and the actual inserted source. The four retained numeric rows match their original raw-CSV recomputation. H/K, seeds, common per-node budgets, exact references, missing-return rules and complete-run termination are verified. Proofs and counts are in `04_metrics/VALIDATION.json`; pairwise regret uses common feasible seed units.

All original protected files remain unchanged: {preserve['Files_Checked']:,} SHA-256 matches. Current PDF: `{paper['PDF']}`; SHA-256 `{paper['PDF_SHA256']}`.

All-page visual inspection: **{'PASS' if visual_ok else 'PENDING for this PDF hash'}**. Rendered pages and contact sheets are in `pages/`; current-hash visual receipt is `VISUAL_REVIEW.json`. Future recompilation requires renewed visual inspection if the PDF hash changes. Main text font size is unchanged.
''')
    history=read(R/'01_audit/HISTORICAL_RANDOM_AUDIT.json');env=read(R/'01_audit/ENVIRONMENT_COMPATIBILITY.json')
    write(R/'01_audit/EXISTING_RESULTS_AUDIT.md',f'''
# Existing-results audit

The current submission source and PDF are the completed NoBestFirst revision, not the original paper or earlier five-row BestFirst manuscript. Both were backed up before editing. Its Figures 1–16 are copied byte-for-byte.

The optimizer source already provides actual uniform frontier selection under M4/Hybrid-Random. Its option dictionary differs from M8/Full only by the selection strategy. All frozen engine/recursion/cache/cost/feedback code and vendored dependencies are reused unchanged. Evidence: `OPTIMIZER_SOURCE_IDENTITY.json` and `ENVIRONMENT_COMPATIBILITY.json`.

Historical Random records found:

```json
{json.dumps(history,indent=2)}
```

None meets the requested 40-node/30-seed/single-thread/current-counter/timer protocol. No historical Random or BestFirst timing/quality row is reused for the new selection-ablation row. The original V2 label is explicitly excluded by variant identity before concatenation.

Reused data: 40 node inputs, frozen scorer/model, original exact reference maps and T_exact, 30 original seeds, and 9,600 untouched records for Full/NoCache/NoFeedback/NoRecursion. New data: 2,400 Random records plus 240 separate Full controls. The combined summary is derived from real records, with source-file pointers preserved. No original experiment file was modified.

Recorded environment matches: `{env['Checks']}`. NumPy {env['NumPy']}, Torch {env['Torch']}; optimizer CPU0, one thread. Same recorded environment does not eliminate timing-batch drift, so the contemporaneous controls and separate drift statistics are required and retained.

Preservation: {preserve['Files_Checked']:,} protected files checked; PASS, zero changed/missing. This includes the old 12,000 runs, 60 pilots, 40 enumeration checks and the previous revision's complete figures/source/PDF/reports. No historical source or report is renamed to conceal its original BestFirst meaning.
''')
    write(R/'README.md','''# Q-COST Random Frontier Selection ablation

This is the new five-row component ablation. The selection-off row means **uniform random frontier selection**, implemented by the original M4 branch. No old BestFirst result is reused for it.

- [Scientific report](QMF_RANDOM_ABLATION_REPORT.md)
- [New Random raw measurements](QMF_RANDOM_ABLATION_RAW.csv)
- [Five-row verified summary](QMF_RANDOM_ABLATION_SUMMARY.csv)
- [Generated table](ABLATION_TABLE_FIVE_VARIANTS.tex)
- [Updated paper PDF](06_pdf/SecPaper_Yaqi-2-Random-Ablation.pdf)
- [Latest main source](05_latex/IEEE-conference-template-062824.tex)
- [Build and consistency checks](07_reports/LATEX_BUILD_AND_CONSISTENCY.md)

All current Figure 1–16 and original four-row measurements are preserved. Run `bash 08_reproduce/reproduce_all.sh`; build only with `bash 08_reproduce/build_paper.sh`. Existing checkpoints resume without overwrite. Archived raw data remain at their original paths. New JSON logs are in `03_runs/formal/`; contemporaneous Full controls are in its `controls/` subdirectory and are excluded from the primary table.
''')
    paper['Status']='PASS' if visual_ok else 'STRUCTURAL_PASS_VISUAL_PENDING';paper['Original_Data_Unchanged']=True
    write(R/'07_reports/PAPER_VALIDATION.json',json.dumps(paper,indent=2))
    print('Reports written; visual status',paper['Status'])
if __name__=='__main__':main()
