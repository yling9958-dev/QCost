"""Current layout deliverables, reusing prior data without re-extraction."""
from pathlib import Path
import json
import pandas as pd
OUT=Path(__file__).resolve().parents[1]

CAPTIONS={
'fig6_latency_ecdf':r'''Range-count latency on large-scale spatial workloads.
Empirical distributions are shown for GeoLife and Skewed 2D using available
per-query records; each curve retains 15,000 observations. GeoLife includes
seven curves and Skewed 2D includes seven. The latency axis is logarithmic.''',
'fig7_grouped_bar':r'''Range-count performance across four large-scale spatial
datasets and seven methods: (a) mean latency, (b) P95 latency, (c) P99 latency,
and (d) derived sequential throughput. Lower latency and higher throughput
are preferable. Speedups compare Q-COST with the fastest competing method
on each dataset. Logarithmic bars begin at positive axis baselines; their
endpoints encode measurements. QPS equals 1000 divided by mean latency in ms.''',
'fig8_construction_storage':r'''Construction cost and storage--latency
characteristics. (a) Q-COST construction time. (b) Complete persisted query
state versus mean query latency; colors indicate methods and shapes denote
datasets. Point payloads are included. The two GiST observations include
table-plus-index footprints. Missing sizes, index-only footprints and point
archives requiring reconstruction are excluded.''',
'fig9_latency_reduction':r'''Relative query-latency reduction against R4 Greedy
across three query-area classes on four spatial datasets with 20K points.
Positive values indicate lower query latency. Error bars represent 95\%
Student-$t$ confidence intervals across five paired independent builds
(four degrees of freedom). S1, S2 and S3 denote nominal pre-clipping query
areas of 0.01\%, 0.1\% and 1\%. The dashed line marks the R4 reference.
Small categorical offsets separate overlapping error bars.''',
'fig9_relative_latency_zoom':r'''Relative range-count latency across three
query-area classes on four spatial datasets with 20K points. Error bars
represent 95\% Student-$t$ confidence intervals across five paired independent
builds (four degrees of freedom). S1, S2 and S3 denote nominal pre-clipping
query areas of 0.01\%, 0.1\% and 1\%. The dashed line at one marks the R4
reference; lower ratios indicate lower latency. Small categorical offsets
separate overlapping error bars.'''}
ZH={
'fig6_latency_ecdf':'大规模范围计数延迟经验分布。使用保留的逐查询计时，每条曲线含15000条观测；GeoLife为七条曲线，Skewed为七条曲线。横轴为对数尺度。',
'fig7_grouped_bar':'四数据集、七种方法的28组查询性能。平均、P95、P99越低越好，QPS越高越好。倍数相对该数据集最快竞争方法。对数柱形采用正数基线并以端点表示数值。',
'fig8_construction_storage':'Q-COST构建时间以及完整持久化查询状态与延迟关系。颜色区分方法、形状区分数据集。缺失存储值、仅索引关系大小与需重建的点归档不纳入散点比较。',
'fig9_latency_reduction':'相对R4 Greedy的查询延迟降幅，正值表示延迟降低。误差棒为五次配对独立构建的95% Student-t区间（自由度4）。20K点样本，S1/S2/S3为裁剪前0.01%/0.1%/1%名义查询面积。',
'fig9_relative_latency_zoom':'四数据集的相对范围计数延迟及五次配对独立构建的95% Student-t区间。20K点样本，S1/S2/S3定义同版本A，参考线为1，数值越低延迟越小。'}

def environment(n,label):
    return '\n'.join([r'\begin{figure*}[t]',r'    \centering',
        r'    \includegraphics[width=0.95\textwidth]{figures/'+n+'.pdf}',
        '    \\caption{'+CAPTIONS[n]+'}', '    % '+ZH[n],
        '    \\label{'+label+'}',r'\end{figure*}',''])

