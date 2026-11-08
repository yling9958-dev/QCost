"""Check new statistics/table/figure and unchanged historical manuscript content."""
from pathlib import Path
import json,re,hashlib
import pymupdf as fitz
import pandas as pd
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parents[1];OLD=R.parent/'qmf_random_ablation_revision'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    checks=[]
    def check(name,ok):checks.append(dict(Check=name,Pass=bool(ok)));assert ok,name
    baseline=(R/'01_code_audit/BASELINE_LATEST.tex').read_text();source=(R/'07_latex/IEEE-conference-template-062824.tex').read_text()
    insertion=json.loads((R/'06_reports/PAPER_INSERTION.json').read_text())
    check('All baseline text unchanged',source.replace(insertion['Block'],'',1).replace(insertion['Figure_Block']+'\n','',1)==baseline)
    check('No BestFirst reintroduced',not re.search(r'Best[-_\s]?First',source,re.I))
    for p in (OLD/'05_latex/figure').glob('*.pdf'):check('Original figure '+p.name,sha(p)==sha(R/'07_latex/figure'/p.name))
    oldtab=re.search(r'% BEGIN HYBRID-QMF CONTROLLED ABLATION.*?% END HYBRID-QMF CONTROLLED ABLATION',baseline,re.S).group()
    check('Five-row TABLE II exactly preserved',oldtab in source)
    table=(R/'04_tables/QMF_SELECTION_TABLE.tex').read_text();check('Measured Table III inserted verbatim',table.strip() in source)
    build=R/'06_reports/paper_build';pdfpath=build/'SecPaper_Yaqi-2-QMF-Selection.pdf';doc=fitz.open(pdfpath)
    oldpdf=fitz.open(R/'01_code_audit/BASELINE_LATEST.pdf')
    log=(build/'SecPaper_Yaqi-2-QMF-Selection.log').read_text();aux=(build/'SecPaper_Yaqi-2-QMF-Selection.aux').read_text()
    check('No compile error/undefined/overfull',not re.search(r'undefined|Overfull|^!|Too many unprocessed floats',log,re.M))
    text='\n'.join(p.get_text() for p in doc);check('No excluded comparator in PDF',not re.search(r'Best[-_\s]?First',text,re.I))
    check('Table III title appears','QMF SELECTION EFFECTIVENESS' in text.upper())
    def forms(d):return {hashlib.sha256(d.xref_stream(x[0])).hexdigest() for p in d for x in p.get_xobjects()}
    check('Every historical figure embedded stream retained',forms(oldpdf)<=forms(doc))
    labels={}
    for key,expected in [('tab:qcost_hybrid_ablation','II'),('tab:qmf_selection_effectiveness','III'),('fig:qmf_selection_diagnostics','17'),('fig:qcost_11','11'),('fig:qcost_12','12'),('fig:qcost_13','13'),('fig:qcost_16','16')]:
        m=re.search(r'\\newlabel\{'+re.escape(key)+r'\}\{\{([^}]+)\}\{([^}]+)\}',aux)
        check(key+' automatic numbering',m is not None and m.group(1)==expected);labels[key]=dict(Number=m.group(1),Page=int(m.group(2)))
    for stem in ['qmf_selection_original','qmf_selection_validation']:
        im=Image.open(R/'05_figures'/f'{stem}.png');check(stem+' 600dpi',all(abs(x-600)<.02 for x in im.info['dpi']))
        figure=fitz.open(R/'05_figures'/f'{stem}.pdf');check(stem+' vector',all(not p.get_images() for p in figure))
        check(stem+' SVG',(R/'05_figures'/f'{stem}.svg').is_file())
    pages=R/'06_reports/pages';pages.mkdir(exist_ok=True);rows=[]
    for i,page in enumerate(doc):
        words=page.get_text('words');outside=[w for w in words if w[0]<-1 or w[1]<-1 or w[2]>page.rect.width+1 or w[3]>page.rect.height+1]
        check(f'Page{i+1} text inside page',not outside);check(f'Page{i+1} not blank',len(words)>15)
        page.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(pages/f'page{i+1:02d}.png');rows.append(dict(Page=i+1,Words=len(words),Outside=len(outside)))
    for start in range(0,len(doc),4):
        im=Image.new('RGB',(1500,2040),'#dddddd');draw=ImageDraw.Draw(im)
        for j in range(start,min(start+4,len(doc))):
            p=Image.open(pages/f'page{j+1:02d}.png');p.thumbnail((735,980));col=(j-start)%2;row=(j-start)//2
            im.paste(p,(col*750+7,row*1020+30));draw.text((col*750+10,row*1020+8),f'PAGE {j+1}',fill='black')
        im.save(pages/f'contact_{start+1:02d}_{min(start+4,len(doc)):02d}.png')
    pd.DataFrame(checks).to_csv(R/'06_reports/PAPER_CHECKS.csv',index=False);pd.DataFrame(rows).to_csv(R/'06_reports/PAGE_CHECKS.csv',index=False)
    result=dict(Status='STRUCTURAL_PASS_VISUAL_PENDING',Pages=len(doc),Checks=len(checks),Labels=labels,PDF=str(pdfpath),PDF_SHA256=sha(pdfpath))
    (R/'06_reports/PAPER_VALIDATION.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
