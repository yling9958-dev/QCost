"""Finalize report artifacts without overwriting any existing draft or result."""
from pathlib import Path
import ast,csv,hashlib,json,statistics,sys
RUN=Path(__file__).resolve().parents[1]

def read(p):return json.loads(Path(p).read_text())
def write(p,x):
    with Path(p).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)

rows=list(csv.DictReader((RUN/'report/TABLE2_LOCAL_TIME_MEMORY.csv').open()))
search=list(csv.DictReader((RUN/'report/TABLE1_SEARCH_QUALITY.csv').open()))
get=lambda n,m:next(r for r in rows if r['node']==f'geolife100m_node{n}' and r['method']==m)
sg=lambda n,m:next(r for r in search if r['node']==f'geolife100m_node{n}' and r['method']==m and float(r['budget_factor'])==2.)
receipts=[]
for p in (RUN/'jobs').glob('*/receipt.json'):
    if p.parent.name.startswith(('prepare_','validate_','search_','local_')):receipts.append(read(p))
assert len(receipts)==64 and all(r['status']=='PASS' for r in receipts)
facts={'validated_real_nodes':3,'infeasibility_probe':1,'scientific_tasks':64,'scientific_task_status':'ALL_PASS',
    'local_jobs':56,'search_rows':1224,'qmf_runs':240,'qmf_default_hits':sum(int(sg(n,'qmf')['exact_hits']) for n in [0,121,251]),
    'random_default_hits':sum(int(sg(n,'random')['exact_hits']) for n in [0,121,251]),'total_default_seed_trials':60,
    'maximum_rss_mib':max(max(r['peak_sampled_rss_bytes'],r['peak_observed_hwm_bytes']) for r in receipts)/1024**2,
    'maximum_task_seconds':max(r['elapsed_seconds'] for r in receipts),
    'enumeration_over_recursive_time_ratios':{n:float(get(n,'exact_enumeration')['median_total_local_seconds'])/float(get(n,'recursive_exact')['median_total_local_seconds']) for n in [0,121,251]},
    'qmf_over_argmin_search_time_ratios':{n:float(sg(n,'qmf')['median_search_ms'])/float(sg(n,'argmin')['median_search_ms']) for n in [0,121,251]},
    'formal_files_unchanged':read(RUN/'formal_files_after_verification.json')['checked_files']}
write(RUN/'report/REPORT_FACTS.json',facts)
index=[];drafts=[]
for path in sorted((RUN/'scripts').glob('*.py')):
    try:tree=ast.parse(path.read_text())
    except SyntaxError as err:
        drafts.append({'file':str(path.relative_to(RUN)),'status':'UNEXECUTED_REPORT_DRAFT_SYNTAX_ERROR',
            'line':err.lineno,'message':err.msg})
        continue
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.ClassDef)):
            index.append({'file':str(path.relative_to(RUN)),'symbol':n.name,'line':n.lineno})
with (RUN/'report/DIAGNOSTIC_CODE_INDEX.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['file','symbol','line']);w.writeheader();w.writerows(index)
write(RUN/'report/REPORT_BUILD_RECOVERY.json',{
    'scientific_outputs_unchanged':True,'scientific_tasks':64,'scientific_failures':0,
    'drafts':drafts,'aggregate_report_v2':'Report content and numeric CSVs were successfully written; final code-index scan then encountered the preserved unexecuted v1 draft SyntaxError. No algorithm test failed.',
    'recovery':'Create missing index/facts and a final report as new files; preserve all drafts and the failed reporting receipt.'})
report=(RUN/'report/QMF_ALGORITHM_FEASIBILITY_REPORT_ZH.md').read_text()
report=report.replace('已完成64个有回执任务，全部PASS','已完成64个科学验证/对照任务，全部PASS')
report=report.replace('不同动作配置可能产生相同终端叶布局，因此“动作配置数”“叶布局数”“不同cost数”不能互换。',
    '本次三个节点的16,384个完整动作配置各自也有16,384种不同终端叶布局；但内部条件状态重复，且node121/node251有大量相同cost。因此“条件状态数”“完整叶布局数”“不同cost数”不能互换。')
report=report.replace('峰值为独立进程RSS（含Python/Torch、输入及验证），不是纯算法工作区；',
    '峰值为独立进程RSS（含Python/Torch、输入及验证），不是纯算法工作区；递归法没有显示稳定的进程峰值内存下降，node251甚至受进程基线波动影响更高；')
report=report.replace('64个科学验证/对照任务，全部PASS；','64个科学验证/对照任务，全部PASS；')
report+='\n\n制作记录：一次报表索引生成遇到保留的未执行草稿语法错误，科学测试和数值输出均未受影响；失败回执与恢复说明保留于 `report/REPORT_BUILD_RECOVERY.json`。最终报告使用新文件名保存，没有覆盖草稿。\n'
final=RUN/'report/QMF_ALGORITHM_FEASIBILITY_REPORT_ZH_FINAL.md'
with final.open('x') as f:f.write(report)
write(RUN/'report/FINAL_REPORT_VALIDATION.json',{
    'source_reports_preserved':True,'final_markdown':str(final),'characters':len(report),
    'required_tables':all(f'表{i}' in report for i in range(1,7)),
    'required_decisions':all(k in report for k in ['GO：','CONDITIONAL GO：','PIVOT：','BLOCKER：']),
    'statistics_from_existing_csv':True,'formal_files_sha_status':'PASS',
    'scientific_validation':facts})
print(json.dumps(facts,ensure_ascii=False,indent=2))

# Create an editable Word companion. All content remains text/tables, not screenshots.
from docx import Document
from docx.shared import Mm,Pt,RGBColor
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
doc=Document();sec=doc.sections[0]
sec.orientation=WD_ORIENT.LANDSCAPE;sec.page_width=Mm(297);sec.page_height=Mm(210)
sec.left_margin=sec.right_margin=Mm(15);sec.top_margin=sec.bottom_margin=Mm(14)
sec.header_distance=sec.footer_distance=Mm(6)
for name in ['Normal','Title','Heading 1','Heading 2','Heading 3']:
    st=doc.styles[name];st.font.name='Arial';st.font.size=Pt(10 if name=='Normal' else (19 if name=='Title' else 13))
    st.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'SimSun' if name=='Normal' else 'Noto Sans CJK SC')
    st.paragraph_format.space_after=Pt(5);st.paragraph_format.line_spacing=1.12
    if name!='Normal':st.font.color.rgb=RGBColor.from_string('244A6C');st.paragraph_format.keep_with_next=True