def main():
    names=['fig6_latency_ecdf','fig7_grouped_bar','fig8_construction_storage','fig9_latency_reduction']
    tex='% Independent figure environments; original paper is not modified.\n'
    tex+='% Requested Figures 6--9 require five preceding figures; use natural numbering.\n'
    tex+='% Figure 9A is the default. Replace only its environment with the B alternative if desired.\n'
    tex+='\n'.join(environment(n,f'fig:qcost_0{i}') for i,n in enumerate(names,6))
    (OUT/'latex/section4_2_figures_revised.tex').write_text(tex)
    (OUT/'latex/fig9_version_B_alternative.tex').write_text('% Alternative to Figure 9A; do not include both under the same label.\n'+environment('fig9_relative_latency_zoom','fig:qcost_09'))
    (OUT/'latex/section4_2_body_revisions.tex').write_text(BODY)
    s=pd.read_csv(OUT/'data/fig9_current_statistics.csv')
    a=json.loads((OUT/'reports/fig9_latency_reduction_data_check.json').read_text())
    b=json.loads((OUT/'reports/fig9_relative_latency_zoom_data_check.json').read_text())
    q=s[(s.method=='Q-COST')&(s.area_class=='S3')]
    (OUT/'reports/layout_revision_data_audit.md').write_text(f'''# 当前版数据与统计审计

本轮只修改绘图脚本与派生输出；未运行实验、查询、索引构建或算法。
修改前完整备份位于 archive/previous_delivery_20261020T204457736756.zip，包含原脚本及
原 fig9_workload_lines.pdf/SVG/PNG。原始输入和历史派生 CSV 只读。

## Flood / Skewed 2D

按本轮明确确认，该结果作为正常有效汇总参加 Figure 7 的28组比较。
显示名 Flood、实际实现 Flood-V2。2026-10-25定点更新：均值199.713213、P95 715.018688、P99 4286.059673 ms；
QPS严格保留用户确认的5.007180，与1000/199.713213在六位小数精度下一致。
Build为153.381455 s，Peak RSS为16535.820313 MiB；204986702点、300次预热、15000次正式测量、5轮，正确性1000/1000通过。
真实结果及来源见 data/flood_skewed_real_result.csv 和 FLOOD_SKEWED_REAL_RESULT_UPDATE.md。仅替换该目标，其他数值原样保留。
柱形颜色、纹理、边框与其余三个 Flood 数据集完全一致，无星号或特殊文字。
图7为112根柱形（28组×4指标），每组加速比考虑全部六种竞争方法。
原有 CSV 中历史审核字段不回写；当前纳入规则记录在 fullscale_plot_accepted.csv，
保留证据来源与本次确认。该规则不修改任何原始实验记录。

Index Size仍缺失；Peak Memory不替代存储。Figure 8存储面板保持22个可比完整状态。
Figure 6保留已有13条ECDF，并从Flood新实验的15000条真实计时补入Skewed曲线；现共14条（两数据集各七条），不由汇总值合成分布。
图片内部没有数据说明；可用逐查询记录的覆盖范围转入LaTeX图注。

## Figure 9 配对统计

从原 workload_build_pairs.csv 的240条构建—面积记录重新计算。
同数据集、种子、面积类别与R4均值配对，五个种子为11/23/37/51/73。
每组 ratio = MethodLatency / R4Latency，先得到五个比值后计算均值及
t(0.975,4) × sd / sqrt(5) 的置信区间。重新计算的全部48组统计与历史值一致。
Q-COST仍是原cpu_qmf_h3构建实现，未改名为Hybrid。

降幅 = 100 × (1-ratio)。降幅CI下界 = 100 × (1-relative_CI_upper)，
上界 = 100 × (1-relative_CI_lower)。同时从五个降幅样本直接计算Student-t区间，
两种结果一致（容差1e-12）。两版没有重新采样或调整任何误差棒。

原始全部相对CI边界：[0.8394890774134625, 1.1081918961736696]。
对应降幅CI边界：[-10.81918961736696, 16.05109225865375]%。
使用全局CI跨度4%的余量，向0.02的相对比值单位外侧取整：
版本A纵轴 {a['shared_ylim']}%，版本B纵轴 {b['shared_ylim']}。
两个范围通过同一线性变换对应，所有四个数据集共享范围；所有误差棒完整保留。
全部12个Q-COST区间在A中覆盖0，在B中覆盖1，均不支持这些条件下的显著查询优势。

S3均值降幅：
{q[['dataset','reduction_pct','reduction_ci_low','reduction_ci_high']].to_csv(index=False)}

## A/B表达比较

A直接表达相对R4降低/增加百分比，正负方向直观，作为默认候选。
B保留旧正文ratio定义，便于与历史结果核对。
两者是同一数据的仿射变换，具有完全相同的统计信息与相对误差棒长度。
放大纵轴提高可辨识度但不改变显著性；图注说明参考线、统计单位与95%CI。
可选S3百分比标注通过Renderer与数据线、误差棒碰撞检查，无法放置则省略。
''')
    (OUT/'README.md').write_text('''# Section 4.2 当前紧凑排版版本

当前候选：fig6_latency_ecdf、fig7_grouped_bar、fig8_construction_storage、
fig9_latency_reduction（默认A）及fig9_relative_latency_zoom（备选B）。
全部位于 figures/，PDF/SVG/600dpi PNG；fig9_comparison.png为A/B并排审阅图。

所有子图标题固定14.5 pt、加粗、单行、相对Axes居中。图内不放总图注或底部说明。
Figure 7正常纳入28组结果，包括本轮确认的Flood–Skewed；内部保留来源，柱形无特殊标识。
Figure 6保持真实14条ECDF；Flood–Skewed新增曲线来自15000条实测计时，没有从汇总指标合成分布。
Figure 9使用原五次配对构建统计；两版CI分别覆盖0或1的关系保持不变。

使用 latex/section4_2_figures_revised.tex 和 section4_2_body_revisions.tex。
原来的 section4_2_revised.tex、旧审核说明和带星号补充图是历史版本，不用于当前稿。
替换Figure 9为B时使用 fig9_version_B_alternative.tex，不同时引入重复label。
全文主TeX仍未取得，图号由原稿插入顺序自动决定，不强制设置计数器。

复现：在本目录运行 `bash reproduce_layout.sh`。该命令先备份当前输出，然后仅从现有
CSV绘图、统计、排版检查和导出，不执行实验或重新提取原始数据。
数据说明：reports/layout_revision_data_audit.md。
排版检查：reports/compact_layout_check.md；原始文件完整性：reports/layout_revision_integrity.md。
旧图和脚本在 archive/previous_delivery_*.zip 中完整保存。
''')

