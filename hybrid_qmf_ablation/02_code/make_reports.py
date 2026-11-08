"""Publication artifacts are generated only after all 12,000 runs validate."""
from pathlib import Path
import json,re,hashlib,difflib
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def markdown(frame,index=False):
    if index:frame=frame.reset_index()
    def cell(v):return f'{v:.6f}' if isinstance(v,float) else str(v)
    return '\n'.join(['| '+' | '.join(map(str,frame.columns))+' |',
                      '| '+' | '.join(['---']*len(frame.columns))+' |']+
                     ['| '+' | '.join(cell(v) for v in row)+' |' for row in frame.itertuples(index=False,name=None)])
def main():
    validation=json.loads((ROOT/'04_metrics/VALIDATION.json').read_text())
    assert validation['status']=='COMPLETE_VALIDATED' and validation['records']==12000
    s=pd.read_csv(ROOT/'04_metrics/ABLATION_SUMMARY.csv').set_index('Variant')
    raw=pd.read_csv(ROOT/'04_metrics/ABLATION_RAW_RESULTS.csv')
    paired=pd.read_csv(ROOT/'04_metrics/PAIRED_DIFFERENCES.csv')
    names=list(s.index);full,best,nocache,nofeedback,enumeration=[s.loc[x] for x in names]
    cache_states=100*(nocache.Mean_Exact_States-full.Mean_Exact_States)/nocache.Mean_Exact_States
    cache_time=100*(nocache.Mean_Optimization_Time-full.Mean_Optimization_Time)/nocache.Mean_Optimization_Time
    feedback_gain=full.Optimal_Root_Rate-nofeedback.Optimal_Root_Rate
    qmf_gain=full.Optimal_Root_Rate-best.Optimal_Root_Rate
    enum_ratio=enumeration.Mean_Optimization_Time/full.Mean_Optimization_Time
    def direction(x):return 'increases' if x>=0 else 'decreases'
    paragraph=(
      r'Table~\ref{tab:qcost_hybrid_ablation} isolates threshold-guided selection, shared conditional-cost reuse, '
      r'incumbent-guided scheduling, and recursive decomposition using five controlled variants. '
      r'We reuse 40 fixed $H=3$, $K=4$ nodes from GeoLife, Gowalla, NYC Taxi, and Skewed 2D, '
      r'with 30 paired seeds per node. '
      rf'At $0.5T_{{\mathrm{{exact}}}}$, Full Hybrid-QMF attains {full.Optimal_Root_Rate:.2f}\% optimal roots, '
      rf'compared with {best.Optimal_Root_Rate:.2f}\% for BestFirst selection. '
      rf'Thus, QMF threshold-guided exploration {direction(qmf_gain)} the measured root-success rate by {abs(qmf_gain):.2f} percentage points in this cohort. '
      rf"Shared caching {'reduces' if cache_states>=0 else 'increases'} exact-state computations by {abs(cache_states):.2f}\%, "
      rf'while incumbent-guided scheduling {direction(feedback_gain)} root success by {abs(feedback_gain):.2f} points. '
      rf'Replacing recursive conditional minimization with direct enumeration requires {enum_ratio:.2f}$\times$ the full optimization time '
      rf'and yields {enumeration.Optimal_Root_Rate:.2f}\% optimal roots under the same budget. '
      r'The feedback ablation retains the live incumbent threshold. '
      r'All complete runs recover an exact optimum. Budget failures remain in success-rate denominators; '
      r'regret averages describe feasible returned roots. Node-level paired confidence intervals accompany the reproducibility records.')
    count=len(paragraph.split());assert 120<=count<=160,count
    zh=(f'表格通过五个受控版本分别检验阈值引导选择、共享条件代价复用、最佳解反馈调度和递归分解。'
        f'沿用四个数据集的40个固定H=3、K=4节点及每节点30个配对种子。0.5T_exact下，完整版本根动作最优率为{full.Optimal_Root_Rate:.2f}%，'
        f'BestFirst为{best.Optimal_Root_Rate:.2f}%，QMF选择的实际差值为{qmf_gain:+.2f}个百分点。'
        f"共享缓存使实际完成的精确状态计算{'减少' if cache_states>=0 else '增加'}{abs(cache_states):.2f}%；反馈调度的根动作最优率差值为{feedback_gain:+.2f}个百分点。"
        f'直接枚举需要完整版本{enum_ratio:.2f}倍的完整优化时间，预算内根动作最优率为{enumeration.Optimal_Root_Rate:.2f}%。'
        '反馈消融保留当前incumbent阈值。全部完整运行均恢复Exact最优解。预算内无可行配置的运行保留在成功率分母中，Root Regret仅对实际返回根动作定义。'
        '节点级配对置信区间随复现记录保存。')
    counts=', '.join(str(int(s.loc[x].Feasible_Runs_A)) for x in names)
    regret_nodes=', '.join(str(int(s.loc[x].Regret_Valid_Nodes)) for x in names)
    table=[r'\begin{table}[t]',r'\centering',r'\caption{Ablation Study of Hybrid-QMF Components}',
           r'\label{tab:qcost_hybrid_ablation}',r'\footnotesize',r'\setlength{\tabcolsep}{2.3pt}',
           r'\begin{tabular}{@{}lrrrr@{}}',r'\toprule',
           r'Variant & Root (\%)$\uparrow$ & Regret$\downarrow$ & Time (s)$\downarrow$ & States$\downarrow$ \\',r'\midrule']
    for name,row in s.iterrows():
        label={'w/o Incumbent Feedback':r'\shortstack[l]{w/o Incumbent\\Feedback}',
               'w/o Recursive Decomposition':r'\shortstack[l]{w/o Recursive\\Decomposition}'}.get(name,name)
        table.append(f'{label} & {row.Optimal_Root_Rate:.2f} & {row.Mean_Root_Regret:.2f} & {row.Mean_Optimization_Time:.4f} & {row.Mean_Exact_States:.1f} '+r'\\')
    table += [r'\bottomrule',r'\end{tabular}',r'\par\vspace{2pt}',r'\parbox{\columnwidth}{\scriptsize',
        r'Root and regret: $0.5T_{\mathrm{exact}}$; time and states: complete optimization. '
        r'Four datasets, 40 fixed nodes, 30 paired seeds (30 timing repeats for deterministic BestFirst). '
        r'Means average seeds within nodes. Unavailable roots count as failures; regret uses feasible returns. '
        f'Feasible budgeted returns, in row order: {counts}, each out of 1,200. '+
        ('Regret is defined on 38 nodes for every variant.' if s.Regret_Valid_Nodes.eq(38).all() else f'Nodes with defined regret: {regret_nodes}, each out of 40.')+r'}',r'\end{table}']
    table='\n'.join(table)+'\n'
    (ROOT/'05_tables/ABLATION_TABLE.tex').write_text(table)
    comment='\n'.join('% '+zh[i:i+45] for i in range(0,len(zh),45))
    addition='\n% BEGIN HYBRID-QMF CONTROLLED ABLATION\n'+table+'\n'+paragraph+'\n\n'+comment+'\n% END HYBRID-QMF CONTROLLED ABLATION\n\n'
    (ROOT/'05_tables/ABLATION_INSERTION.tex').write_text(addition)
    text='# English paper paragraph\n\n'+paragraph+f'\n\nWord count (whitespace tokens): {count}.\n\n# 中文对应段落\n\n'+zh
    text+='\n\n# Measured effects and uncertainty\n\n'+markdown(paired)
    text+=f'\n\nCache time reduction relative to cache-off: {cache_time:.4f}%. Positive means faster with cache. '
    text+='The root-success selection difference is an empirical cohort effect; no quantum-computational speedup is claimed. '
    text+='The feedback ablation retains the live incumbent threshold and best-known return; only scheduling feedback is disabled. '
    text+='Direct enumeration retains sharing and traverses all feasible continuations, so its configuration counts are reported separately from exact conditional-state completions. '
    text+='Intervals use paired fixed nodes, never 1,200 supposedly independent nodes. Regret pairs use only common feasible node/seed pairs, with counts in the paired file.\n'
    (ROOT/'06_reports/ABLATION_ANALYSIS_EN_ZH.md').write_text(text)
    missing={name:int(s.loc[name].Unavailable_Runs_A) for name in names}
    overview=markdown(s[['Optimal_Root_Rate','Mean_Root_Regret','Mean_Optimization_Time','Mean_Exact_States','Feasible_Runs_A','Regret_Valid_Nodes']],index=True)
    report=f'''# Hybrid-QMF five-variant ablation final report

## Experimental completion

12,000/12,000 formal optimizer runs: 40 fixed nodes × 30 original formal seeds × 5 variants × 2 protocols. Additionally 60/60 pilot runs. All 6,000 complete runs returned a legal exact-optimal configuration. Raw per-run JSON, counters, incumbent traces, wall times, references and source hashes are retained under `03_runs/`. No optimizer performance from incompatible historical protocols was pooled. The original nodes, frozen model, exact optima and node-specific T_exact were reused.

## Measured results

{overview}

Optimal-root rate includes unavailable returns as failures. Root regret is undefined without a returned root; it is averaged over feasible seeds within each node, then over nodes with defined regret. The last column explicitly records coverage. Missing decision counts: {json.dumps(missing)}. Complete optimization time is never a truncated timeout. See ABLATION_BY_DATASET.csv, NODE_STATISTICS.csv, METRIC_CONFIDENCE_INTERVALS.csv and PAIRED_DIFFERENCES.csv for disaggregated results and node-based uncertainty.

## Contributions

QMF versus BestFirst: {qmf_gain:+.4f} percentage points in optimal-root rate. Shared caching: {cache_states:.4f}% fewer exact-state completions and {cache_time:.4f}% less complete time relative to cache-off. Feedback scheduling: {feedback_gain:+.4f} percentage points versus feedback off. Direct enumeration: {enum_ratio:.4f}× Full time. These measured effects are retained regardless of sign; paired intervals determine uncertainty. All five methods use the same scalar cost and final exact-completion condition. Exact-state counts alone do not describe the combinatorial configuration work inside V5; see Enumerated_Configurations and Direct_Configuration_Cost_Evaluations.

## Deadline behavior

Mean observed budget return overrun: {validation['mean_deadline_overrun_s']:.6f} s; maximum {validation['max_deadline_overrun_s']:.6f} s. These are cooperative deadlines, not hard-real-time guarantees. Every returned incumbent update timestamp is at or before the requested budget. No reference or post-budget solve improves a returned root.

## Paper and PDF

Final table and 120–160-word analysis are generated only after complete validation. See `05_tables/ABLATION_TABLE.tex`, `ABLATION_INSERTION.tex`, `06_reports/ABLATION_ANALYSIS_EN_ZH.md`, and the separate `PAPER_BUILD_VALIDATION.md` for actual compilation and visual checks. The main LaTeX and original PDF were backed up before editing. Figure 1–16 vector content was recovered byte-for-byte from the original PDF because referenced external figure files were missing. Historical figure datasets and all existing results remain unchanged. Paper changes are tracked by `01_audit/PAPER.diff`; unrelated pre-existing dirty files are untouched.

## Reproduction and limitations

Run `bash hybrid_qmf_ablation/ABLATION_REPRODUCE.sh` to resume/revalidate the frozen campaign without overwriting existing records. Inputs/scorer are read from the audited sibling Phase4 directory. Random searches and deterministic timing repeats are distinguished. No optional additional budget ratios were measured. T_exact retains Figure 13's historical normalization, so it is not a fresh exact-solver speed ratio on the one-thread environment. Desktop OS activity is not eliminated. Budget failures and their undefined regrets are genuine observed limitations, not missing experimental runs. This fixed cohort does not establish universal method superiority.
'''
    (ROOT/'06_reports/ABLATION_FINAL_REPORT.md').write_text(report)
    validation_report=f'''# Ablation validation

- PASS: genuine Phase4 Hybrid M8 copied; original source and diff retained.
- PASS: Figure 11 identities exactly match 40 audited nodes; observed 10 nodes per dataset.
- PASS: H=3, K=4, identical model, points, queries, coefficients, action rules and feasibility.
- PASS: 30 original formal seeds 2026101100–2026101129 paired across all 200 node/variant cells and both protocols.
- PASS: 60 pilot trials, conditional-state agreement, cache on/off exact-cost agreement, V1/V5 common exact-state tables equal.
- PASS: V2 changes selection only; V4 retains incumbent updates and live QMF threshold while disabling scheduling feedback.
- PASS: all 6,000 complete runs legal and exact-optimal, independently evaluated by the frozen oracle.
- PASS: actual repeated cache-off state computations count separately; Cache_Hits=0 for every V3 run.
- PASS: all final regrets recalculated from the same offline root-conditioned references, ties included, no negative regrets.
- PASS: common per-node budgets, complete timing boundaries, pre-deadline returned incumbent timestamps verified in every run.
- PASS: summaries independently regenerated from 12,000 immutable JSONs; raw SHA256 ledger saved.
- PASS: node-level means, standard deviations, 95% bootstrap CIs, paired effects, dataset/overall counts saved.
- OBSERVED: budget decision failures {json.dumps(missing)}; no fabricated zero regrets. Regret coverage is explicit.
- PENDING EXTERNAL CHECK: paper compilation, new-table width, original figure preservation and final PDF review are recorded separately in PAPER_BUILD_VALIDATION.md.

Protocol: `ABLATION_PROTOCOL.md`. Inputs and references: `01_audit/REUSED_INPUTS.csv`. Per-combination historical reuse exclusions: `01_audit/REUSE_RECORDS.csv`. Pilot: `01_audit/PILOT_PASS.json`. Machine-readable final validation: `04_metrics/VALIDATION.json`.
'''
    (ROOT/'06_reports/ABLATION_VALIDATION.md').write_text(validation_report)
    print(overview);print('Analysis words:',count)
if __name__=='__main__':main()
