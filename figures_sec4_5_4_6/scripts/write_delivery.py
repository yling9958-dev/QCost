"""Write independent paper replacements and audits from verified derived data."""
from pathlib import Path
import json,hashlib,re
import pandas as pd
import numpy as np

OUT=Path(__file__).resolve().parents[1];BASE=OUT.parent.parent
NAMES=['fig14_gate_validation','fig15_parameter_sensitivity','fig16_index_scalability']
EXTRAS=['fig15_hybrid_h2_h4_candidate','fig16_20k_five_builds_supplement']
CAPTIONS=dict(zip(NAMES,['Gate-level quantum search validation.','Planning parameter sensitivity.','Index construction and query scalability.']))
CAPTIONS[EXTRAS[0]]='Matched Recursive Exact and Hybrid-QMF complete optimization on four fixed roots; H=2,3,4 and K=2,3,4, one seed. All 36 paired optima agree.'
CAPTIONS[EXTRAS[1]]='Independent 20K replication, separate from the two-size pilot. Bars show means and 95\% Student-$t$ intervals across five independent builds per method and dataset.'

def read(n):return pd.read_csv(OUT/'data'/n)
def write(folder,name,text):(OUT/folder/name).write_text(text,encoding='utf-8')
def figure(name,label):
    return ('\\begin{figure*}[t]\n    \\centering\n    \\includegraphics[width=\\textwidth]'
        '{figure/'+name+'.pdf}\n    \\caption{'+CAPTIONS[name]+'}\n    \\label{'+label+'}\n\\end{figure*}\n')

