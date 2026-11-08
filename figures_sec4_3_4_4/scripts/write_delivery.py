"""Generate independent manuscript replacements and evidence-scoped reports."""
from pathlib import Path
import json,hashlib,io
import pandas as pd
import numpy as np
OUT=Path(__file__).resolve().parents[1]
P4=OUT.parent.parent/'Q-COST-QMF-Necessity-Study/phase4_complementarity_analysis'
NAMES=['fig10_decision_ablation','fig11_budgeted_search_quality','fig12_optimization_efficiency','fig13_hybrid_effectiveness']
CAPTIONS={
NAMES[0]:r'''Controlled decision ablation. (a) Mean query latency on 20K-point samples, with 95\% Student-$t$ intervals across five independent builds. Analytic QMF denotes the original full-table Q-COST builder. (b) Optimal submitted roots in the retained, method-specific diagnostics; labels give successful/total decisions. The populations are unpaired, and one infeasible R4 completion remains in its denominator.''',
NAMES[1]:r'''Budgeted configuration search quality on 40 H3/K4 nodes. Analytic QMF and Random Search use 30 seeds per node; deterministic Beam Search uses one run per node. Error bars are 95\% node-bootstrap intervals after averaging seeds within each node. $B$ is the recorded selection budget for QMF/Random and width for Beam, not a common wall-clock budget. Dotted lines denote unconstrained Recursive Exact and Exact Enumeration references.''',
NAMES[2]:r'''Configuration optimization efficiency. (a) Fresh full-pipeline wall-clock time on 40 nodes with three seeds, including candidate preparation, evaluation, cache and scheduling work. (b) Historical measured phase sums on the same 40 node identities at $B(N)=\min\{N,\lceil2\sqrt{N}\rceil\}$, plus unconstrained exact references. Preparation is shared across seeds; QMF sorting is included once in selection, and Beam-trie construction is in other overhead. The two panels are separate timing campaigns. Error bars are 95\% node-bootstrap intervals.''',
NAMES[3]:r'''Hybrid optimization effectiveness. (a) Returned-root optimality under real deadlines on eight H3/K4 nodes with three seeds; unavailable decisions count as failures. Time is normalized by frozen per-node Exact median times. The dashed Exact curve uses only availability at its blocking return, projected from completed pilot runs, not early interruption or discovery. (b) Complete wall-clock time on 40 nodes with three seeds. (c) Identical recursive scheduling with cache on/off, normalized to cache off. (d) Hybrid-QMF with/without feedback, normalized to no feedback. Panels (c,d) use eight paired nodes and three seeds; intervals resample nodes, with paired ratios for (c,d).'''}

