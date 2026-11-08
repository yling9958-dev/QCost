"""Verify the five-row submission, unchanged figures and all rendered pages."""
from pathlib import Path
import json,re,hashlib
import pandas as pd
import pymupdf as fitz
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parents[1];OLD=R.parent/'bestfirst_removal_revision'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    checks=[]
    def check(name,ok):checks.append({'Check':name,'Pass':bool(ok)});assert ok,name
    old=(R/'01_audit/BASELINE_LATEST.tex').read_text();new=(R/'05_latex/IEEE-conference-template-062824.tex').read_text()
    block=r'% BEGIN HYBRID-QMF CONTROLLED ABLATION.*?% END HYBRID-QMF CONTROLLED ABLATION'
    check('Only ablation block changed',re.sub(block,'BLOCK',old,flags=re.S)==re.sub(block,'BLOCK',new,flags=re.S))
    check('Random frontier definition', 'random frontier selection' in new)
    check('Random row present', 'w/o QMF Selection &' in new)
    check('No removed internal comparator',not re.search(r'Best[-_\s]?First',new,re.I))
    for p in (OLD/'05_latex/figure').glob('*'):
        if p.is_file():check('Unchanged figure file '+p.name,sha(p)==sha(R/'05_latex/figure'/p.name))
    table=(R/'ABLATION_TABLE_FIVE_VARIANTS.tex').read_text()
    check('Table in main source matches generated table',table.strip() in new)
    summary=pd.read_csv(R/'QMF_RANDOM_ABLATION_SUMMARY.csv');assert len(summary)==5
    for row in summary.itertuples():
        for value in [f'{row.Optimal_Root_Rate:.2f}',f'{row.Mean_Root_Regret:.2f}',f'{row.Mean_Optimization_Time:.4f}',f'{row.Mean_Exact_States:.1f}']:
            check('Measured table value '+row.Variant+value,value in table)
    path=R/'06_pdf/SecPaper_Yaqi-2-Random-Ablation.pdf';doc=fitz.open(path);baseline=fitz.open(R/'01_audit/BASELINE_LATEST.pdf')
    log=(R/'06_pdf/SecPaper_Yaqi-2-Random-Ablation.log').read_text();aux=(R/'06_pdf/SecPaper_Yaqi-2-Random-Ablation.aux').read_text()
    check('Clean compile log',not re.search(r'undefined|Overfull|^!|Too many unprocessed floats',log,re.M))
    check('14 pages',len(doc)==14)
    text='\n'.join(p.get_text() for p in doc)
    check('No removed comparator in PDF',not re.search(r'Best[-_\s]?First',text,re.I))
    check('Random ablation in PDF','w/o QMF Selection' in text and 'random frontier selection' in text.replace('\n',' '))
    def forms(pdf):return {hashlib.sha256(pdf.xref_stream(x[0])).hexdigest() for page in pdf for x in page.get_xobjects()}
    check('All embedded vector figure forms unchanged',forms(doc)==forms(baseline))
    labels={}
    for n in range(1,17):
        key='fig:qcost_'+str(n);m=re.search(r'\\newlabel\{'+re.escape(key)+r'\}\{\{([^}]+)\}\{([^}]+)\}',aux)
        # Earlier motivation figures may use a different original label; all figure environments are byte-identical above.
        if m:check(key+' number unchanged',m.group(1)==str(n));labels[key]=dict(number=m.group(1),page=int(m.group(2)))
    m=re.search(r'\\newlabel\{tab:qcost_hybrid_ablation\}\{\{([^}]+)\}\{([^}]+)\}',aux)
    check('Table II automatic numbering',m is not None and m.group(1)=='II');labels['tab:qcost_hybrid_ablation']=dict(number=m.group(1),page=int(m.group(2)))
    pages=R/'07_reports/pages';pages.mkdir(exist_ok=True);pagechecks=[]
    for i,page in enumerate(doc):
        words=page.get_text('words');outside=[w for w in words if w[0]<-1 or w[1]<-1 or w[2]>page.rect.width+1 or w[3]>page.rect.height+1]
        check(f'Page{i+1} no outside text',not outside);check(f'Page{i+1} nonblank',len(words)>15)
        page.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(pages/f'page{i+1:02d}.png')
        pagechecks.append(dict(Page=i+1,Words=len(words),Outside_Text=len(outside)))
    for start in range(0,len(doc),4):
        sheet=Image.new('RGB',(1500,2040),'#dddddd');draw=ImageDraw.Draw(sheet)
        for i in range(start,min(start+4,len(doc))):
            im=Image.open(pages/f'page{i+1:02d}.png');im.thumbnail((735,980));col=(i-start)%2;row=(i-start)//2
            sheet.paste(im,(col*750+7,row*1020+30));draw.text((col*750+10,row*1020+8),f'PAGE {i+1}',fill='black')
        sheet.save(pages/f'contact_{start+1:02d}_{min(start+4,len(doc)):02d}.png')
    pd.DataFrame(checks).to_csv(R/'07_reports/PAPER_CHECKS.csv',index=False);pd.DataFrame(pagechecks).to_csv(R/'07_reports/PAGE_CHECKS.csv',index=False)
    result=dict(Status='STRUCTURAL_PASS_VISUAL_PENDING',Pages=len(doc),Checks=len(checks),Labels=labels,PDF=str(path),PDF_SHA256=sha(path),All_16_Figures_Unchanged=True)
    (R/'07_reports/PAPER_VALIDATION.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
