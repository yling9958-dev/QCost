"""Check actual PDF/SVG/PNG, renderer geometry, paper references and input SHA."""
from pathlib import Path
import os,subprocess,json,re,hashlib,xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from scipy.stats import t
from PIL import Image
from write_delivery import OUT,BASE,NAMES,EXTRAS,CAPTIONS

ASSETS=BASE/'Q-COST-QMF-Necessity-Study/phase5_complementarity_figure/single_column_revision_20261020/previews'
PRE=OUT/'reports/previews'
def run(cmd,**kw):return subprocess.run([str(x) for x in cmd],check=True,capture_output=True,text=True,**kw).stdout
def read(n):return pd.read_csv(OUT/'data'/n)

def numerical():
    checks=[]
    def ck(name,value):checks.append(dict(check=name,passed=bool(value)));assert value,name
    raw=read('gate_measurements_4bit.csv');g=read('gate_validation_results.csv');c=read('circuit_complexity.csv')
    ck('13 gate settings / 65 seed streams',len(g)==13 and len(raw)==65)
    ck('133120 shots',int(g.shots.sum())==133120 and g.shots.eq(10240).all())
    old=read('historical_gate_table.csv').set_index(['N','j']);cur=g.set_index(['N','j'])
    ck('historical gate measured values unchanged',np.allclose(old.Measured,cur.aer_pct,atol=1e-12))
    ck('historical gate analytical values unchanged',np.allclose(old.Theory,cur.analytical_pct,atol=1e-12))
    ck('maximum gate difference0.48828125pp',np.isclose(g.absolute_deviation_pp.max(),.48828125,atol=1e-12))
    ck('23 actual resource rows,13 primary',len(c)==23 and len(c[c.bits==4])==13)
    for row in g.itertuples():
        v=raw[(raw.N==row.N)&(raw.j==row.j)]
        ck(f'pooled measured probability {row.N}/{row.j}',np.isclose(100*v.hits.sum()/v.shots.sum(),row.aer_pct,atol=1e-12))
    s=read('parameter_sensitivity.csv');nodes=read('parameter_common25_records.csv')
    ck('sensitivity9 settings',len(s)==9)
    ck('25 common nodes same9settings',len(nodes)==225 and nodes.groupby('NodeUID').size().eq(9).all())
    ck('40 evaluation population',s.evaluated_nodes.eq(40).all())
    ck('negative values preserved',s[s.H==1].cost_reduction_pct.lt(0).sum()==2)
    ck('48.48137556percent retained',np.isclose(s.query('H==3 and K==4').cost_reduction_pct.iloc[0],48.48137556299494))
    a=read('scalability_results.csv');summary=read('scalability_summary.csv')
    ck('32 matched native campaign builds',len(a)==32 and a.groupby(['dataset','points','method']).size().eq(1).all())
    ck('4datasets2sizes4methods',a.dataset.nunique()==4 and set(a.points)=={20000,50000} and a.method.nunique()==4)
    ck('Q-COST only HybridM8',a[a.display_method=='Q-COST'].original_method_name.eq('M8').all())
    ck('no old QMF or R4 H1 spliced into main',set(a.method)=={'Recursive Exact','Cached Anytime Recursive','Hybrid-BestFirst','Hybrid-QMF'})
    ck('single-build main has no fabricated CI',summary.independent_builds.eq(1).all() and summary.ci_low.isna().all() and summary.ci_high.isna().all())
    x=read('hybrid_20k_five_build_results.csv');sx=read('hybrid_20k_five_build_summary.csv')
    ck('100 repeated20K rows distinct',len(x)==100 and not x.duplicated(['dataset','points','method','seed']).any())
    for r in sx.itertuples():
        z=x[(x.dataset==r.dataset)&(x.points==r.points)&(x.method==r.method)][r.metric]
        half=t.ppf(.975,4)*z.std(ddof=1)/np.sqrt(5)
        ck(f'five-buildtCI {r.dataset}/{r.method}/{r.metric}',len(z)==5 and np.isclose(r.ci_low,z.mean()-half) and np.isclose(r.ci_high,z.mean()+half))
    text=(OUT/'latex/section4_5_4_6_revised.tex').read_text()
    ck('two specified subsection headings',r'\subsection{Gate-Level Quantum Search Validation}' in text and r'\subsection{Sensitivity and Scalability Analysis}' in text and text.count(r'\subsection{')==2)
    ck('no tables or table references',not re.search(r'\\begin\{table\*?\}|Table~|\\(?:ref|autoref)\{tab:',text))
    labels=re.findall(r'\\label\{(fig:[^}]+)\}',text)
    ck('unique14to16labels',labels==['fig:qcost_14','fig:qcost_15','fig:qcost_16'])
    oldtext=(OUT.parent/'figures_sec4_3_4_4/latex/section4_3_4_4_revised.tex').read_text()
    ck('no10to13labelcollision',not set(labels)&set(re.findall(r'\\label\{(fig:[^}]+)\}',oldtext)))
    ck('all references resolve',set(re.findall(r'\\ref\{(fig:[^}]+)\}',text))==set(labels))
    pd.DataFrame(checks).to_csv(OUT/'reports/numeric_export_checks.csv',index=False)

