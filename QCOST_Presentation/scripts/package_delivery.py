#!/usr/bin/env python3
"""Write the final review record and package the completed editable presentation."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
V=ROOT/'validation'
summary=json.loads((V/'structural_checks.json').read_text())
checks=pd.read_csv(V/'delivery_checks.csv')
data_checks=pd.read_csv(V/'data_checks.csv')
prior=pd.read_csv(V/'prior_integrity_after.csv')
inputs=pd.read_csv(V/'input_integrity_after.csv')
slides=json.loads((ROOT/'notes/slide_manifest.json').read_text())
assert checks.Passed.all() and data_checks.Passed.all() and prior.Unchanged.all() and inputs.Unchanged.all()
assert summary['Slides']==22 and summary['OutOfBoundsPDFSpans']==0 and not summary['OutOfBoundsObjects']

reviews=[
 '题名、中英文论文名称、日期和可编辑作者占位完整。',
 '真实20K点和Q84/Q667完整窗口可见；树示意为原生对象。',
 '两侧同一真实点集、查询与放大范围；14条H3边界；引导线与放大刻度无重叠。',
 '三项观察独立编码，21/40/43节点及正式预算总体明确。',
 '全部模块原生可编辑；根提交回路绕开在线查询文本；两优化路线完整。',
 '条件分支、左右子集与递推式完整；固定查询上下文已说明。',
 '精确与有限预算路线并列；经典完整成本表边界明确。',
 '四组真实数据规模、21个完成组合和160次同内核构建分开。',
 '对数轴明确；四组倍率重新计算；表格与嵌入图表数据一致。',
 '六方法两组表清楚；Q-COST行突出；QPS换算范围明确。',
 '50K构建时间与查询时间分表；未声称同内核显著查询加速。',
 '完整配置/根动作指标分别展示；保留Exact 100%与Beam预算区别。',
 '两幅预算图使用横向指标标题，五个实际预算点，表格与曲线一致。',
 '九格热力图与K4表均来自25个配对节点；代理成本含义明确。',
 '解析与真实Aer概率逐条件配对；4位、单标记、13个条件范围明确。',
 '三个核心数字各自附适用范围，后续工作具体，主汇报结束明确。',
 '21行完整七指标可编辑；12.3pt附录字号，底部计量范围注释完整。',
 '20K/50K成对值及μs、KiB、千QPS换算注明；160构建检查完整。',
 '五优化器质量/时间并列，明确Recursive Exact更低CPU阶段时间。',
 '全部阶段为实测；QMF排序不重复计数；0.56%重新计算。',
 '九种H/K组合保留负改善；理论上界与实际可行性分开。',
 '失败、超时、安全停止、部分复现真实保留；补充实验无文字孤行。']
pd.DataFrame([{'Slide':s['number'],'Title':s['title'],'VisualStatus':'PASS',
               'ReviewedImage':f'renders/slide_{s["number"]:02d}.png','Findings':reviews[i]}
              for i,s in enumerate(slides)]).to_csv(V/'visual_review.csv',index=False)
pd.DataFrame([{'Slide':s['number'],'Title':s['title'],'Sources':s['full_sources'],
               'Scope':s['caveat'],'Summary':s['focus']}
              for s in slides]).to_csv(V/'slide_evidence_map.csv',index=False)
font_license=Path('/usr/share/doc/fonts-noto-cjk/copyright')
if font_license.exists():shutil.copy2(font_license,ROOT/'assets/Noto_CJK_FONT_LICENSE.txt')

text=f'''# Q-COST汇报交付检查报告

交付对象：`Q-COST_ICDE_Research_Progress_CN.pptx`与同名PDF。

## 实际完成

- 16:9，22页：16页主报告、6页附录；主报告建议590秒，即9分50秒。
- 16张PowerPoint原生表格、6个原生图表、6份嵌入Excel工作簿、22页演讲者备注。方法图、标题、公式、热力图和说明可编辑。
- 背景/动机图使用真实CSV重绘；空间图保留同一20K点集、两条真实查询窗口和两配置共14条真实H3划分线。原论文Figure 2–15完整副本可核查。
- 已实际渲染参考PDF全部17页；总结其白底、大标题、橙色竖线、图表邻接和一句话结论规范。采用用户指定蓝灰/深蓝/橙红体系，未复制论文内容。
- PPTX实际通过独立LibreOffice Impress导出22页PDF，随后将每页渲染为PNG逐页检查，并在修改后复查。没有用静态图片拼出伪PPT。

## 自动检查结果

|检查|结果|
|---|---|
|Excel与配套CSV及关键统计核验|{len(data_checks)}/{len(data_checks)}通过|
|交付数据/字体/渲染文本/工作簿检查|{len(checks)}/{len(checks)}通过|
|主汇报原生表格最小字体|{summary['MainTableMinPt']:.1f} pt|
|附录原生表格最小字体|{summary['AppendixTableMinPt']:.1f} pt，仅完整备查表|
|超出幻灯片的对象|0|
|超出PDF页面的文本跨度|0|
|PDF字体|全部嵌入|
|原生表格与导出数据|全部一致|
|6个图表缓存与嵌入Excel|全部一致|
|逐页备注|22/22完整|
|原始来源前后SHA|{len(prior)}/{len(prior)}既有清单一致；另{len(inputs)}/{len(inputs)}本次输入一致|

两个SHA集合可能相交，不将其相加为独立文件数。本轮没有运行训练、索引构建或数据库benchmark，也没有修改旧源码、模型、查询池或结果文件。新文件全部写入用户授权的`QCOST_Presentation/`。

## 实际修复的版式问题

1. 清除Office默认主题给原生形状附加的阴影。
2. 调整框架图输入文本和根提交框内行距，重新路由反馈箭头，避免穿过在线查询说明。
3. 将第13页较长纵轴标题改为横向面板指标，保持0–100%完整轴域。
4. 扩展空间图显示范围以完整呈现真实查询窗口，数据点与划分边界坐标保持原值；统一放大区间并保留引导线。
5. 删除局部放大图重复y标签、为刻度留出空间，防止引导线与数字重叠。
6. 将附录A范围注释移到完整表格下方，保证其不被最后两行遮住。
7. 修改附录F提交机制条目的断行，避免单字孤行。

## 科学口径检查

- 10.3–220.8倍来自四个亿级系统的平均prepared范围计数延迟，包含查询内核贡献，未归因为QMF独立收益。
- 50K查询延迟差异有限，联合规划构建更慢；第11页明确展示两种事实。
- QMF正式预算65.42%配置最优、95.08%根最优，Recursive Exact的100%同时保留。Beam预算不等同QMF抽象oracle计数。
- QMF预算曲线复用第三章40节点，未包装为独立新样本；只连已测预算点。
- 48.481%为25共同可行节点的局部代理成本降幅，未写成查询延迟改善。
- 当前CPU QMF依赖经典完整成本表；阶段开销包含预计算，未声称端到端量子加速。Recursive Exact在当前计时下低约16.38%。
- Aer结果使用4位成本、单标记态；0.488个百分点是全部13个N/j条件的最大测量偏差，未称为QPU实验或完整H3最小值成功率。
- 各系统资源统计边界存在差异，附录A保留星号和范围说明。未完成、超时和部分复现保留真实状态。

## 逐页目视检查

|页|标题|结果与检查点|
|---|---|---|
'''
text+='\n'.join(f'|{s["number"]}|{s["title"]}|PASS；{reviews[i]}|' for i,s in enumerate(slides))
text+='''

## 交付限制与使用说明

汇报人、单位没有可靠来源，保留可编辑占位。Noto Sans CJK SC用于版式；字体独立附带，PDF字体已嵌入。实际检查使用当前Linux LibreOffice，PowerPoint可直接编辑原生对象；跨机器字体替换可能改变换行。附录A/B用于放大查看与问答备查，完整数值精度和标准差同时保存在附带Excel。

源文件路径、SHA、每页证据映射、环境版本及逐页PNG全部保留。复现命令见根目录README；主汇报讲稿见notes/SPEAKER_NOTES_ZH.md。
'''
(V/'QUALITY_REPORT_ZH.md').write_text(text)

# Hash the deliverable content, excluding temporary renderer profiles and itself.
included=[]
dirs=['scripts','data','assets','notes','renders','reference_review']
for directory in dirs:
    included += [p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
included += [p for p in V.glob('*') if p.is_file() and p.name!='delivery_file_sha256.csv']
included += [ROOT/'README.md',ROOT/'requirements.txt',ROOT/'Q-COST_ICDE_Research_Progress_CN.pptx',ROOT/'Q-COST_ICDE_Research_Progress_CN.pdf']
included += [V/'portable_renderer/package_manifest.json']
hashes=[]
for p in sorted(set(included)):
    hashes.append({'Path':str(p.relative_to(ROOT)),'SHA256':hashlib.sha256(p.read_bytes()).hexdigest(),'Bytes':p.stat().st_size})
pd.DataFrame(hashes).to_csv(V/'delivery_file_sha256.csv',index=False)
included.append(V/'delivery_file_sha256.csv')
archive=ROOT/'Q-COST_Presentation_Delivery.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(set(included)):z.write(p,str(p.relative_to(ROOT)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(json.dumps({'Archive':str(archive),'ArchiveMiB':archive.stat().st_size/1024**2,'Files':len(set(included)),
                  'PPTXBytes':(ROOT/'Q-COST_ICDE_Research_Progress_CN.pptx').stat().st_size,
                  'PDFBytes':(ROOT/'Q-COST_ICDE_Research_Progress_CN.pdf').stat().st_size},ensure_ascii=False,indent=2))
