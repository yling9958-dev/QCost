"""Evidence-grounded audit, Q1–Q10 answers and complete delivery report."""
from pathlib import Path
import json,time,hashlib,platform,sys
import pandas as pd,numpy as np
R=Path(__file__).resolve().parents[1];O=R/'03_metrics'
def read(p):return json.loads(p.read_text())
def write(p,s):p.write_text(s.strip()+'\n')
def md(frame,cols=None):
    if cols:frame=frame[cols]
    lines=['| '+' | '.join(frame.columns)+' |','|'+'|'.join(['---']*len(frame.columns))+'|']
    for row in frame.itertuples(index=False,name=None):lines.append('| '+' | '.join(f'{x:.6f}' if isinstance(x,(float,np.floating)) else str(x) for x in row)+' |')
    return '\n'.join(lines)
def main():
    v=read(O/'VALIDATION.json');assert v['Status']=='PASS'
    paper=read(R/'06_reports/PAPER_VALIDATION.json');preserve=read(R/'06_reports/PRESERVATION.json');assert preserve['Status']=='PASS'
    visual=read(R/'06_reports/VISUAL_REVIEW.json') if (R/'06_reports/VISUAL_REVIEW.json').exists() else {}
    visual_ok=visual.get('PDF_SHA256')==paper['PDF_SHA256'] and visual.get('Status')=='PASS'
    nodes=pd.read_csv(R/'01_code_audit/NODE_MANIFEST.csv');pairs=pd.read_csv(O/'QMF_PAIRED_STATISTICS.csv');summary=pd.read_csv(O/'QMF_SELECTION_METRICS.csv')
    diag=pd.read_csv(O/'MECHANISM_DIAGNOSTICS.csv');work=pd.read_csv(O/'RUN_MECHANISM_SUMMARY.csv')
    sub=pd.read_csv(O/'PREDECLARED_SUBGROUPS.csv');pilot=read(R/'01_code_audit/PILOT_PASS.json');overhead=pd.DataFrame(pilot['Overhead'])
    overhead['Delta_s']=overhead.Observed-overhead.Bare;overhead['Ratio']=overhead.Observed/overhead.Bare
    overhead.to_csv(O/'PILOT_OBSERVER_OVERHEAD.csv',index=False)
    hist=read(R/'01_code_audit/HISTORICAL_TRAJECTORY_AUDIT.json');reference=read(R/'01_code_audit/NEW_REFERENCE_VALIDATION.json')
    def effect(co,metric,b=.5,contrast='QMF_with_Feedback'):
        return pairs[pairs.Cohort.eq(co)&pairs.Metric.eq(metric)&pairs.Budget_Ratio.eq(b)&pairs.Contrast.eq(contrast)].iloc[0]
    def display(x,scale=1):return f"{x.Mean_Difference*scale:+.4f} [95% CI {x.CI95_Low*scale:+.4f}, {x.CI95_High*scale:+.4f}]; adjusted p={x.Adjusted_P:.6g}; {int(x.Nodes)} nodes/{int(x.Paired_Runs)} paired runs"
    primary=pairs[pairs.Primary];primary_rows=[]
    for metric,budget in [('Optimal_Root',.5),('Anytime_AUC',1.)]:
        old=effect('Original',metric,budget);new=effect('Validation',metric,budget)
        replicated=bool(old.Adjusted_P<.05 and new.Adjusted_P<.05 and old.Mean_Difference*new.Mean_Difference>0)
        primary_rows.append(dict(Metric=metric,Original_Difference=old.Mean_Difference,Original_Adjusted_P=old.Adjusted_P,
            Validation_Difference=new.Mean_Difference,Validation_Adjusted_P=new.Adjusted_P,Replicated=replicated,
            Direction='QMF higher' if new.Mean_Difference>0 else 'QMF lower' if new.Mean_Difference<0 else 'equal'))
    replication=pd.DataFrame(primary_rows);replication.to_csv(O/'PRIMARY_REPLICATION.csv',index=False)
    co='Validation';valid_primary=effect(co,'Optimal_Root');valid_auc=effect(co,'Anytime_AUC',1.)
    primary_supported=primary[primary.Adjusted_P.lt(.05)]
    secondary_supported=pairs[(~pairs.Primary)&pairs.Adjusted_P.lt(.05)]
    secondary_supported.to_csv(O/'EXPLORATORY_SUPPORTED_CONTRASTS.csv',index=False)
    core_columns=['Cohort','Method','Metric','Mean','CI95_Low','CI95_High','Nodes','Valid_Runs','Feasible_Runs','Failed_Returns']
    half=summary[summary.Dataset.eq('Overall')&summary.Method.isin(['QF','RF'])&summary.Budget_Ratio.eq(.5)&summary.Metric.isin(['Optimal_Root','Near_1pct','Near_5pct','Normalized_Regret','Valid_Return'])]
    primary_conclusion=('No primary endpoint has independently replicated support for a stable directional selector effect.' if not replication.Replicated.any() else
        'Replicated primary effects are limited to the endpoints explicitly marked true below; direction must be interpreted separately for success rate and loss.')
    answer=[]
    answer.append('## Q1. Is QMF more likely to return an optimal root?\n\n'+
        '\n\n'.join(f"{c}: QMF minus Random at 0.5 T_exact = {display(effect(c,'Optimal_Root'),100)} percentage points." for c in ['Original','Validation'])+
        '\n\n'+primary_conclusion+' Optimal-root rates include every no-return run as failure.')
    answer.append('## Q2. Is QMF more likely to return a near-optimal root?\n\n'+
        '\n\n'.join(f"{c}, tolerance {tol}: {display(effect(c,metric),100)} percentage points (exploratory)." for c in ['Original','Validation'] for metric,tol in [('Near_1pct','1%'),('Near_5pct','5%')])+
        '\n\nBoth tolerances were fixed before execution. They are relative to max(|F*|,1e-9); no-return runs fail both criteria.')
    answer.append('## Q3. Does QMF converge earlier?\n\n'+
        '\n\n'.join(f"{c}: full-horizon bounded best-so-far AUC difference = {display(effect(c,'Anytime_AUC',1.))}; restricted first-optimal waiting-time difference = {display(effect(c,'Time_Optimal_Restricted_T',1.))} T_exact units." for c in ['Original','Validation'])+
        '\n\nLower AUC/wait is better. AUC includes loss 1 before feasibility, and never-reaching runs remain censored at the common horizon. First-hit discovery and the currently returned root are different endpoints; the current-incumbent AUC sensitivity is retained.')
    stability=pd.read_csv(O/'SEED_STABILITY_COMPARISON.csv')
    stability=stability[(stability.Metric.eq('Optimal_Root')&stability.Budget_Ratio.eq(.5))|(stability.Metric.eq('Anytime_AUC')&stability.Budget_Ratio.eq(1.))]
    answer[-1]+='\n\nWithin-node seed variability (descriptive exploratory analysis; lower standard deviation does not imply better mean quality):\n\n'+md(stability)
    answer.append('## Q4. Does QMF reach the same root quality with fewer evaluations?\n\n'+
        '\n\n'.join(f"{c}: restricted evaluations-to-optimal difference = {display(effect(c,'Evaluations_Optimal_Restricted',1.))}; useful-evaluation ratio difference = {display(effect(c,'Useful_Evaluation_Ratio',1.),100)} percentage points." for c in ['Original','Validation'])+
        '\n\nWork-to-target censoring depends on the work completed by the time budget, so these restricted counts alone do not prove evaluation efficiency. Read them alongside hit indicators, success rates and completed-candidate counts. M7 counts completed ActionTask calls strictly before the hit, including initialization and nested calls; it is not a count of certified whole-subtree solves. All hit/censored observations are retained.')
    answer.append('## Q5. What is the QMF selection overhead?\n\n'+md(diag[diag.Budget_Ratio.eq(1.)],['Cohort','Method','Candidate_Selections','Selection_Seconds','Selection_Per_Call_s','Selection_Share','Threshold_Updates','Threshold_Acceptance','Mean_Marked_Fraction','Uniform_QMF_Selections'])+
        '\n\nSeconds include the selector’s actual required proxy computation, threshold weighting and sampling. Random performs only uniform legal-frontier sampling and common scheduling work; it does not compute unused QMF proxy arrays. The shared frontier/observer overhead is also included in total wall time. Threshold fields for Random are NA, not zero. Threshold_Updates counts changes in the live incumbent threshold between selections, not changes in the lower-quartile proxy cutoff as the frontier changes. The marked-set acceptance and marked fraction are recorded directly. Uniform_QMF_Selections is the fraction of calls with an empty/full marked set, for which the actual QMF distribution is uniform. When no selector call occurs, per-call overhead is undefined. Overall values average seeds within nodes, then nodes.')
    answer.append('## Q6. Does feedback modify the QMF effect?\n\n'+md(pairs[pairs.Metric.isin(['Optimal_Root','Anytime_AUC'])&(((pairs.Metric=='Optimal_Root')&(pairs.Budget_Ratio==.5))|((pairs.Metric=='Anytime_AUC')&(pairs.Budget_Ratio==1.)))],
        ['Cohort','Metric','Contrast','Mean_Difference','CI95_Low','CI95_High','Adjusted_P','Nodes','Paired_Runs'])+
        '\n\nThe interaction is (QF−RF)−(QN−RN). NoFeedback disables feedback scheduling while retaining best feasible updates and the live incumbent threshold. All interaction and feedback contrasts are exploratory BH-FDR analyses; none licenses changing the formal optimizer after inspecting outcomes.')
    interactions=pairs[pairs.Contrast.eq('Interaction')&((pairs.Metric.eq('Optimal_Root')&pairs.Budget_Ratio.eq(.5))|(pairs.Metric.eq('Anytime_AUC')&pairs.Budget_Ratio.eq(1.)))]
    answer[-1]+=f' Of these four cohort/endpoint interaction tests, {int(interactions.Adjusted_P.lt(.05).sum())} pass exploratory BH-FDR correction.'
    answer.append('## Q7. Which differences have statistical support?\n\n'+md(primary,['Cohort','Metric','Mean_Difference','Median_Difference','CI95_Low','CI95_High','P','Adjusted_P','Nodes','Paired_Runs'])+
        f'\n\n{len(primary_supported)} of the four cohort-specific primary tests pass their within-cohort two-test Holm correction. Secondary/budget/feedback tests are exploratory; {len(secondary_supported)} pass the pooled within-cohort BH-FDR procedure and are fully listed in `EXPLORATORY_SUPPORTED_CONTRASTS.csv`. All signs and nonsignificant contrasts remain in the full statistics. Pointwise bootstrap intervals are not simultaneous familywise intervals. Primary p-values use node sign-flip randomization; secondary p-values use node-level paired t statistics with BH adjustment. The fixed-node design and spatial overlap limit population interpretation.')
    answer[-1]+=' A percentile-bootstrap interval and a sign-flip test need not give identical finite-sample decisions. In particular, the held-out optimal-root interval excludes zero while its prespecified randomization p-value exceeds 0.05. The confirmatory decision follows the frozen Holm-adjusted test, without switching procedures after inspecting results.'
    answer.append('## Q8. Do independent nodes reproduce the original findings?\n\n'+md(replication)+
        '\n\n'+primary_conclusion+' The new forty UIDs do not overlap any of the 53 previously analyzed node UIDs. Selection was frozen by feature-space coverage before root-reference calculation/search outcomes; only H3-infeasible nodes were skipped. They come from the same four saved 20K samples and can spatially overlap or nest other nodes, so this is held-out-node validation, not an independent large-scale dataset replication.\n\n'+md(sub))
    answer.append('## Q9. What can be written in the ICDE paper?\n\nThe verified effect sizes, node-bootstrap uncertainty, exact two-primary decisions, feasibility/censoring definitions and held-out findings can be reported. The paper explicitly distinguishes Hybrid frontier wall-clock search from Figure 11 standalone configuration-selection budgets. TABLE II remains unchanged. TABLE III reports original and held-out cohorts, and the new Figure 17 shows held-out trajectories. Do not claim a general or replicated QMF advantage unless the corresponding preregistered primary endpoint is marked replicated with the beneficial direction; do not promote an exploratory subgroup to a confirmatory result.')
    phase_cols=[c for c in work if c.startswith('Phase_')];bottlenecks=[]
    for x in work.itertuples():
        vals={c:getattr(x,c) for c in phase_cols};dominant=max(vals,key=vals.get)
        bottlenecks.append(dict(Cohort=x.Cohort,Method=x.Method,Largest_Phase=dominant,Mean_Seconds=vals[dominant],
            Mean_Wall_s=x.Full_Wall_s,Any_Selector_Used=x.Any_Selector_Used,Optimal_During_Initialization=x.Optimal_During_Initialization))
    mechanism_explanation=[]
    for co in ['Original','Validation']:
        w=work[work.Cohort.eq(co)&work.Method.eq('QF')].iloc[0]
        m=diag[diag.Cohort.eq(co)&diag.Method.eq('QF')&diag.Budget_Ratio.eq(1.)].iloc[0]
        mechanism_explanation.append(f'{co}: candidate generation/model scoring consumes {100*w.Phase_candidate_generation/w.Full_Wall_s:.2f}% of measured wall time; '
            f'{100*w.Optimal_During_Initialization:.2f}% of runs already discover an optimal root during shared initialization. '
            f'QMF selection consumes {100*m.Selection_Share:.2f}% of the fixed horizon, and {100*m.Uniform_QMF_Selections:.2f}% of its selections have an empty/full marked set and therefore a uniform distribution.')
    answer.append('## Q10. If QMF lacks stable gains, what is the most likely bottleneck?\n\n'+md(pd.DataFrame(bottlenecks))+
        '\n\n'+'\n\n'.join(mechanism_explanation)+
        '\n\nThe main measured time bottleneck is candidate generation/model scoring. Shared initialization and uniform-selection cases limit the opportunity for QMF to improve early root quality. These are phase-cost and opportunity diagnostics, not a causal experiment on the scorer. Threshold acceptance measures a visible proxy, not true offline root quality. A proxy/quality mismatch remains a hypothesis; no QMF sorting bug is established by these aggregate outcomes. Event-level exact-state/candidate/cache logs support further investigation without changing this campaign.')
    write(R/'06_reports/QMF_SELECTION_FINAL_REPORT.md',f'''
# QMF selection effectiveness: final report

Completed {v['Trajectories']:,} real matched trajectories and {v['Snapshots']:,} timestamp-based budget snapshots: two forty-node cohorts × thirty paired seeds × four QMF/Random–Feedback combinations. The protocol was frozen before new outcomes; near-optimal tolerances, two primary endpoints, failure losses and subgroup definitions were not tuned after observing results. All raw events and sources are preserved. No simulated optimizer measurements or BestFirst records are used.

Budget snapshots are real prefixes of the same cooperatively stopped 1.0 T_exact trajectory, not four independently timed executions. Later events never improve earlier snapshots. Pilot actually interrupted all four budget values and verified the returned incumbent rule. A completed optimizer holds its final configuration through the fixed observation horizon; it does not stop because an offline optimal root was recognized.

The current paper compiles to **{paper['Pages']} pages**. Current-hash visual review: **{'PASS' if visual_ok else 'PENDING'}**. Existing TABLE II and Figure 1–16 are unchanged. The final PDF is `{paper['PDF']}`.

## Main half-budget outcomes and coverage

{md(half,core_columns)}

Rates in the machine-readable tables are fractions; multiply by 100 for percentages. Counts explicitly distinguish defined outcomes from all runs. Normalized regret and useful ratios require defined values; their paired differences use the same feasible node/seed units. All primary tests use all forty nodes per cohort.

{chr(10).join(answer)}

## Correctness, observation and preservation

The original 40 T_exact values and root-cost references are reused unchanged. The new references use the same three-repeat median completion definition, with their own recorded timing batch. All forty new root-cost maps match independent complete enumeration ({reference['Total_Configurations']:,} actual configurations in total). Twelve H3-infeasible candidate nodes were skipped by the frozen feasibility-only rule and remain recorded; each selected dataset contributes ten nodes.

Pilot: 168 real runs (frozen/bare/observed complete executions plus actual 0.25/0.50/0.75/1.00 cutoffs on two nodes × three seeds × four methods). Unbudgeted seeded selection sequences and exact costs/counters match. Observer-only subclass hooks record candidate, cache and exact-state events; costs, legal frontier, solver/cache/feedback semantics remain shared. Required diagnostics remove unused counterfactual work from both methods and unused QMF proxy evaluation from Random, with no decision-sequence change. Observed logging overhead is measured but not subtracted:

{md(overhead.groupby('Method')[['Bare','Observed','Delta_s','Ratio']].mean().reset_index())}

This small ordered pilot estimates total observation effects plus runtime noise, not an unbiased causal microbenchmark of a single hook. Formal methods all use the same observer. Every incumbent plan is independently checked for legality and true configuration cost after return. Offline root values are never passed into the online selector. Root ties use the frozen tolerance; Random threshold diagnostics are NA. Candidate completeness and cache/state event counts are independently audited.

Formal mean/max deadline overrun: {v['Mean_Deadline_Overrun_s']:.6f}/{v['Max_Deadline_Overrun_s']:.6f} s. Atomic numerical work can cross the deadline, but only incumbent timestamps at or before a snapshot enter its metrics. Partial calls are not counted as completed before cutoff. Exact reference checks and all JSON writes happen outside search timing.

Historical trajectory reuse: {hist['Records']:,} valid half-budget logs were truthfully extracted into `HISTORICAL_AVAILABLE_METRICS.csv`. They cannot provide missing candidate start/end attribution or other budget horizons and are not pooled into the new matched campaign. Original current-paper data remain unchanged; {preserve['Files']:,} protected files pass SHA-256 verification.

## Deliverables and reproduction

- `01_code_audit/FROZEN_PROTOCOL.md`: definitions, units, directions, denominators, missingness, frozen sampling and statistical tests.
- `01_code_audit/NODE_MANIFEST.csv`: all 80 real nodes, input/reference hashes, T_exact, configuration counts and root gaps.
- `02_raw_logs/formal/`: 9,600 per-run event JSONs; exclusive-create checkpoints and terminal log.
- `03_metrics/QMF_ANYTIME_RAW.csv`: all 38,400 per-run/budget metrics; `INCUMBENT_TRAJECTORIES.csv` preserves real-time root histories.
- `03_metrics/QMF_SELECTION_METRICS.csv`: node-cluster summaries, counts and CIs, including every dataset.
- `03_metrics/QMF_PAIRED_STATISTICS.csv`, `QMF_FEEDBACK_INTERACTION.csv`, `PAIRED_BY_DATASET.csv`: all effects, uncertainty and multiplicity labels.
- `03_metrics/FIRST_OPTIMAL_DISTRIBUTION.csv`, `COVERAGE.csv`, `PREDECLARED_SUBGROUPS.csv`, `MECHANISM_DIAGNOSTICS.csv`: censoring, coverage and complete exploratory diagnostics.
- `03_metrics/SEED_STABILITY.csv`, `SEED_STABILITY_COMPARISON.csv`: within-node seed variation, explicitly exploratory and separate from primary inference.
- `03_metrics/COMMON_VALID_COMPARISON.csv`, `INDEPENDENT_METRIC_CHECK.json`: independently recomputed paired coverage and timestamp-based metric validation.
- `04_tables/QMF_SELECTION_TABLE.tex`: validated TABLE III; original TABLE II remains intact.
- `05_figures/qmf_selection_original.*`, `qmf_selection_validation.*`: each PNG 600 dpi, SVG and vector PDF, with pointwise intervals and consistent axes.
- `07_latex/`: complete revised manuscript project; `06_reports/paper_build/`: compiled PDF/logs.
- `08_reproduce/reproduce_all.sh`: resumes checkpoints, recomputes references/metrics, redraws, builds and validates. Existing raw records are not overwritten; fresh independent runs require a separate workspace with empty run directories.

No scientific advantage is presumed. Remaining interpretation limits are finite fixed cohorts, same-source spatial dependence, feasible-only conditional metrics, real wall-clock variation and observer cost. A longer-budget/more-dataset follow-up would be a new experiment, not a silent extension or selective filter of these results.
''')
    audit=f'''# QMF selection code/data audit

Latest baseline: `qmf_random_ablation_revision/05_latex/IEEE-conference-template-062824.tex` and its 14-page Random-Ablation PDF, backed up in this directory. Existing five-row TABLE II and all Figure 1–16 remain unchanged.

Actual selector code: `src/qmf_frontier_operator.py` builds a visible-proxy lower-quartile/current-incumbent marked set and samples its QMF-inspired amplified distribution. Random uses uniform integer sampling over the same `ConditionalEngine.frontier()` legal tasks. Neither reads exact root-cost references online. `recursive_anytime.py` controls incremental evaluation and feedback child ordering; `conditional_state.py` contains scalar costs, legal generation, incumbent updates and frontier filtering; `shared_cache.py` contains state/terminal/configuration reuse.

The original raw ablation JSONs have timestamped incumbent events but lack per-candidate starts/ends. They cannot substantiate evaluations-to-target or directly attributed useful work. {hist['Records']} logs were reused only for supported historical half-budget metrics; no trajectory was inferred from final CSV values. No BestFirst records were imported.

Fresh instrumentation is isolated to `src/selection_observer.py` and the copied optimizer entry point. All original math/solver/cache source bodies are unchanged; subclass observation calls delegate to original operations. `IMPLEMENTATION.diff` records the entry-point edits. Uniform Random avoids unused QMF proxies and all methods omit unused frozen counterfactual diagnostics. Pilot proves seeded complete selection/cost/counter equivalence, including NoFeedback. The live incumbent threshold remains enabled for QMF NoFeedback, matching the schedule-only ablation definition.

New-node order was written before exact reference and optimizer outcome evaluation. Source census: existing real construction-node memberships from the same four saved 20K samples. Exclude all previously analyzed node UIDs; maximize coverage in geometry/workload feature ranks. First ten H3-feasible nodes per dataset are frozen; all infeasible skips retained. Exact gap/count ranges are described, never used to select QMF wins. Forty references cross-check against complete enumeration ({reference['Total_Configurations']:,} configurations).

Original T_exact is exactly the frozen Phase3 median already used in Figure 13. New T_exact is a recorded median of original Recursive Exact total completion times for repeats 11/23/37. Both selectors/four feedback conditions share the resulting node deadline. The new-reference batch is explicitly distinct.

Two primary endpoints and ten metric definitions are frozen in `FROZEN_PROTOCOL.md`; all other budget, group and interaction tests are exploratory. Same-node seed repetitions are not counted as independent nodes. No-return failures remain in rates, censored discovery observations remain in distributions, and conditional comparisons use common defined pairs. The new formal campaign uses one CPU0 optimizer process and one thread, with rotated method order and identical observer accounting.

Protected historical files: {preserve['Files']:,}; all hashes match. Source archives, initial environment, complete node manifests, pilot receipts, raw-record ledgers and manuscript diff are retained. PDF pages: {paper['Pages']}; visual review: {'PASS' if visual_ok else 'PENDING'}.
'''
    write(R/'01_code_audit/QMF_SELECTION_AUDIT.md',audit)
    write(R/'06_reports/LATEX_VALIDATION.md',f'''# Paper verification

PDF: `{paper['PDF']}`; SHA-256 `{paper['PDF_SHA256']}`. Three pdflatex passes succeeded. Page count: {paper['Pages']}. Current-hash visual review: {'PASS' if visual_ok else 'PENDING'}.

Automated checks: {paper['Checks']}. Baseline source is exactly recovered by removing the two new insertion blocks. TABLE II is byte-identical. All existing figure files and embedded vector forms are preserved. New Table III and Figure 17 have automatic numbering; no excluded internal comparator is restored. No undefined references, overfull boxes, blank pages, missing images or out-of-page text.

All page renders/contact sheets are retained in `pages/`; the visual receipt is `VISUAL_REVIEW.json`. The main body font remains unchanged. Original/Validation new plots each have a 600-dpi PNG, SVG and vector PDF, with matching axes and confidence bands. Statistical values are generated from validated CSVs; no hand-entered performance data.

Labels: `{paper['Labels']}`. Preservation check: {preserve['Files']:,} original files unchanged.
''')
    write(R/'README.md','''# QMF selection diagnostics

Read [final report](06_reports/QMF_SELECTION_FINAL_REPORT.md), [frozen protocol](01_code_audit/FROZEN_PROTOCOL.md), and [code audit](01_code_audit/QMF_SELECTION_AUDIT.md).

Paper: [compiled PDF](06_reports/paper_build/SecPaper_Yaqi-2-QMF-Selection.pdf); [main source](07_latex/IEEE-conference-template-062824.tex); [Table III](04_tables/QMF_SELECTION_TABLE.tex).

All current Table II and Figure 1–16 are retained. New figures and data are in `05_figures/` and `03_metrics/`. Raw real trajectories are in `02_raw_logs/formal/`.

Reproduce with `bash 08_reproduce/reproduce_all.sh`; build only with `bash 08_reproduce/build_paper.sh`. Original source data paths and the recorded Python environment are required. Resume skips completed checksummed records; do not overwrite old checkpoints to rerun. Future PDFs require renewed visual inspection.
''')
    paper['Status']='PASS' if visual_ok else 'STRUCTURAL_PASS_VISUAL_PENDING';write(R/'06_reports/PAPER_VALIDATION.json',json.dumps(paper,indent=2))
    print('Scientific Q1–Q10 report and audits generated; visual:',paper['Status'])
if __name__=='__main__':main()