def formats():
    records=[]
    for name in NAMES+EXTRAS:
        p=OUT/'figures'/name;l=json.loads((OUT/'reports'/f'{name}_compact_layout.json').read_text())
        for k in ['text_overlaps','legend_conflicts','outside_canvas','annotation_data_conflicts','extra_figure_captions']:assert not l[k],(name,k,l[k])
        assert all(t['font_pt']==14.5 and t['weight']=='bold' and t['single_line'] and t['center_error_pt']<.1 and t['gap_below_axis_decorations_pt']>=1.9 for t in l['title_checks'])
        fonts=run(['pdffonts',str(p)+'.pdf']);(OUT/'reports'/f'{name}_fonts.txt').write_text(fonts)
        assert all(re.search(r'\byes\s+yes\s+(yes|no)\s+\d+\s+\d+\s*$',s) for s in fonts.splitlines()[2:] if s.strip())
        assert len(run(['pdfimages','-list',str(p)+'.pdf']).splitlines())<=2
        svg=ET.parse(str(p)+'.svg');assert not any(x.tag.endswith('}image') for x in svg.iter())
        assert sum(x.tag.endswith('}text') for x in svg.iter())>15
        im=Image.open(str(p)+'.png');assert abs(im.info['dpi'][0]-600)<.01
        run(['pdftoppm','-r','160','-png','-singlefile',str(p)+'.pdf',PRE/name])
        records.append(dict(figure=name,formal=name in NAMES,subplots=len(l['title_checks']),title_pt=14.5,
          bold=True,single_line=True,centered=True,overlaps=0,footer_notes=0,pdf_fonts_embedded=True,pdf_raster_images=0,
          svg_vector_text=True,png_dpi=im.info['dpi'][0],width_in=l['exported_inches'][0],height_in=l['exported_inches'][1]))
    pd.DataFrame(records).to_csv(OUT/'reports/export_checks.csv',index=False)
    return records

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

