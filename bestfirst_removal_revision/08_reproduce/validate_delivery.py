"""Validate paper-only filtering, unmodified measurements and the compiled copy."""
from pathlib import Path
import json,re,hashlib,csv
import numpy as np,pandas as pd
import pymupdf as fitz
from PIL import Image,ImageOps,ImageDraw
R=Path(__file__).resolve().parents[1];Q=R.parent
STEMS=['fig12_configuration_efficiency','fig13_hybrid_effectiveness','fig16_index_scalability']
PAT=re.compile(r'Hybrid[-_\s]?BestFirst|Best[-_\s]?First|w/o\s+QMF\s+Selection',re.I)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    checks=[]
    def check(name,ok):
        checks.append(dict(Check=name,Pass=bool(ok)));assert ok,name
    # Every retained source cell survives export without a numeric change.
    for n in [12,13,16]:
        d=pd.read_csv(R/f'02_plot_data/FIG{n}_REVISED_DATA.csv',float_precision='round_trip')
        check(f'Figure{n}: excluded display method absent',not d.method.str.contains(PAT).any())
        for source,g in d.groupby('Source_File'):
            old=pd.read_csv(source,float_precision='round_trip')
            for row in g.itertuples(index=False):
                original=old.iloc[int(row.Source_Row)-2];values=row._asdict()
                for column in old.columns:
                    a=values[column];b=original[column]
                    check(f'Figure{n}:{source}:{row.Source_Row}:{column}',(pd.isna(a) and pd.isna(b)) or a==b)
    # Original feedback/cache paired ratio recipe, for unchanged panels 13(c,d).
    ab=pd.read_csv(Q/'figures_sec4_3_4_4/data/component_ablation_records.csv')
    work=pd.read_csv(R/'02_plot_data/FIG13_REVISED_DATA.csv')
    for row in work[work.Panel.isin(['c','d'])].itertuples():
        wide=ab.groupby(['node','original_method_name'])[row.metric].mean().unstack().sort_index()
        baseline='M2' if row.Panel=='c' else 'M7';num=wide[row.original_method_name].to_numpy();den=wide[baseline].to_numpy()
        ix=np.random.default_rng(20261020).integers(0,len(wide),(2000,len(wide)))
        lo,hi=np.quantile(num[ix].mean(1)/den[ix].mean(1),[.025,.975])
        check(f'Unchanged paired work {row.Panel}/{row.method}/{row.metric}',np.allclose([num.mean()/den.mean(),lo,hi],[row.mean,row.ci_low,row.ci_high],rtol=1e-13))
    limits=json.loads((R/'02_plot_data/ORIGINAL_AXIS_LIMITS.json').read_text())
    figure_info=[]
    for n,stem in zip([12,13,16],STEMS):
        layout=json.loads((R/'07_reports'/f'{stem}_compact_layout.json').read_text())
        for key in ['text_overlaps','legend_conflicts','outside_canvas','annotation_data_conflicts']:
            check(stem+' '+key,not layout[key])
        im=Image.open(R/'03_figures'/f'{stem}.png');dpi=im.info.get('dpi')
        check(stem+' PNG 600 dpi',dpi is not None and all(abs(x-600)<.02 for x in dpi))
        pdf=fitz.open(R/'03_figures'/f'{stem}.pdf');txt='\n'.join(p.get_text() for p in pdf)
        check(stem+' vector PDF',all(not p.get_images() for p in pdf))
        check(stem+' no excluded PDF label',not PAT.search(txt))
        check(stem+' no excluded SVG label',not PAT.search((R/'03_figures'/f'{stem}.svg').read_text()))
        rendered=json.loads((R/'07_reports'/f'{stem}_rendered_values.json').read_text())
        for panel,values in zip('abcd',rendered):check(stem+panel+' original axis limits',values['ylim']==limits[f'fig{n}'+panel])
        figure_info.append(dict(Figure=n,PNG_DPI=dpi,PNG_Size=im.size,Vector=True,Layout='PASS'))
    # Bar artists contain the source values, not values reconstructed from a picture.
    d12=pd.read_csv(R/'02_plot_data/FIG12_REVISED_DATA.csv');render12=json.loads((R/'07_reports'/f'{STEMS[0]}_rendered_values.json').read_text())
    m12=['Original Recursive Exact','Original Analytic QMF','Cached Anytime Recursive','Hybrid-QMF']
    check('Figure12a actual bars',np.allclose(render12[0]['bars'][0],d12[d12.Panel=='a'].set_index('method').loc[m12]['mean'],rtol=1e-14))
    d16=pd.read_csv(R/'02_plot_data/FIG16_REVISED_DATA.csv');render16=json.loads((R/'07_reports'/f'{STEMS[2]}_rendered_values.json').read_text())
    for panel,render in zip('abcd',render16):
        for method,bars in zip(['Recursive Exact','Cached Anytime Recursive','Hybrid-QMF'],render['bars']):
            actual=d16[d16.Panel.eq(panel)&d16.method.eq(method)].set_index('dataset').loc[['GeoLife','Gowalla','NYC Taxi','Skewed 2D']]['mean']
            check('Figure16 actual bars '+panel+method,np.allclose(bars,actual,rtol=1e-14))
    # All displayed historical performance assertions remain grounded in their original campaign.
    times=d12[d12.Panel.eq('a')].set_index('method')['mean'];check('Historical 13.96% reduction',round(100*(1-times['Hybrid-QMF']/times['Original Analytic QMF']),2)==13.96)
    for method,value in [('Hybrid-QMF',.3644),('Original Analytic QMF',.4235),('Original Recursive Exact',.3754),('Cached Anytime Recursive',.3337)]:check(method+' historical seconds',round(times[method],4)==value)
    raw16=pd.read_csv(Q/'figures_sec4_5_4_6/data/scalability_results.csv');full=raw16[raw16.method.eq('Hybrid-QMF')].set_index(['dataset','points'])
    exact=raw16[raw16.method.eq('Recursive Exact')].set_index(['dataset','points']);bounds={}
    for n in [20000,50000]:
        v=full.xs(n,level='points').build_seconds;bounds[str(n)]=[round(v.min(),2),round(v.max(),2)]
    check('Q-COST build bounds unchanged',bounds=={'20000':[3.48,4.91],'50000':[7.19,11.67]})
    bratio=full.xs(50000,level='points').build_seconds/full.xs(20000,level='points').build_seconds
    qratio=full.xs(50000,level='points').mean_ms/full.xs(20000,level='points').mean_ms
    check('Size growth ratios unchanged',[round(bratio.min(),2),round(bratio.max(),2),round(qratio.min(),2),round(qratio.max(),2)]==[2.07,3.13,1.19,1.70])
    for n,expected in [(20000,6.36),(50000,8.54)]:check('NYC time reduction '+str(n),round(100*(1-full.loc[('NYC Taxi',n),'build_seconds']/exact.loc[('NYC Taxi',n),'build_seconds']),2)==expected)
    for ds,expected in [('GeoLife',1.28),('Gowalla',1.17),('Skewed 2D',1.11)]:check('50K ratio '+ds,round(full.loc[(ds,50000),'build_seconds']/exact.loc[(ds,50000),'build_seconds'],2)==expected)
    source=R/'05_latex/IEEE-conference-template-062824.tex';text=source.read_text()
    check('Latest submission tex excludes method',not PAT.search(text))
    pdfpath=R/'06_pdf/SecPaper_Yaqi-2-NoBestFirst.pdf';paper=fitz.open(pdfpath)
    log=(R/'06_pdf/SecPaper_Yaqi-2-NoBestFirst.log').read_text();aux=(R/'06_pdf/SecPaper_Yaqi-2-NoBestFirst.aux').read_text()
    check('No compile errors/undefined/overflow',not re.search(r'undefined|Overfull|^!|Too many unprocessed floats',log,re.M))
    check('14 pages',len(paper)==14)
    alltext='\n'.join(p.get_text() for p in paper);check('PDF excludes method',not PAT.search(alltext.replace('-\n','')))
    labels={}
    for key,number in [('fig:qcost_12','12'),('fig:qcost_13','13'),('fig:qcost_16','16'),('tab:qcost_hybrid_ablation','II')]:
        m=re.search(r'\\newlabel\{'+re.escape(key)+r'\}\{\{([^}]+)\}\{([^}]+)\}',aux)
        check(key+' numbering',m is not None and m.group(1)==number);labels[key]=dict(number=m.group(1),page=int(m.group(2)))
    # Unaffected figures stay byte-identical in project and embedded vector content.
    stream_hashes={sha_:True for page in paper for x in page.get_xobjects() for sha_ in [hashlib.sha256(paper.xref_stream(x[0])).hexdigest()]}
    recovery=json.loads((Q/'hybrid_qmf_ablation/01_audit/FIGURE_RECOVERY.json').read_text())
    for n in range(1,17):
        if n in [12,13,16]:continue
        check(f'Figure{n} original file',sha(Q/f'figure/{n}.pdf')==sha(R/f'05_latex/figure/{n}.pdf'))
        check(f'Figure{n} original embedded content',recovery[n-1]['Original_Form_Stream_SHA256'] in stream_hashes)
    pages_dir=R/'07_reports/pages';pages_dir.mkdir(exist_ok=True);pagechecks=[]
    for i,page in enumerate(paper):
        words=page.get_text('words');outside=[w[:5] for w in words if w[0]<-1 or w[1]<-1 or w[2]>page.rect.width+1 or w[3]>page.rect.height+1]
        check(f'Page{i+1} no text outside page',not outside);check(f'Page{i+1} nonblank',len(words)>15)
        pix=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2));pix.save(pages_dir/f'page{i+1:02d}.png')
        pagechecks.append(dict(Page=i+1,Words=len(words),Outside_Text=len(outside)))
    for start in range(0,len(paper),4):
        sheet=Image.new('RGB',(1500,2040),'#dddddd');draw=ImageDraw.Draw(sheet)
        for j in range(start,min(start+4,len(paper))):
            im=Image.open(pages_dir/f'page{j+1:02d}.png');im.thumbnail((735,980))
            col=(j-start)%2;row=(j-start)//2;sheet.paste(im,(col*750+7,row*1020+30));draw.text((col*750+10,row*1020+8),f'PAGE {j+1}',fill='black')
        sheet.save(pages_dir/f'contact_{start+1:02d}_{min(start+4,len(paper)):02d}.png')
    pd.DataFrame(checks).to_csv(R/'07_reports/CONSISTENCY_CHECKS.csv',index=False)
    pd.DataFrame(pagechecks).to_csv(R/'07_reports/PAGE_CHECKS.csv',index=False)
    result=dict(Status='STRUCTURAL_PASS_VISUAL_REVIEW_PENDING',Pages=len(paper),Labels=labels,PDF=str(pdfpath),
                PDF_SHA256=sha(pdfpath),Figures=figure_info,Checks=len(checks),Original_Data_Unchanged='separate hash verification')
    (R/'07_reports/VALIDATION.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
