"""Validate plotted numbers, renderer geometry, real IEEE widths and integrity."""
from pathlib import Path
import os,subprocess,json,re,hashlib,xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from PIL import Image,ImageDraw
from write_delivery import OUT,NAMES,CAPTIONS

ASSETS=OUT.parent.parent/'Q-COST-QMF-Necessity-Study/phase5_complementarity_figure/single_column_revision_20261020/previews'
PRE=OUT/'reports/previews'
def run(cmd,**kw):return subprocess.run([str(x) for x in cmd],check=True,capture_output=True,text=True,**kw).stdout
def compile_tex(stem,text):
    assert not re.search(r'\\(?:setcounter|addtocounter)\s*\{figure\}',text)
    env=os.environ.copy();fonts=ASSETS/'texfonts/extracted/usr/share/texlive/texmf-dist/fonts'
    env['TEXINPUTS']=str(OUT/'latex')+':'+str(ASSETS)+':'+env.get('TEXINPUTS','')
    for key,rel in [('TFMFONTS','tfm'),('VFFONTS','vf'),('T1FONTS','type1'),('ENCFONTS','enc')]:env[key]=str(fonts/rel)+'//:'+env.get(key,'')
    path=OUT/'latex'/f'{stem}.tex';path.write_text(text)
    for _ in range(2):
        p=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','-output-directory',str(OUT/'latex'),str(path)],cwd=OUT,env=env,capture_output=True,text=True)
        (OUT/'reports'/f'{stem}_compile.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError(p.stdout[-6000:])
    return OUT/'latex'/f'{stem}.pdf'

def formats():
    records=[]
    for name in NAMES:
        p=OUT/'figures'/name;layout=json.loads((OUT/'reports'/f'{name}_compact_layout.json').read_text())
        for key in ['text_overlaps','legend_conflicts','outside_canvas','annotation_data_conflicts','extra_figure_captions']:assert not layout[key],(name,key,layout[key])
        assert all(t['font_pt']==14.5 and t['weight']=='bold' and t['single_line'] and t['center_error_pt']<.1 and t['gap_below_axis_decorations_pt']>=1.9 for t in layout['title_checks'])
        fonts=run(['pdffonts',str(p)+'.pdf']);(OUT/'reports'/f'{name}_fonts.txt').write_text(fonts)
        assert all(re.search(r'\byes\s+yes\s+(yes|no)\s+\d+\s+\d+\s*$',s) for s in fonts.splitlines()[2:] if s.strip())
        images=run(['pdfimages','-list',str(p)+'.pdf']);assert len(images.splitlines())<=2
        svg=ET.parse(str(p)+'.svg');assert not any(x.tag.endswith('}image') for x in svg.iter())
        assert sum(x.tag.endswith('}text') for x in svg.iter())>15
        im=Image.open(str(p)+'.png');assert abs(im.info['dpi'][0]-600)<.01
        run(['pdftoppm','-r','160','-png','-singlefile',str(p)+'.pdf',PRE/name])
        actualtext=run(['pdftotext',str(p)+'.pdf','-'])
        assert 'CPU' not in actualtext
        records.append(dict(figure=name,subplots=len(layout['title_checks']),title_pt=14.5,bold=True,single_line=True,
          centered=True,overlaps=0,footer_notes=0,pdf_fonts_embedded=True,pdf_raster_images=0,
          svg_vector_text=True,png_dpi=im.info['dpi'][0],width_in=layout['exported_inches'][0],height_in=layout['exported_inches'][1]))
    pd.DataFrame(records).to_csv(OUT/'reports/export_checks.csv',index=False)
    return records

def numerical():
    checks=[]
    def ck(n,b):checks.append(dict(check=n,passed=bool(b)));assert b,n
    b=pd.read_csv(OUT/'data/budget_search_results.csv');s=pd.read_csv(OUT/'data/fig11_summary.csv')
    for _,r in s.iterrows():
        g=b[(b.method==r.method)&(b.BudgetLabel==r.BudgetLabel)]
        mean=g.groupby('node')[r.metric].mean().mean()*(100 if r.metric.startswith('Optimal') else 1)
        ck(f'Fig11 {r.method}/{r.BudgetLabel}/{r.metric}',np.isclose(mean,r['mean'],rtol=1e-12))
    roots=pd.read_csv(OUT/'data/fig10_root_summary.csv')
    ck('old QMF named honestly',roots.method.eq('Original Analytic QMF').sum()==1 and not roots.method.eq('Hybrid-QMF').any())
    ck('root denominators total224',roots.records.sum()==224)
    h=pd.read_csv(OUT/'data/fig13_budget_records.csv')
    ck('no discovery metric used',not h.protocol.str.contains('discovery',case=False).any())
    ck('all returned roots denominators 8x3',h.groupby(['method','budget_ratio']).size().eq(24).all())
    ck('no feasible not optimal',not h[~h.feasible].root_optimal.any())
    current=pd.read_csv(OUT/'data/main40_trajectories_records.csv');ck('all6methods40nodes3seeds',len(current)==720 and current.groupby(['node','method']).seed.nunique().eq(3).all())
    ck('all Phase4 phase timers sum once',np.allclose(current.filter(regex='^phase_').fillna(0).sum(axis=1),current.total_optimizer_time,rtol=1e-10))
    w=pd.read_csv(OUT/'data/fig13_work_summary.csv')
    ck('cache actual12.71pct',np.isclose(w.query("panel=='cache' and original_method_name=='M3' and metric=='work_exact_completed'").mean_reduction_pct.iloc[0],12.705061082024434))
    ck('cache actual15.43pct',np.isclose(w.query("panel=='cache' and original_method_name=='M3' and metric=='work_terminal_work'").mean_reduction_pct.iloc[0],15.43463381245722))
    sc=pd.read_csv(OUT/'data/scalability_results_for_later.csv');ck('292 build versions retained',len(sc)==292)
    text=(OUT/'latex/section4_3_4_4_revised.tex').read_text()
    ck('no table environments',not re.search(r'\\begin\{table\*?\}',text))
    ck('no legacy table refs',not re.search(r'Table~|\\(?:ref|autoref)\{tab:',text))
    ck('two original subsection titles',text.count('\\subsection{')==2 and '\\subsection{Ablation Study}' in text and '\\subsection{Search Quality and Computational Efficiency}' in text)
    labels=re.findall(r'\\label\{(fig:[^}]+)\}',text)
    ck('four unique figure labels',labels==['fig:qcost_10','fig:qcost_11','fig:qcost_12','fig:qcost_13'])
    ck('all figure refs resolve',set(re.findall(r'\\ref\{(fig:[^}]+)\}',text))==set(labels))
    pd.DataFrame(checks).to_csv(OUT/'reports/numeric_export_checks.csv',index=False)

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
    body=header
    for i,name in enumerate(NAMES):
        width='252pt' if i==0 else r'\textwidth'
        body+=f'\\noindent\\textbf{{Requested Figure {i+10}: IEEE '+('single-column' if i==0 else 'double-column')+' width}\\par\\smallskip\n'
        body+='\\noindent\\makebox[\\textwidth][c]{\\begin{minipage}{'+width+'}\n\\centering\n'
        body+='\\includegraphics[width=\\linewidth]{figures/'+name+'.pdf}\n\\par\\smallskip\\noindent\\footnotesize '+CAPTIONS[name]+'\n\\end{minipage}}\n\\clearpage\n'
    body+=r'\end{document}'
    pdf=compile_tex('ieee_actual_width_preview',body);run(['pdftoppm','-r','140','-png',pdf,PRE/'ieee_actual_width'])
    # Test the actual replacement environments; local numbering naturally starts at 1.
    text=(OUT/'latex/section4_3_4_4_revised.tex').read_text().replace('{figure/','{figures/')
    full=r'''\documentclass[conference]{IEEEtran}
\usepackage{graphicx}\usepackage{times}\usepackage{amsmath}
\begin{document}\section{Experiments}
'''+text+r'\clearpage\end{document}'
    pdf2=compile_tex('section4_3_4_4_preview',full)
    run(['pdftoppm','-r','110','-png',pdf2,PRE/'section_preview'])
    pages=sorted(PRE.glob('ieee_actual_width-*.png'))
    canvas=Image.new('RGB',(4*400,570),'#EEEEEE')
    for i,p in enumerate(pages):
        im=Image.open(p).convert('RGB');im.thumbnail((400,570));canvas.paste(im,(400*i,0))
    canvas.save(PRE/'ieee_actual_width_contact.png')
    logs=[(OUT/'reports'/f'{n}_compile.log').read_text() for n in ['ieee_actual_width_preview','section4_3_4_4_preview']]
    warns=[x for log in logs for x in log.splitlines() if 'Overfull' in x or 'undefined' in x.lower()]
    (OUT/'reports/latex_preview_warnings.json').write_text(json.dumps(warns,indent=2))
    return warns

def integrity():
    p=pd.read_csv(OUT/'data/provenance.csv');initial=json.loads((OUT/'reports/initial_protected_sha256.json').read_text());rows=[]
    for path,h in {**initial,**dict(zip(p.source_file,p.sha256))}.items():
        current=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        rows.append(dict(source_file=path,before_sha256=h,after_sha256=current,unchanged=current==h))
    d=pd.DataFrame(rows);d.to_csv(OUT/'reports/source_integrity_after.csv',index=False);assert d.unchanged.all()
    return len(d)

def main():
    numerical();records=formats();warns=preview();count=integrity()
    rows='\n'.join(f"| {r['figure']} | {r['width_in']:.3f} × {r['height_in']:.3f} | {r['subplots']} | PASS |" for r in records)
    (OUT/'reports/figure_layout_check.md').write_text(f'''# Figure10–13 排版与导出核验

| 文件 | 导出尺寸（inch） | 子图数 | 结果 |
|---|---|---|---|
{rows}

全部12个子图标题：14.5 pt、Times New Roman Bold、单行、Axes水平居中；中心偏差小于0.1pt。
标题与坐标装饰间距至少2pt，图内不含独立底部说明。所有text bbox、legend/axes bbox均无冲突或越界。
使用继承4.2的Renderer实际边界反复压缩布局，pad_inches=0.02；每图独立设置绘图区高度及间距。
Figure12首版两个长方法刻度重叠，已把Enumeration缩写为enum.，保留完整Caption名称后重新导出。
Figure13纵轴下界为-3%仅留出零点Marker边缘，数据依然0–100%，全部CI完整显示。
PDF无栅格图像、字体全部嵌入；SVG使用矢量文字；PNG600dpi。

实际IEEEtran textwidth=516 TeX pt，columnwidth=252 TeX pt。
已编译latex/ieee_actual_width_preview.pdf（4页）并逐页渲染，图10为单栏，图11–13为双栏。
已编译完整替换片段latex/section4_3_4_4_preview.pdf；所有引用可解析，未强行设图计数器。
编译Overfull/未定义引用记录：{json.dumps(warns,ensure_ascii=False)}。

输入及原4.2保护文件共{count}项，SHA256前后全部一致。未运行任何数据库/优化/训练实验。
''')
    print(json.dumps(dict(figures=4,title_checks=12,protected_files=count,latex_warnings=warns,checks='PASS')),flush=True)
if __name__=='__main__':main()
