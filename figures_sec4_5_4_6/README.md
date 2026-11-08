# Q-COST Figures14–16

现有数据只读复算、绘图与独立LaTeX替换；未运行实验。

- Figure14：13组4-bit gate验证＋实测线路深度。6/8-bit另存。
- Figure15：9组Recursive Exact H/K；25共同节点质量/时间、40节点可行数。
- Figure16：新版Hybrid同批20K/50K四方法pilot，单build无CI。原请求R4/H1的新版配对缺失，未拼接。
- 补充：四根节点H2–H4 Exact/Hybrid参数候选；20K五独立build的五方法Student-t图。

PDF/SVG矢量，PNG600dpi，14.5pt加粗单行下方标题。方法、数据源、时间边界与缺失项见reports。
`bash reproduce.sh`仅重新提取已存记录并绘图，先归档本目录现有派生输出。
原脚本备份archive/original_plot_scripts.zip；原数据与之前4.2–4.4输出的SHA核验见reports/source_integrity_after.csv。
独立论文片段latex/section4_5_4_6_revised.tex；不修改正式论文，图号须在整合时自然确定。
