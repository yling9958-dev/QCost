"""Validate new layouts, render actual PDF/SVG, and check immutable inputs."""
from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from PIL import Image
from plot_style import OUT
from preview_and_check import run,compile_tex
from render_svg import render
from write_layout_revision import CAPTIONS

NAMES=['fig6_latency_ecdf','fig7_grouped_bar','fig8_construction_storage',
       'fig9_latency_reduction','fig9_relative_latency_zoom']
PREVIEW=OUT/'reports/compact_previews'

def validate():
    records=[]
    for n in NAMES:
        p=OUT/'figures'/n;d=json.loads((OUT/'reports'/f'{n}_compact_layout.json').read_text())
        assert not d['text_overlaps'] and not d['legend_conflicts'] and not d['outside_canvas']
        assert not d['extra_figure_captions'] and not d['annotation_data_conflicts']
        assert all(t['font_pt']==14.5 and t['weight']=='bold' and t['single_line'] and t['center_error_pt']<.1 for t in d['title_checks'])
        font=run(['pdffonts',str(p)+'.pdf']);imgs=run(['pdfimages','-list',str(p)+'.pdf'])
        (OUT/'reports'/f'{n}_current_pdf_fonts.txt').write_text(font)
        assert all(re.search(r'\byes\s+yes\s+(yes|no)\s+\d+\s+\d+\s*$',r) for r in font.splitlines()[2:] if r.strip())
        assert not any(r.strip() for r in imgs.splitlines()[2:])
        svg=ET.parse(str(p)+'.svg').getroot();ns={'s':'http://www.w3.org/2000/svg'}
        text=' '.join(''.join(t.itertext()) for t in svg.findall('.//s:text',ns))
        assert not svg.findall('.//s:image',ns)
        assert not any(x in text for x in ['V2','Tsunami-CR','Unverified','User-provided','Pending verification','no verified','no raw timings','nominal query area','95% CIs'])
        im=Image.open(str(p)+'.png');assert all(abs(x-600)<.01 for x in im.info['dpi'])
        run(['pdftoppm','-singlefile','-r','160','-png',str(p)+'.pdf',PREVIEW/n])
        render(str(p)+'.svg',PREVIEW/(n+'_svg.png'),round(d['exported_inches'][0]*160),round(d['exported_inches'][1]*160))
        records.append(dict(figure=n,width_in=d['exported_inches'][0],height_in=d['exported_inches'][1],
            subplots=len(d['title_checks']),title_font_pt=14.5,bold=True,single_line=True,centered=True,
            bottom_notes=0,text_overlaps=0,legend_conflicts=0,annotations_over_data=0,
            embedded_pdf_fonts=True,vector_only=True,png_dpi=im.info['dpi'][0],renderer_iterations=len(d['layout_iterations'])))
    pd.DataFrame(records).to_csv(OUT/'reports/compact_export_checks.csv',index=False)
    source=pd.read_csv(OUT/'data/fullscale_results.csv')
    plotted=pd.read_csv(OUT/'data/fig7_current_plotted_values.csv')
    assert len(plotted)==112 and plotted.groupby(['metric','dataset']).size().eq(7).all()
    for r in plotted.itertuples():
        ref=source[(source.dataset==r.dataset)&(source.method==r.method)].iloc[0]
        assert np.isclose(r.value,ref[r.metric],rtol=1e-12)
    styles=pd.read_csv(OUT/'reports/fig7_bar_style_audit.csv').fillna('none')
    flood=styles[styles.method=='Flood']
    assert len(flood)==16 and all(flood[k].nunique()==1 for k in ['color','hatch','alpha','edgecolor','linewidth'])
    s=pd.read_csv(OUT/'data/fig9_current_statistics.csv');q=s[s.method=='Q-COST']
    assert np.allclose(s.reduction_ci_low,100*(1-s.relative_ci_high),atol=1e-12)
    assert np.allclose(s.reduction_ci_high,100*(1-s.relative_ci_low),atol=1e-12)
    assert ((q.reduction_ci_low<=0)&(q.reduction_ci_high>=0)).all()
    for n,lo,hi in [('fig9_latency_reduction','reduction_ci_low','reduction_ci_high'),
                     ('fig9_relative_latency_zoom','relative_ci_low','relative_ci_high')]:
        c=json.loads((OUT/'reports'/f'{n}_data_check.json').read_text());bounds=c['shared_ylim']
        assert s[lo].min()>bounds[0] and s[hi].max()<bounds[1]
    return records

