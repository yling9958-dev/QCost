"""Build the current submission copy from the backed-up latest TABLE-II source."""
from pathlib import Path
import re,difflib,json,shutil
R=Path(__file__).resolve().parents[1]
def main():
    original=(R/'01_audit/BASELINE_LATEST.tex').read_text();s=original;changes=[]
    def replace(old,new,why):
        nonlocal s
        assert old in s,why
        changes.append(dict(Reason=why,Before=old,After=new));s=s.replace(old,new)
    replace('Recursive Exact, Hybrid-BestFirst, and\nCached Anytime achieve mean optimization\ntimes of 0.3754, 0.3600, and 0.3337 s,\nrespectively, with 100\\% final root optimality.',
        'Recursive Exact and Cached Anytime achieve\nmean optimization times of 0.3754 and 0.3337 s,\nrespectively, with 100\\% final root optimality.',
        'IV-D-2: remove internal strategy time only; keep historical times unchanged')
    replace('% Recursive Exact、Hybrid-BestFirst\n% 和Cached Anytime的平均优化时间\n% 分别为0.3754、0.3600和0.3337秒，',
        '% Recursive Exact和Cached Anytime的平均优化时间\n% 分别为0.3754和0.3337秒，','Matching Chinese overhead comments')
    replace('Hybrid-BestFirst reaches 87.50\\%\nunder the same budget.\n','', 'IV-D-3: remove internal strategy historical budget comparison')
    replace('% 相同预算下，Hybrid-BestFirst\n% 的根动作最优率达到87.50%。\n','', 'Matching Chinese budget comments')
    replace('To examine the contribution of QMF-inspired\nselection to hybrid configuration optimization,',
        'To examine budgeted root decisions and\ncomputational reuse in hybrid optimization,','IV-D-3 scope: retained comparisons do not isolate selector contribution')
    replace('% 为分析QMF启发式选择\n% 在混合配置优化中的作用，',
        '% 为分析混合优化中的预算根动作决策\n% 与计算复用，','Matching Chinese scope')
    replace('These results highlight QMF-guided exploration\nand incumbent feedback in identifying\nhigh-quality root decisions under time budgets.',
        'These results characterize returned-root quality\nunder wall-clock budgets in the eight-node cohort.',
        'Limit historical budget conclusion to the actual eight-node cohort')
    replace('% 结果体现了QMF引导的配置探索\n% 和最佳解反馈在有限时间预算内\n% 发现高质量根动作的作用。',
        '% 这些结果刻画了8个节点上\n% 真实墙钟预算下返回根动作的质量。','Matching Chinese cohort conclusion')
    newpara=r'''Table~\ref{tab:qcost_hybrid_ablation} examines shared conditional-cost reuse, incumbent-guided scheduling, and recursive decomposition while retaining QMF-inspired selection in all four variants. We use 40 fixed $H=3$, $K=4$ nodes across the four datasets, with 30 paired seeds per node. Full Hybrid-QMF achieves 71.50\% optimal roots at $0.5T_{\mathrm{exact}}$ and requires 0.3813 s for complete optimization. Shared caching reduces exact-state computations by 20.64\% and complete time by 8.60\%. Disabling feedback yields 76.50\% optimal roots and 0.3514 s, showing that incumbent-guided scheduling provides no observed improvement in this cohort; the paired root-rate interval includes zero. This ablation retains the live incumbent threshold and best-known feasible return. Direct enumeration requires 1.86$\times$ the complete time and achieves 65.83\% optimal roots, quantifying the benefit of recursive minimization. All complete runs recover exact optima. These measurements form a separate campaign from Figure~\ref{fig:qcost_12}; Figure~\ref{fig:qcost_11} evaluates Analytic QMF under configuration-selection budgets rather than wall-clock limits.'''
    zh='''% 表格检验共享条件代价复用、最佳解反馈调度和递归分解，四个版本均保留QMF启发式选择。
% 使用四个数据集共40个固定H=3、K=4节点，每节点30个配对种子。
% 完整版本在0.5T_exact下根动作最优率为71.50%，完整优化时间为0.3813秒。
% 共享缓存将精确状态计算减少20.64%，完整时间减少8.60%。
% 关闭反馈后最优率为76.50%，时间为0.3514秒；该节点集合未观察到反馈调度的性能改善，
% 根动作率的节点级配对置信区间包含零。反馈消融仍保留实时incumbent阈值及最佳已知可行解。
% 直接枚举的完整时间为完整版本的1.86倍，根动作最优率为65.83%，量化递归最小化的计算作用。
% 全部完整运行均获得Exact最优解。本轮与图12属于独立计时批次。
% 图11分析Analytic QMF的配置选择预算，不能与墙钟预算直接等同。'''
    table=(R/'04_tables/ABLATION_TABLE_REVISED.tex').read_text()
    block='\n% BEGIN HYBRID-QMF CONTROLLED ABLATION\n'+table+'\n'+newpara+'\n\n'+zh+'\n% END HYBRID-QMF CONTROLLED ABLATION\n'
    old=re.search(r'\n% BEGIN HYBRID-QMF CONTROLLED ABLATION\n.*?% END HYBRID-QMF CONTROLLED ABLATION\n',s,re.S).group()
    replace(old,block,'Four-row component table; retain unfavorable feedback measurements; separate selector evidence/protocol')
    replace('We further evaluate the scalability of\nfour construction strategies on',
        'We further evaluate the scalability of\nRecursive Exact, Cached Anytime, and Q-COST on','IV-F: explicit retained three methods')
    replace('% 评价四种构建策略的可扩展性。','% 评价Recursive Exact、Cached Anytime和Q-COST三种构建策略的可扩展性。','Matching Chinese scale setup')
    replace('all four construction strategies pass the','all three construction strategies pass the','IV-F: verified retained correctness records only')
    replace('% 四种构建策略均通过1000条查询的','% 三种构建策略均通过1000条查询的','Matching Chinese correctness count')
    names={12:'fig12_configuration_efficiency',13:'fig13_hybrid_effectiveness',16:'fig16_index_scalability'}
    for n,name in names.items():
        replace(f'{{figure/{n}.pdf}}',f'{{figure/{name}.pdf}}',f'Figure {n}: regenerated vector PDF')
        shutil.copy2(R/'03_figures'/f'{name}.pdf',R/'05_latex/figure'/f'{name}.pdf')
        # Only the copied old affected figure is removed from the submission package.
        (R/'05_latex/figure'/f'{n}.pdf').unlink(missing_ok=True)
    assert not re.search(r'Best[-_\s]?First|w/o QMF Selection',s,re.I)
    assert original.count(r'\begin{figure}')==s.count(r'\begin{figure}')
    for env in ['equation','align','thebibliography']:
        pat=r'\\begin\{'+env+r'\}.*?\\end\{'+env+r'\}'
        assert re.findall(pat,original,re.S)==re.findall(pat,s,re.S),env
    figures=lambda t:re.findall(r'\\begin\{figure\}.*?\\end\{figure\}',t,re.S)
    for old,new in zip(figures(original),figures(s)):
        if not any('{figure/'+str(n)+'.pdf}' in old for n in names):assert old==new
    # All non-figure content outside IV-D and IV-F remains byte-identical, including IV-A's unrelated four decision strategies.
    (R/'05_latex/IEEE-conference-template-062824.tex').write_text(s)
    (R/'05_latex/ABLATION_TABLE_REVISED.tex').write_text(table)
    (R/'01_audit/MANUSCRIPT.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='latest-five-version.tex',tofile='submission-four-version.tex')))
    (R/'07_reports/MANUSCRIPT_CHANGES.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2))
    (R/'07_reports/REVISED_ANALYSIS_EN_ZH.md').write_text(newpara+'\n\n'+zh+'\n')
    print('Updated submission copy; original source unchanged; analysis words:',len(newpara.split()))
if __name__=='__main__':main()
