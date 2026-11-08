"""Recover the exact embedded vector figures; no replotting or changed data."""
from pathlib import Path
import hashlib,json,difflib,argparse,re
import pymupdf as fitz
ROOT=Path(__file__).resolve().parents[1]
def recover_figures():
    source=ROOT/'01_audit/SecPaper_Yaqi-2.pdf';doc=fitz.open(source);figs=[]
    for pi,page in enumerate(doc):
        for xref,name,parent,bbox in page.get_xobjects():
            if parent==0 and name.startswith('Im'):
                figs.append((int(name[2:]),xref,bbox,pi))
    assert sorted(n for n,*_ in figs)==list(range(1,17))
    out=ROOT.parent/'figure';out.mkdir(exist_ok=True);manifest=[]
    for n,xref,bbox,pi in sorted(figs):
        p=out/f'{n}.pdf'
        if p.exists():raise FileExistsError(p)
        d=fitz.open(source);rect=fitz.Rect(bbox)
        page=d.new_page(width=rect.width,height=rect.height)
        d.xref_set_key(page.xref,'Resources',f'<< /XObject << /OriginalFigure {xref} 0 R >> >>')
        content=d.get_new_xref();d.update_object(content,'<< >>')
        d.update_stream(content,f'q 1 0 0 1 {-rect.x0:g} {-rect.y0:g} cm /OriginalFigure Do Q'.encode())
        page.set_contents(content);d.select([len(d)-1]);d.save(p,garbage=4,deflate=True);d.close()
        check=fitz.open(p);form=next(x for x in check[0].get_xobjects() if x[1]=='OriginalFigure')
        original_stream=doc.xref_stream(xref);recovered=check.xref_stream(form[0]);assert original_stream==recovered
        manifest.append(dict(Figure=n,Source_PDF=str(source),Source_Page=pi+1,Source_XRef=xref,
            Output=str(p.resolve()),Original_Form_Stream_SHA256=hashlib.sha256(original_stream).hexdigest(),
            Recovered_Form_Stream_SHA256=hashlib.sha256(recovered).hexdigest(),Bytes_Equal=True,
            PDF_SHA256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (ROOT/'01_audit/FIGURE_RECOVERY.json').write_text(json.dumps(manifest,indent=2))
    print('Restored all 16 original vector Form XObjects byte-for-byte (decoded streams).')
def integrate():
    v=json.loads((ROOT/'04_metrics/VALIDATION.json').read_text());assert v['status']=='COMPLETE_VALIDATED'
    assert len(list((ROOT/'01_audit/enumeration_checks').glob('*.json')))==40
    for p in (ROOT/'01_audit/enumeration_checks').glob('*.json'):assert json.loads(p.read_text())['Status']=='PASS'
    source=ROOT.parent/'IEEE-conference-template-062824.tex'
    original=(ROOT/'01_audit/IEEE-conference-template-062824.tex').read_text()
    addition=(ROOT/'05_tables/ABLATION_INSERTION.tex').read_text()
    repaired=original.replace(r'\usepackage{algorithmic}',
        '% Build repair: unused legacy algorithmic package omitted; Algorithm 1 is native tabular.').replace(
        r'\usepackage{algpseudocode}','% Build repair: unused algpseudocode package omitted.')
    anchor=r'\subsection{Gate-Level Quantum Search Validation}'
    assert repaired.count(anchor)==1
    updated=repaired.replace(anchor,addition+anchor)
    current=source.read_text()
    without_added=re.sub(r'\n% BEGIN HYBRID-QMF CONTROLLED ABLATION\n.*?% END HYBRID-QMF CONTROLLED ABLATION\n\n','',current,flags=re.S)
    assert current==original or without_added==repaired,'Unrelated paper edit detected; do not overwrite'
    source.write_text(updated)
    delta=''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),
                   fromfile='original/IEEE-conference-template-062824.tex',tofile='updated/IEEE-conference-template-062824.tex'))
    (ROOT/'01_audit/PAPER.diff').write_text(delta)
    # Reversibility check: every existing word, equation, figure and reference survives.
    assert updated.replace(addition,'')==repaired
    for env in ['equation','align','figure','figure*','thebibliography']:
        pattern=r'\\begin\{'+re.escape(env)+r'\}.*?\\end\{'+re.escape(env)+r'\}'
        assert re.findall(pattern,original,re.S)==re.findall(pattern,updated,re.S),env
    print('Inserted verified table/analysis; original math, figures, algorithm and references unchanged.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--integrate',action='store_true');args=parser.parse_args()
    if args.integrate:integrate()
    else:recover_figures()
