# Q-COST Figures 10–13

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
