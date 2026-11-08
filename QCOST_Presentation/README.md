# Q-COST 中文研究进展汇报

交付：`Q-COST_ICDE_Research_Progress_CN.pptx`、同名PDF。共22页，16页主汇报、6页备查附录；主汇报讲述稿合计590秒，约9分50秒。建议第9、11、12页重点讲，附录按导师提问展开。

## 打开与编辑

- PPTX内有16张原生可编辑表格、6个原生数据图表及其内嵌Excel数据、22页演讲者备注。标题、说明、流程框、箭头与热力图均为原生对象。
- 第2–4页的实际空间点、划分边界和动机小图使用高分辨率科研图片；对应CSV、Matplotlib脚本、SVG和矢量PDF保存在`data/`、`scripts/plot_assets.py`、`assets/`。
- 封面汇报人和单位没有可靠信息，使用`[待填写]`；日期设为明天2026年10月16日。可直接修改文本框。
- 使用Noto Sans CJK SC。当前环境已安装；另附`assets/NotoSansCJKSC-Regular.otf`以便跨机器保持字体。PDF字体已嵌入，适合直接演示或打印。PPTX没有内嵌整套字体，缺少字体的电脑可能发生替换。
- `notes/SPEAKER_NOTES_ZH.md`提供每页重点、30–60秒讲述词、数据口径；同样内容已写入PowerPoint备注。`notes/SLIDE_OUTLINE_ZH.md`提供逐页摘要与时间。

## 数据与统计口径

主数据来自原`QMap-LI/paper_icde_qcost_results/07_reporting_tables/QCOST_COMPARISON_TABLES.xlsx`的18张主表、6张附表。全部24张表与对应CSV自动核对。独立Excel副本和导出CSV保存在`data/`。额外动机空间数据来自既有`QMF-Motivation-Figures/derived_data/`，每份来源与SHA-256保存在`validation/input_manifest.csv`。

1. 亿级系统的21个完成组合测量prepared range-count；相对BMTree的10.3–220.8倍均由未截断均值重新计算，包含索引和查询内核差异。
2. 20K/50K控制实验使用统一查询内核。主报告展示50K均值，附录B展示两种规模完整七指标；全部160次构建通过COUNT和ID集合检查。跨构建QPS是每个索引QPS的均值。
3. 正式预算搜索复用40主节点；随机方法30种子。逐节点正式预算为`ceil(2*sqrt(N))`；固定预算曲线只画实际32/64/128/256/512记录。Beam预算与QMF抽象oracle计数不同。
4. 敏感性分析为25个共同可行节点，相对各自H1/K4计算代理成本降幅后平均。48.481%是代理成本降幅。
5. 门级数据为真实Qiskit Aer、4位成本、单标记态、每条件5种子×2048 shots；13个N/j条件的最大概率偏差0.488个百分点。它验证概率行为，不是硬件加速或整套QMF的成功率。
6. 不同系统构建/RSS/存储统计边界不完全相同，附录A保留星号和说明；LMSFC部分复现与失败/超时组合放入附录F，不填0。

`validation/data_checks.csv`记录来源一致性与关键统计检查；`validation/delivery_checks.csv`进一步核对可编辑图表缓存、内嵌Excel、表格显示值、PDF字体和来源哈希。

## 复现命令

以下步骤只读现有冻结结果并生成演示文件，不运行索引构建、训练或benchmark。所有生成文件仅写入本目录。使用当前已具备的Python依赖；精确版本见`requirements.txt`和`validation/environment.json`。

```bash
cd '/media/lingyaqi/Lenovo F510/QMF/QCOST_Presentation'
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=2
python3 -B scripts/prepare_data.py
python3 -B scripts/plot_assets.py
python3 -B scripts/build_deck.py
python3 -B scripts/render_and_check.py
python3 -B scripts/validate_delivery.py
```

`prepare_data.py`从原项目重新核查并复制输入。若只在独立目录中调整版式，已有`data/`足够，直接从`plot_assets.py`开始，无需访问原项目。

当前系统仅有LibreOffice Writer，不能直接读取PPTX。为实际渲染，本次把现有核心程序只读复制到`validation/portable_renderer/root/`，并将匹配版本的Impress、Draw及5个依赖包解压到同一独立目录，**未进行系统安装或升级**。下载包清单、官方Ubuntu仓库相对路径和SHA保存在`package_manifest.json`。此本地渲染器已就绪，`render_and_check.py`自动使用它。若在相同系统重建：

```bash
python3 -B scripts/download_renderer_packages.py
python3 -B scripts/setup_local_renderer.py
python3 -B scripts/render_and_check.py
```

其他机器可直接用PowerPoint导出PDF，或在完整LibreOffice Impress环境运行`render_and_check.py`。便携渲染器脚本针对当前Ubuntu/LibreOffice版本，不作为跨平台安装器。

## 文件组织

|路径|内容|
|---|---|
|根目录PPTX/PDF|正式汇报文件|
|`scripts/`|数据提取、科研图、PPT生成、PDF渲染、检查脚本|
|`data/`|Excel独立副本、24张表、空间案例数据、实际图表数据|
|`assets/`|演示科研图PNG/SVG/PDF、字体；原论文图完整副本|
|`notes/`|讲稿、逐页摘要、结构化备注|
|`reference_review/`|17页ICDE参考PPT渲染与风格分析|
|`renders/`|22页实际PPTX导出PDF的逐页PNG与联系表|
|`validation/`|数据校验、PDF/布局检查、前后哈希、依赖与渲染器记录|

## 质量检查与保护范围

22页PPTX已实际导出PDF并逐页目视检查；修正了默认主题阴影、方法框中文字换行、回路箭头交叉、预算轴标题折行和附录A的注释遮挡。详细记录见`validation/QUALITY_REPORT_ZH.md`。

177项既有结果来源SHA清单在制作前后复核，另对本次59份输入保存前后哈希。两组记录可能有交集，不把数量相加成独立文件总数。所有受检原文件保持一致。原项目源码和实验数据未修改，唯一新增写入范围是用户指定的`QCOST_Presentation/`。

便于转交的`Q-COST_Presentation_Delivery.zip`包含正式文件、脚本、数据、讲稿、渲染图和检查记录；不含约958MB的本地LibreOffice核心副本和临时缓存，保留重建脚本与依赖包校验清单。