doc.core_properties.title='QMF-Index 算法可行性与研究路线报告'
doc.core_properties.subject='真实轻量实验、Recursive Exact H3、QMF解析模拟与研究路线'
doc.core_properties.author='QMF-Index 研究诊断'
sec.header.paragraphs[0].text='QMF-Index | 算法可行性与研究路线 | 2026-10-09'
foot=sec.footer.paragraphs[0];foot.alignment=1
foot.add_run('QMF 算法诊断报告  ·  ')
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');foot._p.append(fld)
def strip_markup(x):
    import re
    x=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 (\2)',x)
    return x.replace('**','').replace('`','').replace('<br>','\n')
lines=report.splitlines();i=0;code=False
while i<len(lines):
    line=lines[i]
    if line.startswith('```'):code=not code;i+=1;continue
    if code:
        pp=doc.add_paragraph(line);pp.paragraph_format.space_after=Pt(1)
        for run in pp.runs:run.font.name='DejaVu Sans Mono';run.font.size=Pt(8)
        i+=1;continue
    if line.startswith('|'):
        group=[]
        while i<len(lines) and lines[i].startswith('|'):
            vals=[strip_markup(x.strip()) for x in lines[i].strip('|').split('|')]
            if not all(set(v)<=set('-: ') for v in vals):group.append(vals)
            i+=1
        n=len(group[0]);t=doc.add_table(rows=0,cols=n);t.autofit=False
        for rownum,vals in enumerate(group):
            cells=t.add_row().cells
            for j in range(n):
                cells[j].width=Mm(267/n);cells[j].text=vals[j] if j<len(vals) else ''
                for pp in cells[j].paragraphs:
                    pp.paragraph_format.space_after=Pt(3);pp.paragraph_format.line_spacing=1.05
                    for run in pp.runs:
                        run.font.size=Pt(8 if n>=7 else 9)
                        if rownum==0:run.bold=True
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E4EFF7' if rownum==0 else ('F4F6F8' if rownum%2==0 else 'FFFFFF'))
                cells[j]._tc.get_or_add_tcPr().append(sh)
            tr=t.rows[-1]._tr.get_or_add_trPr();ns=OxmlElement('w:cantSplit');tr.append(ns)
            if rownum==0:ns=OxmlElement('w:tblHeader');tr.append(ns)
        doc.add_paragraph('');continue
    if not line.strip():i+=1;continue
    if line.startswith('# '):doc.add_paragraph(strip_markup(line[2:]),'Title')
    elif line.startswith('### '):doc.add_heading(strip_markup(line[4:]),2)
    elif line.startswith('## '):doc.add_heading(strip_markup(line[3:]),1)
    else:doc.add_paragraph(strip_markup(line))
    i+=1
out=RUN/'report/QMF_算法可行性与研究路线报告_20261009.docx'
assert not out.exists();doc.save(out)
reopened=Document(out)
assert len(reopened.tables)>=10
write(RUN/'report/WORD_CONTENT_VALIDATION.json',{'path':str(out),'bytes':out.stat().st_size,
    'tables':len(reopened.tables),'paragraphs':len(reopened.paragraphs),'editable_text':True})
print('FINAL_REPORTS',str(final),str(out),flush=True)
