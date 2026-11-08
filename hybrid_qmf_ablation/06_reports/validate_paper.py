from pathlib import Path
import json,re,hashlib
import pymupdf as fitz
ROOT=Path(__file__).resolve().parents[1]
build=ROOT/'06_reports/paper_build'
stem='SecPaper_Yaqi-2-Hybrid-Ablation'
pdf=build/(stem+'.pdf');log=(build/(stem+'.log')).read_text();aux=(build/(stem+'.aux')).read_text()
assert not re.search(r'undefined|^!|Overfull',log,re.M),'Unresolved compilation/overflow issue'
match=re.search(r'\\newlabel\{tab:qcost_hybrid_ablation\}\{\{([^}]+)\}\{([^}]+)\}',aux)
assert match,'Missing table label'
number,page=match.groups();doc=fitz.open(pdf)
streams={}
for pi,p in enumerate(doc):
    for x in p.get_xobjects():
        streams[hashlib.sha256(doc.xref_stream(x[0])).hexdigest()]=pi+1
figures=json.loads((ROOT/'01_audit/FIGURE_RECOVERY.json').read_text())
assert all(x['Original_Form_Stream_SHA256'] in streams for x in figures)
table_page=doc[int(page)-1];text=table_page.get_text()
assert 'Recursive' in text and 'ablation' in text.lower() and 'Full Hybrid-QMF' in text
alltext='\n'.join(p.get_text() for p in doc)
assert 'Hybrid QMF-Inspired Joint-Subtree Optimization' in ' '.join(alltext.replace('-\n','').split())
assert len(re.findall(r'Fig\.\s*\d+\.',alltext))==16
for pi in sorted({int(page)-1,max(0,int(page)-2),min(len(doc)-1,int(page))}):
    doc[pi].get_pixmap(matrix=fitz.Matrix(1.6,1.6)).save(build/f'review_page{pi+1}.png')
original=(ROOT/'01_audit/IEEE-conference-template-062824.tex').read_text()
updated=(ROOT.parent/'IEEE-conference-template-062824.tex').read_text()
add=(ROOT/'05_tables/ABLATION_INSERTION.tex').read_text()
repaired=original.replace(r'\usepackage{algorithmic}',
    '% Build repair: unused legacy algorithmic package omitted; Algorithm 1 is native tabular.').replace(
    r'\usepackage{algpseudocode}','% Build repair: unused algpseudocode package omitted.')
assert updated.replace(add,'')==repaired
before=json.loads((ROOT/'01_audit/protected_before.json').read_text());changed=[]
for path,expected in before.items():
    actual=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual!=expected:changed.append(path)
assert changed==[str((ROOT.parent/'IEEE-conference-template-062824.tex').resolve())],changed
validation=dict(status='STRUCTURAL_PASS_VISUAL_REVIEW_PENDING',pages=len(doc),original_pages=14,table_number=number,
    table_page=int(page),figure13_page=streams[figures[12]['Original_Form_Stream_SHA256']],
    all16figures_content_identical=True,undefined_references=False,overfull_boxes=False,
    original_equations_algorithm_references_preserved=True,protected_files_checked=len(before),
    protected_changes=changed,pdf=str(pdf.resolve()),PDF_SHA256=hashlib.sha256(pdf.read_bytes()).hexdigest())
(ROOT/'06_reports/PAPER_BUILD_VALIDATION.json').write_text(json.dumps(validation,indent=2))
print(json.dumps(validation,indent=2))