def main():
    receipt=json.loads((OUT/'reports/extraction_receipt.json').read_text())
    s=read('scalability_summary.csv');g=read('gate_validation_results.csv');c=read('circuit_complexity.csv')
    q=s[s.method=='Hybrid-QMF'].pivot(index='dataset',columns=['metric','points'],values='mean')
    order=['GeoLife','Gowalla','NYC Taxi','Skewed 2D'];q=q.loc[order]
    ratios=q['build_seconds'][50000]/q['build_seconds'][20000]
    f14,f15,f16=[figure(n,f'fig:qcost_{i}') for i,n in enumerate(NAMES,14)]
    text=r'''% Independent replacement for Sections 4.5 and 4.6; original manuscript unchanged.
% Figure numbers follow insertion order. Insert after the retained Figures 1--13.
\subsection{Gate-Level Quantum Search Validation}
\label{sec:gate_validation}

Figure~\ref{fig:qcost_14} compares analytical amplification probabilities with
recorded Qiskit Aer measurements for one marked address and a four-bit cost
register. The 13 $(N,j)$ configurations use $N\in\{4,8,16,32,64\}$, five simulator
seeds, and 2,048 shots per seed, totaling 133,120 shots. The marked set,
initialization, and iteration count are identical in each comparison.
% 图14比较单标记地址、4位成本寄存器下的解析放大概率与真实Aer测量。13组(N,j)采用五个种子、每种子2048 shots，总计133120 shots；两者使用相同标记集、初始化和迭代次数。

The maximum absolute deviation is 0.488 percentage points. For $(N,j)=(4,1)$,
both probabilities are 100\%; for $(16,2)$, the analytical and measured values
are 90.845\% and 91.143\%, and for $(64,5)$ they are 96.352\% and 96.162\%.
These measurements support the implemented threshold marking, uncomputation,
and diffusion on the controlled validation tables.
% 最大绝对偏差为0.488个百分点。三组代表条件的理论/测量值分别为100%/100%、90.845%/91.143%和96.352%/96.162%，支持受控验证表上的阈值标记、反计算及扩散实现。

Panel (b) reports recorded transpiled circuit depth, including measurement.
At $(64,5)$, the circuit uses 11 logical qubits, a depth of 100,643, and 112,837
$u$/CX gates; gate counts exclude measurement. Six- and eight-bit component
checks use separate circuit conditions and are retained separately. These
ideal CPU gate simulations validate component behavior and quantify circuit
resources; they do not measure quantum-hardware or database-system speedup.
% 子图(b)展示实际转译线路深度，包含测量。(64,5)使用11个逻辑比特、深度100643和112837个u/CX门，门数不含测量。6/8位组件检查单独保留。理想CPU门级模拟验证组件及资源开销，不代表量子硬件或数据库系统加速。

'''+f14+r'''
\subsection{Sensitivity and Scalability Analysis}
\label{sec:sensitivity_scalability}

\paragraph{Planning parameters.}
Figure~\ref{fig:qcost_15} evaluates Recursive Exact for all nine combinations
of $H\in\{1,2,3\}$ and $K\in\{2,3,4\}$. Cost reduction and optimization time use
the same 25 nodes feasible at every setting. Reduction is computed per node
against its $H=1,K=4$ cost; time is the mean of per-node repeat medians.
Feasible-node counts use the full set of 40 evaluated nodes.
% 图15评价Recursive Exact的全部9组H/K设置。成本降幅与时间使用同一25个共同可行节点；降幅相对同节点H1/K4，时间先取逐节点重复中位数再平均。可行节点数使用完整40节点总体。

At $H=3,K=4$, the proxy cost decreases by 48.48\% with a mean optimization time
of 0.401 s; $H=2,K=4$ obtains a 34.43\% decrease in 0.062 s. At $H=3$,
increasing $K$ from two to four raises feasibility from 25/40 to 40/40 nodes.
The $H=1$ reductions of $-2.55\%$ and $-0.67\%$ for $K=2$ and $K=3$ retain the
cost of removing candidate actions. These are surrogate-cost measurements
under exact optimization.
% H3/K4代理成本下降48.48%，平均优化时间0.401秒；H2/K4下降34.43%，时间0.062秒。H3下K从2增至4将可行数由25/40增至40/40。H1/K2、K3的-2.55%、-0.67%负降幅真实保留。这些指标属于精确优化的代理成本。

'''+f15+r'''
\paragraph{Index size scaling.}
Figure~\ref{fig:qcost_16} uses the matched Hybrid-era construction campaign at
20K and 50K points. Its completed methods are Recursive Exact, Cached Anytime
Recursive, Hybrid-BestFirst, and Q-COST, where Q-COST denotes Hybrid-QMF.
All methods share the scorer, partition rules, tree constraints, root-only
commitment, child replanning, and native C++ range-count kernel. Each cell
contains one independent build (seed 11), followed by five query rounds; the
separate five-build 20K replication is not pooled into this two-size comparison.
% 图16使用新版Hybrid时期同批20K/50K构建记录，已完成的方法是Exact、Cached Anytime、Hybrid-BestFirst和Q-COST（Hybrid-QMF）。评分器、划分规则、树约束、根提交、子节点重规划及原生C++计数内核一致。每组一个独立构建种子11、五轮查询；另存20K五构建复核，未拼接进两规模对比。

Q-COST construction time increases from 4.149 to 10.564 s on GeoLife, from
4.909 to 10.488 s on Gowalla, from 3.482 to 7.193 s on NYC Taxi, and from
3.727 to 11.666 s on Skewed 2D. For the $2.5\times$ increase in point count,
these are factors of 2.55, 2.14, 2.07, and 3.13. At 50K, Q-COST's mean query
latencies are 0.000206, 0.000239, 0.000216, and 0.001258 ms, respectively.
Within each paired dataset/size condition, the four methods produce identical
persisted indices. The query timings therefore characterize the same index
structures under repeated execution, rather than a structural query advantage.
% Q-COST四数据集构建时间20K→50K依次为4.149→10.564、4.909→10.488、3.482→7.193、3.727→11.666秒，数据量增加2.5倍时构建倍数为2.55、2.14、2.07、3.13。50K平均延迟分别为0.000206、0.000239、0.000216、0.001258毫秒。同数据集/规模下四方法持久化索引相同，时延变化不能解释为索引结构收益。

'''+f16
    write('latex','section4_5_4_6_revised.tex',text)
    write('latex','figure_insertion_code.tex','\n'.join([f14,f15,f16]))
    write('latex','figure_captions.json',json.dumps(CAPTIONS,indent=2))
    write('latex','supplementary_figures.tex',
       '% Optional supporting figures; not replacements for the primary cohorts.\n'+
       '\n'.join(figure(n,'fig:supp_'+str(i)) for i,n in enumerate(EXTRAS)))

    coverage=read('requested_scalability_coverage.csv')
    repeated_seeds='、'.join(map(str,sorted(read('hybrid_20k_five_build_results.csv').seed.unique())))
    paired=read('hybrid_parameter_matched_summary.csv')
    per_ds='\n'.join(f"| {ds} | {q.loc[ds,('build_seconds',20000)]:.6f} | {q.loc[ds,('build_seconds',50000)]:.6f} | {ratios[ds]:.3f} | {q.loc[ds,('mean_ms',20000)]:.9f} | {q.loc[ds,('mean_ms',50000)]:.9f} |" for ds in order)
    width_rows='\n'.join(f"| {r.N} | {r.bits} | {r.j} | {r.total_qubits} | {r.circuit_depth} | {r.gate_count} | {r.simulation_seconds:.6f} |" for r in c[c.bits.isin([6,8])].itertuples())
    audit=f'''# 数据审计：4.5与4.6

本轮只读取、复算及绘图，未运行量子模拟、数据库查询、索引构建、训练或优化实验。
扫描QMF、Mthod、Quantum-Circuit、Motivation-Study、Core-Ablation和Necessity-Study，记录26,655个相关文件的路径、大小与mtime。具体见source_file_inventory.csv和scan_counts.json。旧绘图脚本已归档，4.2与4.3/4.4图件保持不变。

## Figure14：完整主试验与资源口径

- 来源：QMF-Quantum-Circuit/results/stage_4、stage_8、stage_16、stage_32、stage_64_aer/result.json；逐项核对receipt的PASS状态。
- 4-bit主实验共13组(N,j)、65条独立种子测量，每组5种子20261009–20261013，每种子2048 shots；每组10240、合计133120 shots。`result.json`顶层另有20个minimum-finding种子，未误当作主振幅验证种子。
- 一标记地址N/2，均匀初始化；解析概率按原源码公式核验，测量值由日志中的整数命中数复算。没有生成任何模拟观测。
- 最大绝对偏差{receipt['gate']['max_deviation_pp']:.9f}个百分点，对应N=8,j=1。N=4,j=1为100%/100%；N=16,j=2为90.8447265625%/91.142578125%；N=64,j=5为96.351548...%/96.162109375%。
- 存在13条4-bit实际资源记录，以及10条6/8-bit资源记录。每配置的资源/编译/模拟耗时来自首个seed，不能解释为五种子平均。
- 线路深度是实际transpiled circuit.depth()，包含末尾measurement；u/CX门数排除measurement、barrier和save_statevector，门数和深度分别存储，不相加。
- 固定基础门u/CX、optimization_level=1、无硬件耦合图、理想Aer statevector。4-bit宽度7–11逻辑比特，深度2–100643；N64/j5门数112837、模拟3.144306秒（首seed）。j=0只有初始化与测量，不承担完整oracle调用成本。
- 6-bit与8-bit各5种N、j=1，每配置五个seed，共50条测量；单独保存，不合入133120 shots。资源明细如下。

| N | Cost bits | j | Qubits | Depth | Gate count | Aer seconds |
|---|---|---|---|---|---|---|
{width_rows}

这些组件记录不能推导量子硬件加速或数据库整体加速。

## Figure15：9组设置，两个明确总体

- 从motivation2_runtime.csv读取排除GeoLife reproduction后的40主节点，H=1/2/3、K=2/3/4，共880条原始计时记录，按节点/设置/方法/Repeat检查无重复。
- 在每个可行节点设置内，先取重复计时的中位数。341个共同可行节点设置的Enumeration与Recursive Exact最优成本一致。
- 9设置均可行的交集为25节点；逐节点相对自身H1/K4计算百分比降幅，再取节点均值，时间使用同一25节点。不是先平均成本再求百分比。
- Feasible nodes统计40节点，每设置一次。H3/K2、K3、K4分别25、36、40；其余6设置40。
- 与旧T17/原Table VI所有9行完全匹配（浮点容差1e-10）；负值-2.548931%、-0.666585%保留。
- H3/K4降幅48.481376%，平均节点中位时间0.400625秒；不能据此声称查询延迟下降48.48%。
- 找到新版Hybrid完整的另一组网格：Phase4四个固定根节点、seed11、H=2/3/4及K=2/3/4。72条Exact/M8记录与逐次JSON、离线参考SHA核对；36组配对成本全部一致且两者均完成精确求解。另出候选图fig15_hybrid_h2_h4_candidate，不能替换或混入25/40节点H=1/2/3研究。
- 所有Phase3/4网格记录（含其他方法、资源守卫NOT_RUN状态和H4 deadline试验）保留在独立CSV，未删除失败/未运行记录。候选图是完整求解时间，不是有限预算质量曲线。

## Figure16：新版Hybrid、同批比较及缺失方法

请求的R4 Greedy、Cost-H1、Exact、Hybrid四策略没有同协议完整20K/50K交集。历史R4/H1属于旧构建及查询执行campaign，不能拼接。正式候选图使用真实已完成且同批的Exact、Cached Anytime、Hybrid-BestFirst、Hybrid-QMF四方法；图例Q-COST只指M8 Hybrid。

- 主图来源Phase2 results/indexing/pilot_four_datasets/summary.csv：4数据集×2规模×4方法×seed11，共32次独立构建。
- 该campaign每cell只有1个build；5轮查询不能代替5次独立构建，因此主图无虚构CI。两规模采用同一campaign，未把Phase3五build20K均值接到Phase2单build50K上。
- 共享R4模型SHA、数据与查询SHA、native C++查询内核SHA；所有方法根提交与实际split一致。共同约束为最大128叶、深度8、最小子节点256点；4096点以下统一greedy回退；H3/K4联合规划、root-only commitment与child replanning沿用源码。
- build_seconds包含模型加载至compact序列化，排除输入文件加载；query延迟来自native C++计数计时，排除PostgreSQL/libpq流水线。旧实验约0.026ms与此处约0.0001ms之间不可计算跨版本加速。
- 每次构建验证15000条非负有限latency_ns、3000唯一query×5轮及1000条正确性记录；按1e6换算ms，复算mean与原metrics/summary一致。正确性记录的expected/count逐条一致。
- 8个数据集/规模配对条件下四方法index SHA全部相同，因此主图微小时延差不构成结构优势。重复执行噪声与缓存/系统状态可影响计时；本轮未重测这些因素。
- Phase3独立20K五build（seed{repeated_seeds}）已读取完整resume汇总，100次构建（5方法）没有与早期95行重复合并。单独输出fig16_20k_five_builds_supplement，按build均值计算95% Student-t区间（df=4），保留Original Analytic QMF额外对照。旧Analytic没有进入主Figure16。

Q-COST主图实际值：

| Dataset | Build20K(s) | Build50K(s) | Ratio | Mean20K(ms) | Mean50K(ms) |
|---|---|---|---|---|---|
{per_ds}

scalability_historical_and_new_inventory.csv保留上阶段整理的292条历史/新版构建记录以及原Table III指标，不合并不同campaign的CI。

## 溯源与可复现性

所有正式图读取data目录统一CSV；gate raw/result保留源JSON列表下标，runtime保留源CSV行号，build保留summary行号、metrics/build/latency路径、seed及哈希。provenance.csv记录实际读取源文件SHA。data_checks.csv当前通过{receipt['checks_passed']}项检查；最终完整性由check_delivery.py重新计算。
'''
    write('reports','data_audit.md',audit)
    write('reports','missing_results.md','''# 缺失与实际采用范围

1. **未找到新版Hybrid与R4 Greedy、Cost-H1同批的20K/50K四策略完整结果。** 不补齐、不改名、不拼接历史数据。Figure16当前候选使用同批已完成的Exact/Cached/BestFirst/Hybrid；需求覆盖表逐cell保留缺失状态。
2. **50K五次独立构建缺失。** 可用Phase2四数据集各一seed；主Figure16两规模均使用此同批pilot，不绘制独立构建CI。20K五次构建另图展示。
3. **Hybrid的H=1,2,3×K=2,3,4、25/40节点完整敏感性缺失。** 找到的是四根节点H=2,3,4网格及H4预算记录，另存/另图，不能把Exact历史数据改名Hybrid。
4. 门级13组、shots、gate count/depth及6/8-bit组件资源没有缺失。每配置资源耗时只记录首seed，不能添加种子CI。
5. 搜索到的Q-COST LaTeX为历史分析/编译预览及独立替换片段，未找到正式投稿主TeX。当前替换稿内部label唯一且与新10–13不冲突，正式14–16号须由完整正文插入顺序自然形成。

全部缺失仅按已有记录报告，本轮未补跑任何实验。
''')
    write('reports','experiment_version_audit.md','''# 实验版本与方法身份

| 输出 | 真实来源 / 方法 | 统计口径 |
|---|---|---|
| Figure14 | stage4/8/16/32/64_aer；理想Qiskit Aer | 4-bit 13配置；其他位宽分开 |
| Figure15 | 原Recursive Exact H/K记录 | 25共同节点质量/时间，40节点可行数 |
| Figure16 Q-COST | Phase2 M8，Hybrid-QMF implementation | 同批20K/50K，每cell一个build |
| Figure16其他方法 | Phase2 M1/M3/M6 | Exact / Cached Anytime / Hybrid-BestFirst |
| 20K补充图 | Phase3 EXACT/QMF/M3/M6/M8 | 五build；QMF为Original Analytic，与M8分开 |
| H2–H4候选 | Phase4 EXACT/M8 | 四固定根×九设置×一个seed，均完整求解 |

原Table III的cpu_qmf_h3、Phase3的QMF和Phase2/3/4的M8不是同一实现。只有M8展示为Q-COST。历史R4/H1/Analytic记录完整保留于inventory，不用于填补新版缺项。
Figure16采用已有同批四方法是对缺失数据的明确处理，并非宣称已完成请求的R4/H1新实验。可用Exact与Hybrid直接比较；Cached/BestFirst同批记录一并保留，避免遗漏已完成强基线。
样本数据、查询、模型和kernel SHA按每个dataset/size/seed核对，Phase2与Phase3的计时不混合。
颜色继承已定规范；Cost-H1按本次明确要求记录为#4DBBD5，但因未进入主图没有产生与BestFirst共同图例混淆。原4.2–4.4图形完全不改。
''')
    write('reports','paper_change_notes.md','''# 论文替换说明

- 独立文件保留两节标题：Gate-Level Quantum Search Validation；Sensitivity and Scalability Analysis。
- 原门级图label fig:qcost_13改为fig:qcost_14；原H/K图fig:qcost_14改为fig:qcost_15；原规模图fig:qcost_15改为fig:qcost_16。新的fig:qcost_13继续用于Hybrid，不被占用。
- 原Table VI及其引用由Figure15替代。旧门级概率表信息并入Figure14；原Table III的构建/查询指标由Figure16承接，旧数据另存，不再重加表格。
- 删除原“Figure13(b)解析—测量散点”描述，改为实际线路深度；成功率仍保持全部13组。
- Figure16正文更新为真正Hybrid的20K/50K同批pilot和实际已完成方法。原四策略/五构建描述不适用于该完整两规模新版campaign；五构建20K仅作独立补充。
- Caption使用三个指定短图名；统计单位、协议与版本在紧邻正文说明，图内不加底部说明。
- 原投稿主文件没有被覆盖。替换稿没有Table引用、table环境或手动figure计数器；与前一替换片段的10–13标签无重名。
- 完整投稿主TeX尚未定位，因此不能声称最终全文已自然编号14–16；预览按片段自然从1起号，需在13张前序图之后整合。
''')
    write('reports','figure_design_notes.md','''# 图形设计

- Figure14：双栏上下两子图。13组标签采用N/j，每个N用浅灰分隔；两根真实概率柱，深度为log纵轴、同N内连线，不跨地址空间连接。这样每组N/j保持可读。
- Figure15：双栏1×3。成本/时间折线按K分色与marker；可行节点分组柱，0–40范围保留。H3计数标为25、36、40，避免25/40长标注遮挡相邻柱形。
- Figure16：双栏2×2。两规模同批四方法、两个指标；主图线性零起点，无虚构单buildCI。长dataset刻度分两行，子图标题仍单行14.5pt。
- 查询毫秒刻度固定为真实0.0002/0.0004步长，避免格式化将0.00025错标为0.0003。20K五build补充图完整显示Student-t误差棒。
- 全部标题14.5pt Times Bold，下方Axes居中。布局沿用4.2的Renderer点单位压缩，逐图设置绘图区高度，导出pad_inches=0.02。
''')
    mapping=pd.DataFrame([dict(role=role,old_label=old,new_label=new) for role,old,new in [
      ('Gate validation','fig:qcost_13','fig:qcost_14'),('Parameter sensitivity','fig:qcost_14','fig:qcost_15'),('Index scalability','fig:qcost_15','fig:qcost_16')]])
    mapping.to_csv(OUT/'data/figure_label_mapping.csv',index=False)
    # Register every inspected old paper fragment, without changing it.
    prov=read('provenance.csv').drop(columns=['source_row'],errors='ignore')
    paths=[BASE/'QMap-LI/paper_icde_qcost_results/05_analysis'/n for n in ['LATEX_COMPILE_PREVIEW.tex','FIG13_PAPER_TEXT_EN_ZH.tex','FIG14_PAPER_TEXT_EN_ZH.tex','FIG15_PAPER_TEXT_EN_ZH.tex']]
    oldpaths=set(prov.source_file)
    extra=[]
    for p in paths:
        value=p.read_bytes()
        if str(p) not in oldpaths:extra.append(dict(source_file=str(p),sha256=hashlib.sha256(value).hexdigest(),bytes=len(value),mtime_ns=p.stat().st_mtime_ns))
    pd.concat([prov,pd.DataFrame(extra)],ignore_index=True).to_csv(OUT/'data/provenance.csv',index=False)
    (OUT/'README.md').write_text('''# Q-COST Figures14–16

现有数据只读复算、绘图与独立LaTeX替换；未运行实验。

- Figure14：13组4-bit gate验证＋实测线路深度。6/8-bit另存。
- Figure15：9组Recursive Exact H/K；25共同节点质量/时间、40节点可行数。
- Figure16：新版Hybrid同批20K/50K四方法pilot，单build无CI。原请求R4/H1的新版配对缺失，未拼接。
- 补充：四根节点H2–H4 Exact/Hybrid参数候选；20K五独立build的五方法Student-t图。

PDF/SVG矢量，PNG600dpi，14.5pt加粗单行下方标题。方法、数据源、时间边界与缺失项见reports。
`bash reproduce.sh`仅重新提取已存记录并绘图，先归档本目录现有派生输出。
原脚本备份archive/original_plot_scripts.zip；原数据与之前4.2–4.4输出的SHA核验见reports/source_integrity_after.csv。
独立论文片段latex/section4_5_4_6_revised.tex；不修改正式论文，图号须在整合时自然确定。
''')
    print('Wrote LaTeX and data/version audits; original files untouched.')

if __name__=='__main__':main()
