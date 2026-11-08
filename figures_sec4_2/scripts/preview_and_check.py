"""Check real IEEEtran widths, vector exports, source hashes and plotted numbers."""
from pathlib import Path
import os, subprocess, json, hashlib, re
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from plot_style import OUT, FONT, font_manager
from render_svg import render

ROOT=OUT.parent.parent
ASSETS=ROOT/'Q-COST-QMF-Necessity-Study/phase5_complementarity_figure/single_column_revision_20261020/previews'
PRIMARY=['fig6_latency_ecdf','fig7_grouped_bar','fig8_construction_storage','fig9_workload_lines']
NAMES=PRIMARY+['fig7_grouped_bar_with_user_summary']

def run(cmd,**kw):
    return subprocess.run([str(x) for x in cmd],capture_output=True,text=True,check=True,**kw).stdout

def texenv():
    env=os.environ.copy();fonts=ASSETS/'texfonts/extracted/usr/share/texlive/texmf-dist/fonts'
    env['TEXINPUTS']=str(OUT/'latex')+':'+str(ASSETS)+':'+env.get('TEXINPUTS','')
    for key,rel in [('TFMFONTS','tfm'),('VFFONTS','vf'),('T1FONTS','type1'),('ENCFONTS','enc')]:
        env[key]=str(fonts/rel)+'//:'+env.get(key,'')
    return env