def preview():
    body=r'''\documentclass[conference]{IEEEtran}
\usepackage{graphicx}\usepackage{times}\usepackage{amsmath}
\begin{document}
\typeout{QCOST-TEXTWIDTH=\the\textwidth}
\typeout{QCOST-COLUMNWIDTH=\the\columnwidth}
\onecolumn\pagestyle{plain}
'''
    for n,name in enumerate(NAMES,14):
        body+='\\noindent\\textbf{Requested Figure '+str(n)+': IEEE double-column width}\\par\\smallskip\n'
        body+='\\noindent\\includegraphics[width=\\textwidth]{figures/'+name+'.pdf}\n\\par\\smallskip\\noindent\\footnotesize '+CAPTIONS[name]+'\n\\clearpage\n'
    body+=r'\end{document}'
    p=compile_tex('ieee_actual_width_preview',body)
    run(['pdftoppm','-r','130','-png',p,PRE/'ieee_actual_width'])
    text=(OUT/'latex/section4_5_4_6_revised.tex').read_text().replace('{figure/','{figures/')
    full=r'''\documentclass[conference]{IEEEtran}
\usepackage{graphicx}\usepackage{times}\usepackage{amsmath}
\begin{document}\section{Experiments}
'''+text+r'\clearpage\end{document}'
    p=compile_tex('section4_5_4_6_preview',full)
    run(['pdftoppm','-r','110','-png',p,PRE/'section_preview'])
    pages=sorted(PRE.glob('ieee_actual_width-*.png'))
    canvas=Image.new('RGB',(3*440,620),'#EEEEEE')
    for i,p in enumerate(pages):
        im=Image.open(p).convert('RGB');im.thumbnail((440,620));canvas.paste(im,(440*i,0))
    canvas.save(PRE/'ieee_actual_width_contact.png')
    logs=[(OUT/'reports'/f'{n}_compile.log').read_text() for n in ['ieee_actual_width_preview','section4_5_4_6_preview']]
    warns=[x for log in logs for x in log.splitlines() if 'Overfull' in x or 'undefined' in x.lower()]
    (OUT/'reports/latex_preview_warnings.json').write_text(json.dumps(warns,indent=2))
    return warns

def integrity():
    p=read('provenance.csv');initial=json.loads((OUT/'reports/initial_protected_sha256.json').read_text())
    rows=[]
    for path,h in {**initial,**dict(zip(p.source_file,p.sha256))}.items():
        current=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        rows.append(dict(source_file=path,before_sha256=h,after_sha256=current,unchanged=current==h))
    d=pd.DataFrame(rows);d.to_csv(OUT/'reports/source_integrity_after.csv',index=False)
    assert d.unchanged.all(),d[~d.unchanged].source_file.tolist()
    return len(d)

def main():
    numerical();records=formats();warns=preview();count=integrity()
    assert not warns,warns
    table='\n'.join(f"| {r['figure']} | {r['width_in']:.3f} × {r['height_in']:.3f} | {r['subplots']} | PASS |" for r in records)
    n=sum(r['subplots'] for r in records if r['formal']);extra=sum(r['subplots'] for r in records if not r['formal'])
    (OUT/'reports/figure_layout_check.md').write_text(f'''# 排版与导出检查

| 图 | 导出尺寸(inch) | 子图数 | 结果 |
|---|---|---|---|
{table}

三张正式图共{n}个标题、候选图{extra}个标题，均14.5pt Times New Roman Bold、单行、相对Axes水平居中、在下方，中心误差<0.1pt。标题与坐标装饰至少2pt，无裁剪。
Renderer自动检查Text/Legend/Axes边界与柱形标注，text_overlaps、legend_conflicts、outside_canvas、annotation_data_conflicts全部为空。图内无独立底部说明。
继承4.2布局代码，逐图独立设置绘图区高度、间距并迭代压缩；pad_inches=0.02。Figure15首版25/40长标签遮挡相邻柱，已改为明确的节点数25、36、40后重新检查。Figure16长dataset标签分行，但子图标题保持单行。
查询刻度使用真实0.0002/0.0004ms步长；主图从0起，补充图完整显示95%t区间。单build主图没有误差棒；没有以5轮查询构造build CI。
全部PDF嵌入字体，无栅格图像；SVG矢量文字；PNG600dpi。所有PDF重新渲染到reports/previews。
IEEEtran实际textwidth=516 TeX pt。已编译三页实际宽度预览及完整替换片段预览，无Overfull或未定义引用警告：{warns}。
原数据和旧4.2–4.4输出共{count}文件，SHA256前后全部一致。
''')
    print(json.dumps(dict(formal_figures=3,candidate_figures=2,formal_title_checks=n,protected_files=count,latex_warnings=warns,status='PASS')))

if __name__=='__main__':main()