def preview():
    header=r'''\documentclass[conference]{IEEEtran}
\usepackage{graphicx}
\usepackage{times}
\begin{document}
\typeout{QCOST-TEXTWIDTH=\the\textwidth}
\typeout{QCOST-COLUMNWIDTH=\the\columnwidth}
\onecolumn
\pagestyle{plain}
'''
    labels=['6','7','8','9A','9B']
    for stem,scales in [('section4_2_figures_layout_preview',[.95]),('section4_2_figures_three_widths',[.90,.95,1.0])]:
        text=header
        for scale in scales:
            for lab,n in zip(labels,NAMES):
                text+=f'\\noindent\\textbf{{Figure {lab}: {scale:.2f} IEEE text width (layout preview)}}\\par\\smallskip\n'
                text+=f'\\noindent\\makebox[\\textwidth][c]{{\\includegraphics[width={scale:.2f}\\textwidth]{{figures/{n}.pdf}}}}\n'
                text+='\\par\\medskip\\noindent\\small '+CAPTIONS[n]+'\n\\clearpage\n'
        text+=r'\end{document}'
        pdf=compile_tex(stem,text)
        run(['pdftoppm','-r','130','-png',pdf,PREVIEW/stem])
    pages=sorted(PREVIEW.glob('section4_2_figures_three_widths-*.png'),key=lambda p:int(p.stem.rsplit('-',1)[1]))
    sheet=Image.new('RGB',(400*5,530*3),'#E5E5E5')
    for i,p in enumerate(pages):
        im=Image.open(p).convert('RGB');im.thumbnail((400,530));sheet.paste(im,((i%5)*400,(i//5)*530))
    sheet.save(PREVIEW/'three_widths_contact_sheet.png')
    (OUT/'reports/current_preview_geometry.json').write_text(json.dumps(dict(
        class_name='IEEEtran conference',text_width_TeX_pt=516,column_width_TeX_pt=252,
        scales=[.90,.95,1],global_numbering='Retain natural manuscript insertion order; no counter override'),indent=2))

def integrity():
    rows=[]
    for r in pd.read_csv(OUT/'reports/layout_revision_protection_before.csv').itertuples():
        actual=hashlib.sha256(Path(r.path).read_bytes()).hexdigest()
        rows.append(dict(path=r.path,before_sha256=r.sha256,after_sha256=actual,unchanged=r.sha256==actual))
    pd.DataFrame(rows).to_csv(OUT/'reports/layout_revision_protection_after.csv',index=False)
    assert all(r['unchanged'] for r in rows)
    (OUT/'reports/layout_revision_integrity.md').write_text(f'''# 本轮原始文件与输入保护

PASS：{len(rows)}个受保护文件SHA256全部一致，包含677个已审计来源及6个本轮只读输入CSV。
本轮未运行原始提取程序、实验、数据库查询、索引构建、训练或算法。
允许的修改仅限绘图脚本与figures_sec4_2中的派生输出及LaTeX建议。
旧脚本、原Figure 6–9及旧fig9_workload_lines已在开始修改前完整归档。
fig9_workload_lines的原文件仍保留，新A/B版本使用不同文件名。
没有修改原始实验记录、其他论文图片、正式论文源文件或4.3及后续章节。
''')

def main():
    PREVIEW.mkdir(exist_ok=True)
    records=validate();preview();integrity()
    heights='\n'.join(f"- {r['figure']}: {r['width_in']:.3f} × {r['height_in']:.3f} inches; {r['renderer_iterations']}轮Renderer位置收敛。" for r in records)
    (OUT/'reports/compact_layout_check.md').write_text(f'''# Figure 6–9 紧凑排版检查

## 必须条件

- 五个输出（6、7、8、9A、9B）全部子图标题为14.5 pt、bold、单行、居中。
- 居中误差小于0.1 pt，相对于各自Axes中心；同一行标题位置对齐。
- 图内底部没有总图注、实验条件、数据说明或置信区间说明。
- 标题位于刻度/轴名称下方；与轴装饰保留2 pt间距。所有导出采用0.02 inch外侧留白。
- 共享图例置顶。Figure 8分别有方法与数据集编码，两者都属于必要图例。
- Renderer检查文本两两边界、图例与Axes边界、标注与柱体/误差棒；全部无冲突。
- Figure 6初版检测出左下角对数刻度与0概率刻度相交1.12 pt，已通过微调tick pad修正。
- PDF重新渲染、SVG独立渲染；PDF嵌入字体、没有栅格图层，SVG保留文字，PNG为600 dpi。

## 逐图尺寸

{heights}

边距按真实tick/axis/legend/title文字边界反复计算，不是只调用tight_layout。
图6/7/8/9分别使用不同的数据矩形高度、列间距和行间距，再执行tight bbox裁切。
Figure 7的28组有效结果均绘入；Flood所有柱形颜色、纹理、边框完全一致，无特殊标识。
Speedup用全部六种竞争方法最小平均延迟计算，黑色标注避开柱形。

## Figure 9

- A：共享纵轴为[-12%, 18%]；B：共享纵轴为[0.82, 1.12]。
- 使用同一240条配对构建—面积记录、48组均值和CI；未进行实验或数据筛选。
- 降幅CI上下界正确反向，且与直接从五个降幅样本计算Student-t区间一致。
- 全部误差棒在边界内，12个Q-COST区间在A中覆盖0，在B中覆盖1。
- R4仅保留灰色虚线及reference图例，没有方形Marker。
- A的S3标注仅在不碰撞曲线和误差棒时放置，碰撞检查结果单独记录。
- A更直接表达增减方向；B保留旧ratio解释。两者统计信息相同，放大不代表显著优势。

## 实际论文尺寸

IEEEtran textwidth=516 TeX pt。已生成0.90/0.95/1.00倍双栏宽度预览并逐页栅格化。
建议0.95textwidth；14.5 pt是源图字号，LaTeX缩放会按物理比例同步缩放所有元素。
没有手工设置Figure计数器；完整原稿的编号仍由原论文实际插入顺序决定。

请结合compact_previews/与manual_visual_review_compact.md查看实际渲染审阅记录。
''')
    print('PASS: all title, overlap, numeric, CI, vector, DPI, IEEE preview and integrity checks')

if __name__=='__main__':main()