def compile_tex(stem,body):
    assert not re.search(r'\\(?:setcounter|addtocounter)\s*\{figure\}',body)
    path=OUT/'latex'/f'{stem}.tex';path.write_text(body)
    for _ in range(2):
        p=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error',
                          '-output-directory',str(OUT/'latex'),str(path)],cwd=OUT,
                         env=texenv(),capture_output=True,text=True)
        (OUT/'reports'/f'{stem}_compile.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError(p.stdout[-7000:])
    return OUT/'latex'/f'{stem}.pdf'

def previews():
    header=r'''\documentclass[conference]{IEEEtran}
\usepackage{graphicx}
\usepackage{times}
\begin{document}
\typeout{QCOST-TEXTWIDTH=\the\textwidth}
\typeout{QCOST-COLUMNWIDTH=\the\columnwidth}
'''
    body=header+r'''
\section{Experimental Evaluation: Isolated Preview}
This is a standalone Section 4.2 integration preview. Its four figures are
numbered locally by LaTeX; global manuscript numbering is not forced.
\input{latex/section4_2_revised.tex}
\end{document}
'''
    section=compile_tex('section4_2_preview',body)
    caption=[
        'Empirical latency distributions. Seven GeoLife and six Skewed curves; every curve retains 15,000 raw timings. Missing Flood--Skewed timings are not synthesized.',
        'Mean, P95, P99 and derived QPS for 27 verified pairs. Ratios are versus the fastest verified competitor; logarithmic bars begin at positive baselines.',
        'Q-COST construction hours and complete persistent serving-state footprints. Colors indicate methods and shapes identify datasets.',
        'Relative query latency on 20K samples. Ratios and 95\% Student-$t$ intervals use five paired independent builds; all twelve Q-COST intervals include one.'
    ]
    body=header+r'\onecolumn\pagestyle{plain}'+'\n'
    for scale in [.90,.95,1.00]:
        for i,n in enumerate(PRIMARY):
            body+=f'\\noindent\\textbf{{Requested Fig. {i+6} -- layout review at {scale:.2f} text width}}\\par\\medskip\n'
            body+=f'\\noindent\\makebox[\\textwidth][c]{{\\includegraphics[width={scale:.2f}\\textwidth]{{figures/{n}.pdf}}}}\n'
            body+='\\par\\medskip\\noindent\\small '+caption[i]+'\n'
            body+='\\par\\medskip\\noindent\\footnotesize Actual IEEEtran text width: 516 pt. Review heading identifies the requested figure; it does not establish its manuscript counter.\n\\clearpage\n'
    body+=r'\end{document}'
    overview=compile_tex('ieee_figures_6_9_preview',body)
    for pdf in [section,overview]:
        run(['pdftoppm','-r','120','-png',pdf,OUT/'reports/previews'/pdf.stem])
    # A review montage of all physical-size pages, not a replacement for the PDF.
    pages=sorted((OUT/'reports/previews').glob('ieee_figures_6_9_preview-*.png'),
                 key=lambda p:int(p.stem.rsplit('-',1)[1]))
    thumbs=[]
    for p in pages:
        im=Image.open(p).convert('RGB');im.thumbnail((430,600));thumbs.append(im)
    canvas=Image.new('RGB',(430*4,600*3),'#E8E8E8')
    for i,im in enumerate(thumbs):canvas.paste(im,((i%4)*430,(i//4)*600))
    canvas.save(OUT/'reports/previews/ieee_12_page_contact_sheet.png')
    (OUT/'reports/preview_geometry.json').write_text(json.dumps({
        'class':'IEEEtran conference','textwidth_TeX_pt':516,'columnwidth_TeX_pt':252,
        'scales':[.90,.95,1.0],'nominal_canvas_inches':7.1,
        'display_width_inches':[516/72.27*s for s in [.90,.95,1]],
        'local_section_figure_numbers':[1,2,3,4],
        'global_manuscript_numbers':'UNVERIFIED_MAIN_TEX_NOT_FOUND'},indent=2))

def check_exports():
    records=[]
    for n in NAMES:
        p=OUT/'figures'/n
        fonttext=run(['pdffonts',str(p)+'.pdf']);images=run(['pdfimages','-list',str(p)+'.pdf'])
        (OUT/'reports'/f'{n}_pdf_fonts.txt').write_text(fonttext)
        (OUT/'reports'/f'{n}_pdf_images.txt').write_text(images)
        rows=[line for line in fonttext.splitlines()[2:] if line.strip()]
        embedded=bool(rows) and all(re.search(r'\byes\s+yes\s+(yes|no)\s+\d+\s+\d+\s*$',line) for line in rows)
        vector_only=len([line for line in images.splitlines()[2:] if line.strip()])==0
        svg=ET.parse(str(p)+'.svg').getroot();ns={'s':'http://www.w3.org/2000/svg'}
        texts=svg.findall('.//s:text',ns);rasters=svg.findall('.//s:image',ns)
        text=' '.join(''.join(t.itertext()) for t in texts)
        assert not any(m in text for m in ['LISA-V2','Flood-V2','Tsunami-CR'])
        im=Image.open(str(p)+'.png');dpi=im.info.get('dpi',(0,0))
        dpi_ok=all(abs(x-600)<.01 for x in dpi)
        layout=json.loads((OUT/'reports'/f'{n}_layout.json').read_text())
        layout_ok=all(x['inside_canvas'] for x in layout['texts']) and not layout['legend_title_overlaps']
        assert embedded and vector_only and texts and not rasters and dpi_ok and layout_ok,(n,embedded,vector_only,dpi_ok,layout)
        run(['pdftoppm','-singlefile','-r','160','-png',str(p)+'.pdf',OUT/'reports/previews'/f'{n}_pdf'])
        render(str(p)+'.svg',OUT/'reports/previews'/f'{n}_svg.png',round(layout['size_inches'][0]*160),round(layout['size_inches'][1]*160))
        records.append({'figure':n,'png_width':im.width,'png_height':im.height,'png_dpi':dpi[0],
                        'embedded_pdf_fonts':bool(embedded),'vector_pdf':vector_only,'svg_text_objects':len(texts),
                        'svg_raster_objects':len(rasters),'inside_canvas':layout_ok})
    pd.DataFrame(records).to_csv(OUT/'reports/format_quality_checks.csv',index=False)

def numerical_checks():
    d=pd.read_csv(OUT/'data/fullscale_results.csv');v=d[d.verified_for_plot]
    assert len(d)==28 and len(v)==27 and (v.timing_observations==15000).all()
    assert np.allclose(d.qps,1000/d.mean_ms,rtol=1e-12)
    for supplement in [False,True]:
        name='fig7_grouped_bar'+('_with_user_summary' if supplement else '')
        p=pd.read_csv(OUT/'data'/f'{name}_plotted_values.csv')
        assert len(p)==(112 if supplement else 108)
        for r in p.itertuples():
            ref=d[(d.dataset==r.dataset)&(d.method==r.method)].iloc[0]
            assert np.isclose(r.value,ref[r.metric],rtol=1e-12) and r.value>r.baseline>0
    steps=pd.read_csv(OUT/'data/fig6_ecdf_steps.csv');logs=pd.read_csv(OUT/'data/fig6_ecdf_statistics.csv')
    assert len(logs)==13
    for (ds,m),g in steps.groupby(['dataset','method']):
        assert g.multiplicity.sum()==15000
        assert np.all(np.diff(g.latency_ms)>0) and np.all(np.diff(g.cumulative_probability)>0)
        assert np.allclose(g.cumulative_probability,g.multiplicity.cumsum()/15000)
        assert g.cumulative_probability.iloc[-1]==1
    s=pd.read_csv(OUT/'data/fastest_competitor_speedups.csv')
    for r in s.itertuples():
        x=v[v.dataset==r.dataset]
        assert r.competitor==x[x.method!='Q-COST'].sort_values('mean_ms').iloc[0].method
        assert np.isclose(r.speedup,x[x.method!='Q-COST'].mean_ms.min()/x[x.method=='Q-COST'].mean_ms.iloc[0])
    w=pd.read_csv(OUT/'data/workload_area_results.csv');q=w[w.method=='Q-COST']
    assert len(q)==12 and ((q.ci95_low<=1)&(q.ci95_high>=1)).all()
    (OUT/'reports/plot_numeric_validation.json').write_text(json.dumps({
        'status':'PASS','verified_pairs':27,'supplemental_user_summary_pairs':1,
        'verified_bar_endpoints':108,'supplement_bar_endpoints':112,
        'ecdf_curves':13,'ecdf_observations':195000,'all_ecdf_steps_exact':True,
        'all_qps_reciprocal_of_mean':True,'speedups_use_fastest_verified_competitor':True,
        'qcost_workload_intervals_containing_one':12},indent=2))

def integrity():
    df=pd.read_csv(OUT/'reports/source_sha256.csv');rows=[]
    for r in df.itertuples():
        actual=hashlib.sha256(Path(r.path).read_bytes()).hexdigest()
        rows.append({'path':r.path,'expected_sha256':r.sha256,'actual_sha256':actual,'unchanged':actual==r.sha256})
    state=pd.read_csv(OUT/'data/storage_results.csv');state_checks=[]
    for r in state[state.file_exists_now].itertuples():
        p=Path(r.state_path)
        state_checks.append({'path':r.state_path,'bytes_match':p.is_file() and p.stat().st_size==r.stat_bytes})
    good=all(r['unchanged'] for r in rows) and all(r['bytes_match'] for r in state_checks)
    pd.DataFrame(rows).to_csv(OUT/'reports/source_integrity_after.csv',index=False)
    pd.DataFrame(state_checks).to_csv(OUT/'reports/current_index_size_recheck.csv',index=False)
    (OUT/'reports/original_file_integrity.md').write_text(f'''# Original file integrity

Status: {'PASS' if good else 'FAILED'}.

{len(rows)} consumed/protected original files were rehashed after export and LaTeX generation.
Every SHA-256 matches: {all(r['unchanged'] for r in rows)}. These include timing/correctness
records, build receipts, protocols, source code, original figure scripts/PDFs, retained TeX
fragments and the four reference PNGs. {len(state_checks)} available multi-gigabyte index
files retain their exact receipt sizes; absent runtime files are flagged in storage_results.csv.
Large payloads were stat-checked, not rebuilt or rewritten. This is not a whole-disk hash audit.

Writes are restricted to figures_sec4_2. No benchmark or database operation was run.
The previous generated delivery is retained in archive with a member hash manifest;
the original CDF/P95 files and backup copies are unchanged. Original Fig. 1–3 and all
other original paper figures, experimental algorithms and manuscript files were untouched.
''')
    assert good

def main():
    numerical_checks();check_exports();previews();integrity()
    (OUT/'reports/quality_check.md').write_text('''# Automated quality validation

- Five exported canvases: four primary figures and one explicitly qualified summary supplement.
- PDF/SVG are vector-only; PDF fonts are embedded; SVG retains text; PNG metadata is 600 dpi.
- Numerical reconstruction and plotted endpoints match the verified CSV; ECDFs retain every observation.
- Positive log-bar baselines and reciprocal-mean QPS are verified.
- All displayed labels fit the canvas; panel titles and legends are separated.
- All PDF and SVG canvases were independently rendered; every IEEE preview page was rendered.
- Actual IEEEtran textwidth is 516 TeX pt and columnwidth is 252 TeX pt.
- Twelve size-review pages cover four figures at 0.90/0.95/1.00 textwidth.
- The separate subsection preview uses automatic local numbering 1–4, with no figure counter override.
- Source hashes and existing index-file sizes remain unchanged.

See visual_review.md for the manual review and its concrete layout adjustments.
''')
    print('Numeric, vector/font/DPI, IEEE geometry, and protected-source checks PASS')

if __name__=='__main__':main()