BODY=r'''
% Independent prose replacement suggestions; do not overwrite the original manuscript automatically.
% Use this range-count paragraph to replace the former 27-combination qualification.
Figure~\ref{fig:qcost_07} compares seven methods on four large-scale datasets,
covering 28 method--dataset results. Q-COST's mean latencies are 0.8636,
1.3646, 0.1601, and 6.4236 ms for GeoLife, Gowalla, NYC Taxi, and Skewed 2D.
Against the fastest competing method on each dataset, the corresponding
speedups are 34.1, 35.6, 220.8, and 10.3 times. The competitor is LISA on
Gowalla and BMTree on the other three datasets. These measurements compare
complete index systems, including their execution pipelines.
% 图7包含七方法、四数据集的28组结果。Q-COST平均延迟依次为0.8636、1.3646、0.1601、6.4236 ms；相对最快竞争方法为34.1、35.6、220.8、10.3倍。Gowalla比较对象为LISA，其余为BMTree。这些倍数是完整索引系统及执行流水线的比较。

% Preferred Figure 9A: replace the paragraph discussing relative latency ratios.
Figure~\ref{fig:qcost_09} reports query-latency reduction relative to R4 Greedy
on the retained 20K-point workloads. For each dataset, build seed, and query-area
class, reduction is $100(1-L_{\mathrm{method}}/L_{\mathrm{R4}})$.
Positive values indicate lower latency, while negative values indicate higher
latency. Means and 95\% Student-$t$ confidence intervals use five paired
independent builds. Q-COST retains the original analytic-QMF construction
implementation used in this controlled campaign.
% 图9A在原20K点受控工作负载上展示相对R4的延迟降幅。先按数据集、构建种子、查询面积类别配对计算100(1-方法延迟/R4延迟)，正值表示延迟降低，负值表示增加。均值和95% Student-t区间来自五次配对独立构建。Q-COST保留原实验的解析QMF构建实现。

At S3, Q-COST's mean reductions are $-1.95\%$, $0.55\%$, $2.68\%$, and
$2.70\%$ on GeoLife, Gowalla, NYC Taxi, and Skewed 2D, respectively.
All twelve Q-COST confidence intervals contain zero. The magnified display
therefore reveals modest dataset-dependent shifts together with their
uncertainty, rather than establishing a significant latency advantage under
these common-kernel conditions.
% S3下Q-COST平均降幅依次为-1.95%、0.55%、2.68%、2.70%。全部12组Q-COST区间覆盖0，显示较小的数据集相关变化及不确定性，不据此宣称统一内核下存在显著延迟优势。

% Alternative Figure 9B: use the following paragraph only when selecting version B.
% Figure~\ref{fig:qcost_09} shows mean query latency normalized to the paired R4
% Greedy run. The common vertical range retains every 95\% Student-$t$ interval
% across five independent builds. All twelve Q-COST intervals include one.
% 若采用版本B，保持相对延迟定义，统一纵轴完整容纳五次独立构建的95%区间；Q-COST全部12组区间仍包含1。
'''

if __name__=='__main__':main()