def write():
    text=r'''% Independent replacements for 4.3 and 4.4. Original manuscript is not edited.
% Figures are numbered by their natural insertion order; no counter override.
% Use paths relative to the main manuscript after copying the PDFs to figure/.
\subsection{Ablation Study}
\label{sec:ablation}

Figure~\ref{fig:qcost_10} compares four root-only construction strategies under
the retained 20K controlled protocol. The Analytic QMF curve identifies the
original Q-COST builder; Hybrid-QMF is evaluated separately in
Figure~\ref{fig:qcost_13}. Query-latency means and intervals use five independent
builds per method and dataset.
% 图10保留20K受控实验的四种根提交构建策略。Analytic QMF明确表示原Q-COST构建器；新版Hybrid-QMF另见图13。查询延迟统计以每方法、每数据集五次独立构建为单位。

Analytic QMF submits an optimal root in 138/142 diagnostic records (97.18\%),
compared with 14/27 (51.85\%) for R4 Greedy, 15/26 (57.69\%) for Cost-H1, and
29/29 (100\%) for Recursive Exact. These method-specific populations describe
observed decision quality, not a paired causal comparison. Mean query latency
is 0.02627, 0.02582, 0.02628, and 0.02723 ms for the Analytic QMF builder on
GeoLife, Gowalla, NYC Taxi, and Skewed 2D, respectively; the intervals overlap
substantially across construction strategies.
% 原Analytic QMF的最优根记录为138/142（97.18%）；R4为14/27，Cost-H1为15/26，递归精确为29/29。诊断来自各自构建树，不是配对因果比较。四数据集平均延迟依次为0.02627、0.02582、0.02628、0.02723 ms，各构建策略区间明显重叠。
'''
    def figure(i):
        n=NAMES[i];number=i+10;env='figure' if i==0 else 'figure*';width=r'\columnwidth' if i==0 else r'\textwidth'
        return '\n\\begin{'+env+'}[t]\n    \\centering\n    \\includegraphics[width='+width+']{figure/'+n+'.pdf}\n    \\caption{'+CAPTIONS[n]+'}\n    \\label{fig:qcost_'+str(number)+'}\n\\end{'+env+'}\n'
    text+=figure(0)
    text+=r'''
\subsection{Search Quality and Computational Efficiency}
\label{sec:search_efficiency}

Figure~\ref{fig:qcost_11} evaluates selection quality on 40 fixed H3/K4 node
problems. Original Analytic QMF and Random Search use 30 seeds per node, whereas
Beam Search is deterministic. At the per-node reference budget
$B(N)=\min\{N,\lceil2\sqrt{N}\rceil\}$, Analytic QMF attains 65.42\%
configuration optimality and 95.08\% root optimality, compared with
46.92\% and 89.33\% for Random Search. Its mean root regret is 3.471,
versus 11.788 for Random Search and 64.160 for Beam Search.
% 图11基于固定40个H3/K4节点，随机方法每节点30种子，Beam为确定性方法。逐节点参考预算下，原Analytic QMF配置/根最优率为65.42%/95.08%，Random为46.92%/89.33%；平均根遗憾为3.471、11.788和64.160。

Increasing the nominal budget to 512 raises Analytic QMF's configuration and
root optimality to 94.75\% and 99.67\%, respectively. These results characterize
selection over the original precomputed cost table. Beam uses the nominal
budget as its width; equal labels therefore do not imply equal computation.
Recursive Exact and Exact Enumeration supply the unconstrained optimum.
% 名义预算512时，原Analytic QMF的配置/根最优率为94.75%/99.67%。这些结果评价已物化成本表上的选择质量；Beam的同名预算为宽度，不代表相同计算工作。两种精确方法仅提供无预算约束的最优参考。
'''+figure(1)
    text+=r'''
Figure~\ref{fig:qcost_12} separates end-to-end node optimization from historical
phase-sum accounting. In the fresh 40-node campaign, Hybrid-QMF takes 0.3644 s
on average, reducing time by 13.96\% relative to Original Analytic QMF
(0.4235 s), while attaining 100\% final root optimality versus 98.33\%.
Original Recursive Exact, Cached Anytime Recursive, and Hybrid-BestFirst take
0.3754, 0.3337, and 0.3600 s, respectively. The node-paired Hybrid--Exact time
difference has a 95\% interval of $[-28.31,6.62]$ ms.
% 新40节点批次中Hybrid平均0.3644秒，相比旧Analytic QMF的0.4235秒减少13.96%；最终根最优率为100%对98.33%。Exact、Cached Anytime、BestFirst分别为0.3754、0.3337、0.3600秒。Hybrid减Exact的节点配对时间差95%区间为[-28.31,6.62]毫秒。

Historical phase sums are 0.4250 s for Analytic QMF, 0.4227 s for Random
Search, 0.4543 s for Beam Search, and 0.3554 s for Recursive Exact.
Analytic QMF selection accounts for only 2.372 ms, including sorting;
cost-table evaluation accounts for 42.513 ms, compared with 2.773 ms for
Recursive Exact. Conditional decomposition and preparation costs therefore
remain central to CPU optimization efficiency.
% 历史阶段合计中Analytic QMF、Random、Beam及Exact分别为0.4250、0.4227、0.4543、0.3554秒。QMF选择含排序仅2.372毫秒；成本评价42.513毫秒，而Exact为2.773毫秒，体现条件分解及准备开销的重要性。
'''+figure(2)
    text+=r'''
Figure~\ref{fig:qcost_13} evaluates budgeted return quality and the shared-cache
and feedback mechanisms. At $0.5T_{\mathrm{exact}}$ on the eight pilot nodes,
Hybrid-QMF returns an optimal root in 75.00\% of runs, compared with 58.33\%
for Cached Anytime, 66.67\% without feedback, and 87.50\% for Hybrid-BestFirst.
At $T_{\mathrm{exact}}$, these rates are 91.67\%, 87.50\%, 95.83\%, and
100\%, respectively. The denominator includes every scheduled run, including
those without a feasible incumbent; these are deadline-output rates, not
cumulative discovery rates.
% 八节点实际截止试验在0.5倍Exact时间下，Hybrid、Cached、无反馈和BestFirst最优根率分别75.00%、58.33%、66.67%、87.50%；1.0倍时分别91.67%、87.50%、95.83%、100%。分母包含无可行解的全部计划运行，指标是截止输出而非累计发现率。

With identical recursive scheduling, the cache reduces completed exact-state
evaluations by 12.71\% and terminal-cost computations by 15.43\%; the mean
wall-clock reduction is 0.52\%. Feedback changes all 24 paired execution
orders, but full Hybrid-QMF evaluation uses 5.32\% more completed exact states,
3.65\% more terminal computations, and 6.13\% more time than its no-feedback
variant in this ablation. The evidence supports reusable computation and
budget-dependent scheduling effects, while Cached Anytime and BestFirst
remain strong alternatives.
% 相同递归调度下，缓存减少12.71%的精确状态完成数、15.43%的终端计算，墙钟均值减少0.52%。反馈改变24/24配对执行顺序，但完整求解相对无反馈增加5.32%状态、3.65%终端计算和6.13%时间。结果支持计算复用及预算相关调度作用，Cached和BestFirst仍是强对照。
'''+figure(3)
    (OUT/'latex/section4_3_4_4_revised.tex').write_text(text)
    (OUT/'latex/figure_captions.json').write_text(json.dumps(CAPTIONS,indent=2))
    (OUT/'latex/figure_insertion_code.tex').write_text(''.join(figure(i) for i in range(4)))
    method_rows=[
        ('R4 Greedy','r4_greedy','Figure10 original controlled cohort','scorer-only root selection'),
        ('Cost-H1','cost_h1','Figure10 original controlled cohort','one-level cost selection'),
        ('Original Recursive Exact','recursive_exact_h3 / EXACT / M1','version and campaign retained per row','additive conditional exact solver'),
        ('Original Analytic QMF','cpu_qmf_h3 / CPU Analytic QMF / QMF','Figures10–12 old implementation','full configuration cost table, sorting, CPU analytic sampling'),
        ('Cached Anytime Recursive','M3','Phase2/3/4 incremental implementation','cache ON, recursive schedule, feedback OFF'),
        ('Hybrid-QMF','M8','Phase2/3/4 incremental implementation','cache ON, qmf frontier operator, feedback ON'),
        ('Hybrid-QMF-NoFeedback','M7','Phase4 matched ablation','cache ON, qmf frontier operator, feedback OFF'),
        ('Hybrid-BestFirst','M6','Phase3/4','cache ON, best-first frontier, feedback ON'),
        ('Anytime Recursive (cache off)','M2','Phase4 paired cache ablation','cache OFF, recursive schedule, feedback OFF'),
        ('Hybrid-NoCache','NOT FOUND','no plotted result','M2 is NOT relabeled as Hybrid-NoCache'),
        ('Random Search','Random Search','original table campaign','distinct complete-cost reads'),
        ('Beam Search','Beam Search','original table campaign','deterministic; B is width'),
        ('Exact Enumeration','Exact Enumeration','historical exact campaign','complete enumeration reference')]
    pd.DataFrame(method_rows,columns=['display_method','source_id','campaign','mechanism']).to_csv(OUT/'data/method_version_mapping.csv',index=False)
    method_md='\n'.join('| '+' | '.join(row)+' |' for row in method_rows)
    (OUT/'reports/method_version_audit.md').write_text('''# 方法及实现版本审计

| 显示方法 | 原始标识 | 记录范围 | 真实机制 |
|---|---|---|---|
'''+method_md+'''

短图例 `Analytic QMF` 仅是 `Original Analytic QMF` 的显示缩写；没有把旧QMF改名为Hybrid或用红色Hybrid身份展示。
Figure10使用允许的历史回退方案：四方法同批20K实验、五次独立构建、224条方法各自的根诊断。
新Hybrid与R4/Cost-H1缺少同批构建对照及全体提交根的离线最优诊断，不能拼接其他campaign。
Phase3 build.json可验证实际root提交；这些提交不自动构成最优性诊断，因为完整离线F_H(a)未覆盖全部构建状态。
Figure10因单栏14.5pt标题需要空间，使用2×1排列，而不是缩小标题。

Phase4 comparison_adapter源码确认Original QMF先物化配置、计算全表、初始化排序，再采样。
Hybrid M8按需展开条件状态，共享cache/当前可行解，反馈影响后续计算优先级。M7只关闭反馈。
M2/M3才是已完成的匹配缓存开关实验；C_STATE_OFF/C_TERM_OFF/C_CONFIG_OFF均基于M3，不是Hybrid-NoCache。

颜色按本次指定执行：Exact深蓝、Cached青绿、Analytic棕色、Hybrid红色、BestFirst浅蓝、NoFeedback橙色。
4.2中的字体、轴线、边距测量、导出规则原样继承；4.2的文件未修改。
''')
    (OUT/'reports/missing_results.md').write_text('''# 缺失结果及采用的处理

- 新Hybrid-QMF、R4 Greedy、Cost-H1、Recursive Exact的同批20K四策略构建及root诊断：未找到。Figure10保留原始四策略消融，明确标为Analytic QMF；不使用138/142冒充Hybrid。
- Phase3新Hybrid 20K：已找到每数据集5次独立构建（共20次M8；五方法总100次）。最新resume汇总补齐旧95行，未重复合并。
- Phase2新Hybrid 50K：已找到四数据集、每方法单一独立seed11。每索引5轮查询不是5次构建；不生成5-build CI。
- 同批Hybrid 50K五独立构建：未找到；不能与Phase2单seed混计。
- 40节点×3seed实际截止试验：未找到；Phase4真实截止是8节点×3seed。40节点720次记录是完整轨迹，不是实际中断。
- 原Exact无原生anytime提前返回。Figure13(a)保留相同8节点完整pilot的实际API返回可用性投影，蓝虚线明确说明；未将内部首次发现提前当输出。
- Hybrid-NoCache独立实测：未找到。使用真实M2/M3同递归调度cache对照，不改方法名称。
- 当前Phase4没有重新测Random/Beam/Enumeration完整墙钟。Figure12(b)单独呈现历史阶段合计，不能与(a)跨批计算加速。
- 完整正式Q-COST主LaTeX：没有找到。只能核验独立替换文件内label和引用；实际10–13编号须由全文自然插入顺序确认。

本轮没有补跑实验、没有训练/查询/索引构建，没有用模拟数据补齐任何项目。
''')
    # Supplemental H4 observation-sensitivity evidence, retained separately.
    provenance=pd.read_csv(OUT/'data/provenance.csv');extra=[]
    for name in ['H4_LOW_OBSERVER_SENSITIVITY.csv','H4_LOW_OBSERVER_PAIRED.csv','paired_node_differences.csv']:
        p=P4/'tables/final_v1'/name;b=p.read_bytes();(OUT/'data'/('phase4_'+name)).write_bytes(b)
        extra.append(dict(source_file=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),mtime_ns=p.stat().st_mtime_ns))
    pd.concat([provenance,pd.DataFrame(extra)],ignore_index=True).drop_duplicates('source_file').to_csv(OUT/'data/provenance.csv',index=False)
    (OUT/'reports/data_audit.md').write_text('''# 4.3–4.4 数据审计

## 来源与保护
扫描QMF、Mthod，并沿已有来源追溯至QMF-Core-Ablation、QMF-Motivation-Study和Q-COST-QMF-Necessity-Study。
source_file_inventory.csv记录22,025个候选文件。内部实验无需跨系统基线，不混入Mthod的亿级系统计时。
原绘图脚本已备份于archive/original_plot_scripts.zip；在新目录中修改副本。全部读取路径、SHA256见data/provenance.csv。
源码审计只读，不import求解器或实验runner。extract_results.py只使用文件读取和统计计算。

## Figure10 / Table III
历史160条独立构建覆盖20K/50K、四数据集、四方法、五seed，保留全部记录。
图10的80个20K构建均重新读取15,000条查询时间核验均值，所有已有正确性状态为COUNT_AND_ID_SET_PASS。
CI以5次独立构建均值计算Student-t(df=4)，没有把15,000个查询当独立构建。
Root诊断224条、无重复键，四方法为14/27、15/26、29/29、138/142；R4一个不可行H3补全不赋零遗憾，但保留分母。
诊断是各方法构建树产生的不等总体，柱顶显示完整分子/分母，不添加不成立的配对CI。
新版Hybrid的20K 5-build、50K单seed数据存在，但没有同批R4/Cost-H1和完整root诊断，故Figure10明确使用原Analytic QMF。
scalability_results_for_later.csv共292条构建记录：原160、Phase3最新100、Phase2 pilot32。
其中campaign、original_method_name、algorithm_version、preferred_for_later保留区别。20K优先新Phase3；50K只有新Phase2单seed，不能混合历史与新查询内核计时。

## Figure11
直接读取motivation3_budget_trials.csv，排除三额外GeoLife reproduction节点后保留40主节点。
每个预算QMF/Random各1200行，Beam40行；Beam确定性不复制成30seed。
五固定预算+2sqrtN参考；名义预算实际含义依方法保留，不能解释为等墙钟。
种子先在节点内平均，再以节点bootstrap，4000次、seed20261015，与原图协议一致。
官方参考预算QMF配置65.416667%、根95.083333%；Random46.916667%/89.333333%；Beam45%/77.5%。
Figure11补入原图未绘制的Beam，四个质量指标均来自同一原始记录。
100%/零线是无约束精确参考，没有将同一精确解重复计成各预算下的测量试验。

## Figure12
(a) Phase4 40节点×3seed完整运行，6方法原始JSON均核查offline reference只能在运行后使用；图中五主要方法。
实际全墙钟包含R4准备、条件展开、代价、cache、搜索、incumbent维护。模型加载/输入IO是节点试验的共同前置条件，不是此timer；完整索引构建另计。
(b) 历史40节点阶段合计：共享准备仅计一次，QMF排序在Selection中，BeamTrie计Other。
Exact阶段来自同节点总耗时中位那一次原始记录，所有分项来自同次运行。
搜索汇总中的Recursive Exact H3记录使用各阶段独立中位，分项不严格相加；正式分解不使用这些行，而读取motivation2_runtime原配对记录。
两批时间不混合排序、不跨批计算加速比。历史所有五方法及新Hybrid/Cached/BestFirst已覆盖。
Phase4原始各互斥阶段总和与total逐次一致；额外阶段数据保存在current_phase_summary.csv供核对。

## Figure13
(a)实际8节点×3seed、5个deadline档位，M3/M6/M7/M8；最优率分母含无可行解。
原Exact使用相同pilot节点/seed的实际阻塞返回时间作可用性投影；没有伪装成可中断算法，没有复用Fig3的累计发现曲线。
T_exact是冻结Phase3逐节点中位数，非本轮Phase4完成时间；因此归一化1.0不保证原Exact已返回。
(b)全40节点×3seed完整时间；与(a)样本范围不同，caption明确。
(c,d)同一component_ablation批次8节点×3seed，cache对照为M2/M3，feedback为M7/M8。
ratio使用节点均值之比，CI共同重采样配对节点，2000次、seed20261020。对照自身ratio=1，区间零宽。
缓存精确状态减少12.705061%、终端减少15.434634%；时间仅减少0.522912%，CI跨无差异。
反馈改变24/24顺序，但完整求解状态增加5.316386%、终端增加3.647124%、时间增加6.129200%。不隐藏负向结果。
未找到Hybrid-NoCache；不能把M2冒称为Hybrid-NoCache。
H4K4既有4根×3seed×3预算已单独整理。0.25档Hybrid根最优83.33%、Cached50%、BestFirst75%；样本仅4节点。
另保留低观察开销敏感性：0.5档Cached从83.33%变为100%，与Hybrid持平。不将观察开销敏感的H4现象写成普遍优势。

## 文本及编号
section4_3_4_4_revised.tex只含两个目标小节及四幅图，不含表环境或旧Table引用。
原Table III数据保留待Scalability使用，未修改后续图；Table IV的质量进图11、成本进图12。
正式源文件只读、未覆盖。完整主LaTeX缺失，因此全局图号未被冒称验证；独立预览自然从1编号，不使用setcounter强制10–13。
''')
    (OUT/'reports/paper_change_notes.md').write_text('''# 论文集成说明

1. 用latex/section4_3_4_4_revised.tex替换两个对应小节，保留两个原章节标题。
2. 替换文件没有Table III/IV环境或旧表引用；原文的这些表环境应在集成时移除。未直接修改正式源文件。
3. 复制四PDF至论文figure/，保留fig:qcost_10、11、12、13 label。
4. 短图例Analytic QMF是原Q-COST analytic构建器，不能将Fig10改称新版Hybrid实证。
5. 本地仅发现分图片段和方法建议，未找到完整主稿。最终编号取决于此前九幅图顺序，本交付不强行修改计数器。
6. 4.5及后续没有改动；scalability_results_for_later.csv保留各实验版本，后续绘图不可跨campaign直接合并。
''')
    (OUT/'README.md').write_text('''# Q-COST Figures 10–13

四幅图来自已有测量；没有运行任何实验或更改原数据。

- Figure10：单栏2×1，原始20K四策略配对构建均值/95%t区间及不配对root诊断。原Q-COST明确名为Analytic QMF，未冒充新版Hybrid。
- Figure11：双栏2×2，原Analytic QMF/Random/Beam五名义预算下的配置/根质量；节点bootstrap。
- Figure12：双栏1×2，Phase4实际墙钟与历史阶段堆叠分开，覆盖所有指定成本基线。
- Figure13：双栏2×2，真实预算输出、完整时间、匹配cache和feedback消融；保留Cached/BestFirst/NoFeedback。

PDF/SVG为矢量，PNG600dpi。所有12个子图标题14.5pt加粗单行居中、位于下方。
输入来源及SHA见data/provenance.csv；原脚本备份archive/original_plot_scripts.zip。
新Hybrid20K五build、50K单seed已保留在data/scalability_results_for_later.csv，与旧160build分campaign。

运行 `bash reproduce.sh` 仅重提取已有记录、绘图及核验。已有输出会先归档。
独立论文替换代码见latex/section4_3_4_4_revised.tex；说明见reports/data_audit.md和method_version_audit.md。
''')

if __name__=='__main__':write()
