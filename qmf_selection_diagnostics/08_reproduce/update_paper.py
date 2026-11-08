"""Add validated Table III and a held-out selection figure; preserve Table II."""
from pathlib import Path
import json,re,difflib,shutil
import pandas as pd
R=Path(__file__).resolve().parents[1]
TABLE_METRICS=[('Optimal root (\\%)','Optimal_Root',.5,100,1),('Near-opt. 5\\% (\\%)','Near_5pct',.5,100,1),
 ('Norm. regret','Normalized_Regret',.5,1,3),('Anytime AUC','Anytime_AUC',1.,1,3),
 ('Optimal wait / $T_e$','Time_Optimal_Restricted_T',1.,1,3),('Useful eval. (\\%)','Useful_Evaluation_Ratio',1.,100,1)]
def main():
    v=json.loads((R/'03_metrics/VALIDATION.json').read_text());assert v['Status']=='PASS' and v['Trajectories']==9600
    independent=json.loads((R/'03_metrics/INDEPENDENT_METRIC_CHECK.json').read_text());assert independent['Status']=='PASS' and independent['Snapshots']==38400
    s=pd.read_csv(R/'03_metrics/QMF_SELECTION_METRICS.csv');s=s[s.Dataset.eq('Overall')]
    p=pd.read_csv(R/'03_metrics/QMF_PAIRED_STATISTICS.csv');p=p[p.Contrast.eq('QMF_with_Feedback')]
    def mean(co,method,metric,b):return s[s.Cohort.eq(co)&s.Method.eq(method)&s.Metric.eq(metric)&s.Budget_Ratio.eq(b)].iloc[0]
    def effect(co,metric,b):return p[p.Cohort.eq(co)&p.Metric.eq(metric)&p.Budget_Ratio.eq(b)].iloc[0]
    coverage=[]
    for co in ['Original','Validation']:
        a=mean(co,'QF','Normalized_Regret',.5);b=mean(co,'RF','Normalized_Regret',.5);c=effect(co,'Normalized_Regret',.5)
        coverage.append(f'{int(a.Valid_Runs)}/{int(b.Valid_Runs)} returns ({int(a.Nodes)}/{int(b.Nodes)} nodes; {int(c.Paired_Runs)} paired)')
    coverage_note='Regret QMF/Random coverage: original '+coverage[0]+', held-out '+coverage[1]+'. '
    primary_p_note='Holm-adjusted primary $p$ (root/AUC): '+', '.join(
        f"{label} {effect(co,'Optimal_Root',.5).Adjusted_P:.3f}/{effect(co,'Anytime_AUC',1.).Adjusted_P:.3f}"
        for co,label in [('Original','original'),('Validation','held-out')])+'. '
    lines=[r'\begin{table}[t]',r'\centering',r'\caption{QMF Selection Effectiveness}',r'\label{tab:qmf_selection_effectiveness}',
           r'\footnotesize',r'\setlength{\tabcolsep}{2.2pt}',r'\begin{tabular}{@{}lrrr@{}}',r'\toprule',
           r'Metric & QMF & Random & $\Delta$ [95\% CI] \\',r'\midrule']
    for co,label in [('Original','Original 40 nodes'),('Validation','Held-out 40 nodes')]:
        lines.append(r'\multicolumn{4}{l}{\textit{'+label+r'}} \\')
        for label,metric,b,scale,dec in TABLE_METRICS:
            a=mean(co,'QF',metric,b);c=mean(co,'RF',metric,b);d=effect(co,metric,b)
            fmt=lambda x:f'{x*scale:.{dec}f}'
            lines.append(f'{label} & {fmt(a.Mean)} & {fmt(c.Mean)} & {fmt(d.Mean_Difference)} [{fmt(d.CI95_Low)}, {fmt(d.CI95_High)}] '+r'\\')
        if co=='Original':lines.append(r'\midrule')
    lines += [r'\bottomrule',r'\end{tabular}',r'\par\vspace{2pt}',r'\parbox{\columnwidth}{\scriptsize',
        r'Both selectors retain feedback. $\Delta=$ QMF minus Random; intervals resample paired nodes, with 30 seeds per node. '
        r'Root/near-root/regret use $0.5T_e$; AUC, restricted optimal wait, and useful evaluations use $T_e=T_{\mathrm{exact}}$. '
        r'AUC integrates capped normalized best-so-far root regret, assigning loss 1 before feasibility. '
        r'Unhit optimal discoveries remain censored at $T_e$. Regret and useful-evaluation ratios use defined outcomes; paired effects use common valid runs. '
        +coverage_note+primary_p_note+r'Root rate and AUC are the two primary endpoints; other comparisons are exploratory.}',r'\end{table}']
    table='\n'.join(lines)+'\n';(R/'04_tables/QMF_SELECTION_TABLE.tex').write_text(table)
    root=effect('Validation','Optimal_Root',.5);auc=effect('Validation','Anytime_AUC',1.)
    original_root=effect('Original','Optimal_Root',.5);original_auc=effect('Original','Anytime_AUC',1.)
    significant=lambda a:a.Adjusted_P<.05
    replicated=[bool(significant(a) and significant(b) and a.Mean_Difference*b.Mean_Difference>0) for a,b in [(root,original_root),(auc,original_auc)]]
    if not any(replicated):conclusion='Neither primary endpoint provides replicated evidence of a directional selector advantage.'
    elif all(replicated):conclusion='Both primary effects retain their direction with Holm-adjusted support in the held-out cohort.'
    else:conclusion='Only one primary endpoint retains its direction with Holm-adjusted support in both cohorts.'
    para=(r'\textit{Selection-specific validation:} Table~\ref{tab:qmf_selection_effectiveness} compares fresh, event-instrumented QMF and uniform random frontier runs under identical wall-clock accounting, '
          r'including selector computation. We retain the original 40 nodes and freeze 40 previously unmeasured nodes, ten per dataset, before search outcomes. '
          r'Each node uses 30 paired seeds; Figure~\ref{fig:qmf_selection_diagnostics} reports the held-out trajectories. '
          f'On held-out nodes, QMF-minus-Random differences are {100*root.Mean_Difference:+.2f} percentage points in optimal-root rate '
          f'(95\\% CI [{100*root.CI95_Low:+.2f}, {100*root.CI95_High:+.2f}]) and {auc.Mean_Difference:+.3f} in anytime AUC '
          f'([{auc.CI95_Low:+.3f}, {auc.CI95_High:+.3f}]); their Holm-adjusted $p$-values are {root.Adjusted_P:.3f} and {auc.Adjusted_P:.3f}, respectively. '+conclusion+' '
          r'A separate $2\times2$ scheduling ablation, censoring records, coverage, and exploratory mechanism statistics accompany the reproducibility package. '
          r'These frontier-search budgets differ from Figure~\ref{fig:qcost_11}\textquotesingle s standalone configuration-selection budgets.')
    para=para.replace(r'\textquotesingle s',"'s")
    zh=(f'% 专项采用新一轮带事件记录的QMF与均匀随机前沿选择实验，墙钟计时包含实际选择开销。原40节点与搜索结果前冻结的独立40节点分别分析，\n'
        f'% 每数据集10个验证节点，每节点30个配对种子。独立节点上QMF减Random的最优根动作率差为{100*root.Mean_Difference:+.2f}个百分点，\n'
        f'% 配对95%区间[{100*root.CI95_Low:+.2f}, {100*root.CI95_High:+.2f}]；AUC差为{auc.Mean_Difference:+.3f}，区间[{auc.CI95_Low:+.3f}, {auc.CI95_High:+.3f}]。\n'
        f'% 验证组两个主终点的Holm校正p值分别为{root.Adjusted_P:.3f}和{auc.Adjusted_P:.3f}，检验结论不由未校正的区间单独决定。\n'
        f'% 两个主终点在原与独立节点同时获得同向Holm校正支持的标记为{replicated}；不预设QMF优势。\n'
        f'% 2×2反馈交互、删失、可行覆盖和探索性机制指标完整保存在复现包。本实验前沿墙钟预算不同于图11的独立完整配置选择预算。')
    figure=r'''\begin{figure}[t]
    \centering
    \includegraphics[width=\columnwidth]{figure/qmf_selection_validation.pdf}
    \caption{Hybrid frontier selection on 40 held-out nodes. Shading shows node-bootstrap 95\% intervals. Panel (b) uses feasible returns; panel (d) retains censored runs.}
    \label{fig:qmf_selection_diagnostics}
\end{figure}'''
    block='\n% BEGIN QMF SELECTION DIAGNOSTICS\n'+table+'\n'+para+'\n\n'+zh+'\n% END QMF SELECTION DIAGNOSTICS\n'
    figure_block='\n% BEGIN QMF SELECTION FIGURE\n'+figure+'\n% END QMF SELECTION FIGURE\n'
    original=(R/'01_code_audit/BASELINE_LATEST.tex').read_text()
    # Insertion after Figure 16 preserves automatic numbering of all historical figures.
    marker='\\section{Related Work}'
    if marker not in original:
        match=re.search(r'\\section\{[^}]*Related[^}]*\}',original);assert match;marker=match.group()
    ablation_end='% END HYBRID-QMF CONTROLLED ABLATION'
    assert original.count(ablation_end)==1
    revised=original.replace(ablation_end,ablation_end+block,1).replace(marker,figure_block+'\n'+marker,1)
    assert revised.replace(block,'',1).replace(figure_block+'\n','',1)==original
    assert not re.search(r'Best[-_\s]?First',revised,re.I)
    (R/'07_latex/IEEE-conference-template-062824.tex').write_text(revised)
    shutil.copy2(R/'05_figures/qmf_selection_validation.pdf',R/'07_latex/figure/qmf_selection_validation.pdf')
    (R/'07_latex/QMF_SELECTION_TABLE.tex').write_text(table)
    (R/'01_code_audit/MANUSCRIPT.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),revised.splitlines(True),fromfile='Random-ablation-baseline.tex',tofile='Selection-diagnostics.tex')))
    (R/'06_reports/ANALYSIS_EN_ZH.md').write_text(para+'\n\n'+zh+'\n')
    (R/'06_reports/PAPER_INSERTION.json').write_text(json.dumps(dict(Block=block,Figure_Block=figure_block,Primary_Replicated=replicated,Analysis_Words=len(para.split())),ensure_ascii=False,indent=2))
    print('Table III and Figure 17 inserted; Table II and old figures unchanged')
if __name__=='__main__':main()
