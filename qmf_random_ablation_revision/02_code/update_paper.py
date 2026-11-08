"""Generate the measured five-row table and update only the current ablation block."""
from pathlib import Path
import pandas as pd,json,re,difflib
R=Path(__file__).resolve().parents[1]
NAMES=['Full Hybrid-QMF','w/o QMF Selection','w/o Shared Cache','w/o Incumbent Feedback','w/o Recursive Decomposition']
def main():
    validation=json.loads((R/'04_metrics/VALIDATION.json').read_text());assert validation['Status']=='PASS' and validation['New_Runs']==2400
    s=pd.read_csv(R/'QMF_RANDOM_ABLATION_SUMMARY.csv').set_index('Variant').loc[NAMES]
    p=pd.read_csv(R/'04_metrics/PAIRED_DIFFERENCES.csv');p=p[p.Variant.eq(NAMES[1])].set_index('Metric')
    common=pd.read_csv(R/'04_metrics/FULL_RANDOM_COMMON_FEASIBLE_REGRET.csv').set_index('Variant')
    calibration=pd.read_csv(R/'04_metrics/CALIBRATION_SUMMARY.csv').set_index('Campaign')
    full=s.loc[NAMES[0]];random=s.loc[NAMES[1]]
    table=[r'\begin{table}[t]',r'\centering',r'\caption{Ablation Study of Hybrid-QMF Components}',
           r'\label{tab:qcost_hybrid_ablation}',r'\footnotesize',r'\setlength{\tabcolsep}{2.3pt}',
           r'\begin{tabular}{@{}lrrrr@{}}',r'\toprule',
           r'Variant & Root (\%)$\uparrow$ & Regret$\downarrow$ & Time (s)$\downarrow$ & States$\downarrow$ \\',r'\midrule']
    for name,row in s.iterrows():
        label={NAMES[3]:r'\shortstack[l]{w/o Incumbent\\Feedback}',NAMES[4]:r'\shortstack[l]{w/o Recursive\\Decomposition}'}.get(name,name)
        table.append(f'{label} & {row.Optimal_Root_Rate:.2f} & {row.Mean_Root_Regret:.2f} & {row.Mean_Optimization_Time:.4f} & {row.Mean_Exact_States:.1f} '+r'\\')
    counts=', '.join(str(int(x)) for x in s.Feasible_Runs_A)
    coverage=('the same '+str(int(full.Regret_Valid_Nodes))+' nodes' if validation['Regret_Coverage_Identical'] else
              ', '.join(str(int(x)) for x in s.Regret_Valid_Nodes)+' nodes, respectively')
    table += [r'\bottomrule',r'\end{tabular}',r'\par\vspace{2pt}',r'\parbox{\columnwidth}{\scriptsize',
        r'Root and regret: $0.5T_{\mathrm{exact}}$; time and exact states: complete optimization. '
        r'Four datasets, 40 fixed nodes, 30 paired seeds per node. Unavailable roots count as failures. '
        f'Regret averages feasible returns within nodes, then across {coverage}. '
        f'Feasible returns in row order: {counts}, each out of 1,200. '
        f'Paired Full/Random regret uses {int(common.iloc[0].Common_Seed_Units):,} common returns on {int(common.iloc[0].Common_Nodes)} nodes. '
        r'The selection ablation uses uniform random frontier selection. '
        r'Random is measured in a later batch with the same environment; separate Full controls assess batch drift.}',r'\end{table}']
    table='\n'.join(table)+'\n';(R/'ABLATION_TABLE_FIVE_VARIANTS.tex').write_text(table)
    root=p.loc['Optimal_Root_Rate'];delta=-root.Delta_Ablated_Minus_Full;lo=-root.CI95_High;hi=-root.CI95_Low
    cache=100*(1-full.Mean_Exact_States/s.loc[NAMES[2]].Mean_Exact_States)
    enum=s.loc[NAMES[4]].Mean_Optimization_Time/full.Mean_Optimization_Time
    regret_interval=p.loc['Mean_Root_Regret']
    uncertainty=('Both root-rate and paired regret intervals include zero. ' if lo<=0<=hi and regret_interval.CI95_Low<=0<=regret_interval.CI95_High else 'The root-rate interval includes zero. ' if lo<=0<=hi else '')
    para=(r'Table~\ref{tab:qcost_hybrid_ablation} isolates the selection, cache, feedback, and recursive components. '
          r'The w/o QMF Selection variant replaces QMF-inspired frontier selection with random frontier selection, '
          r'retaining recursive exact evaluation, shared caches, and incumbent feedback. '
          r'We use 40 fixed $H=3$, $K=4$ nodes and 30 paired seeds per node across four datasets. '
          f'The Full-minus-Random optimal-root difference is ${delta:+.2f}$ percentage points '
          f'(paired 95\\% interval $[{lo:+.2f},{hi:+.2f}]$). '+uncertainty+
          f'On common feasible pairs, mean root regret is {common.loc[NAMES[0]].Mean_Root_Regret:.2f} for Full '
          f'and {common.loc[NAMES[1]].Mean_Root_Regret:.2f} for Random. '
          f'Complete times are {full.Mean_Optimization_Time:.4f} and {random.Mean_Optimization_Time:.4f} s, '
          f'with {full.Mean_Exact_States:.1f} and {random.Mean_Exact_States:.1f} exact-state evaluations, respectively. '
          f'Separate same-session controls instead take {calibration.loc["Contemporaneous Full"].Mean_Optimization_Time:.4f} and '
          f'{calibration.loc["Contemporaneous Random (same 3 seeds)"].Mean_Optimization_Time:.4f} s, so the cross-batch time difference does not isolate selector cost. '
          f'Shared caching reduces exact computations by {cache:.2f}\\%. '
          f'Disabling feedback yields {s.loc[NAMES[3]].Optimal_Root_Rate:.2f}\\% optimal roots and '
          f'{s.loc[NAMES[3]].Mean_Optimization_Time:.4f} s, retaining the live threshold and best feasible return. '
          f'Direct enumeration requires {enum:.2f}'+r'$\times$ Full\textquotesingle s complete time. '
          r'All complete runs recover exact optima. These wall-clock experiments are distinct from '
          r'Figure~\ref{fig:qcost_11}\textquotesingle s standalone configuration-selection budgets.')
    # Avoid adding package dependencies for apostrophes.
    para=para.replace(r'Full\textquotesingle s',"Full's").replace(r'\textquotesingle s',"'s")
    zh=(f'% 表格消融选择、缓存、反馈和递归组件。w/o QMF Selection仅将QMF启发式前沿选择替换为均匀随机前沿选择，\n'
        f'% 保留递归精确求解、共享缓存和incumbent反馈。沿用四个数据集40个H=3、K=4节点及30个配对种子。\n'
        f'% Full相对Random的根动作最优率差为{delta:+.2f}个百分点，节点级配对95%区间[{lo:+.2f},{hi:+.2f}]。\n'
        f'% 共同可行配对上的Root Regret分别为{common.loc[NAMES[0]].Mean_Root_Regret:.2f}和{common.loc[NAMES[1]].Mean_Root_Regret:.2f}，不直接相减不同有效分母的主表均值。\n'
        f'% 完整优化时间分别为{full.Mean_Optimization_Time:.4f}、{random.Mean_Optimization_Time:.4f}秒，实际精确状态数为{full.Mean_Exact_States:.1f}、{random.Mean_Exact_States:.1f}。\n'
        f'% 根动作率和共同可行配对Regret的置信区间均包含零，不能宣称确定的搜索质量优势。\n'
        f'% 同期Full/Random校准时间为{calibration.loc["Contemporaneous Full"].Mean_Optimization_Time:.4f}、{calibration.loc["Contemporaneous Random (same 3 seeds)"].Mean_Optimization_Time:.4f}秒，跨批次时间差不能单独归因于选择器。\n'
        f'% 缓存减少{cache:.2f}%精确计算；关闭反馈的真实结果仍保留，其live阈值和最佳可行解更新不变。\n'
        f'% 直接枚举需Full的{enum:.2f}倍完整时间。所有完整运行均达Exact最优。图11为独立完整配置选择预算，不能与本次墙钟预算混用。\n'
        f'% Random属于同环境后续计时批次；同时期Full校准记录独立保存，不覆盖原有四行。')
    block='% BEGIN HYBRID-QMF CONTROLLED ABLATION\n'+table+'\n'+para+'\n\n'+zh+'\n% END HYBRID-QMF CONTROLLED ABLATION'
    baseline=(R/'01_audit/BASELINE_LATEST.tex').read_text();pat=r'% BEGIN HYBRID-QMF CONTROLLED ABLATION.*?% END HYBRID-QMF CONTROLLED ABLATION'
    original_block=re.search(pat,baseline,re.S).group()
    revised=baseline.replace(original_block,block)
    assert re.sub(pat,'BLOCK',baseline,flags=re.S)==re.sub(pat,'BLOCK',revised,flags=re.S)
    assert not re.search(r'Best[-_\s]?First',revised,re.I)
    (R/'05_latex/IEEE-conference-template-062824.tex').write_text(revised)
    (R/'05_latex/ABLATION_TABLE_FIVE_VARIANTS.tex').write_text(table)
    # Remove only the superseded table copy inside this new project; historical projects remain untouched.
    (R/'05_latex/ABLATION_TABLE_REVISED.tex').unlink(missing_ok=True)
    (R/'01_audit/MANUSCRIPT.diff').write_text(''.join(difflib.unified_diff(baseline.splitlines(True),revised.splitlines(True),fromfile='NoBestFirst-four-row.tex',tofile='Random-frontier-five-row.tex')))
    (R/'07_reports/ANALYSIS_EN_ZH.md').write_text(para+'\n\n'+zh+'\n')
    (R/'07_reports/MANUSCRIPT_CHANGE.json').write_text(json.dumps(dict(Before=original_block,After=block,Analysis_Words=len(para.split())),ensure_ascii=False,indent=2))
    print('Generated measured five-row table and ablation-only manuscript change; analysis words:',len(para.split()))
if __name__=='__main__':main()
