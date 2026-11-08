# Section 4.2 当前紧凑排版版本

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
2026-10-25已更新Flood × Skewed 2D真实汇总、Figure 7，并补齐Figure 6真实ECDF；Figure 8保持不变。结果见data/flood_skewed_real_result.csv，汇总替换审计见FLOOD_SKEWED_REAL_RESULT_UPDATE.md。
只重现此次定点更新：`python -B scripts/update_flood_skewed_real_result.py`，不运行其他绘图脚本或实验。
只重现Figure 6同步：`python -B scripts/sync_fig6_flood_ecdf.py`；说明与保护检查见FIG6_FIG8_FLOOD_SYNC.md。
排版检查：reports/compact_layout_check.md；原始文件完整性：reports/layout_revision_integrity.md。
旧图和脚本在 archive/previous_delivery_*.zip 中完整保存。
