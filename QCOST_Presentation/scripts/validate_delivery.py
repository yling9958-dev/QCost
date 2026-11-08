#!/usr/bin/env python3
"""Validate editable chart workbooks, displayed numbers, fonts, and source hashes."""
from pathlib import Path
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import re
import zipfile
import pandas as pd
import pymupdf
from lxml import etree
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
V=ROOT/'validation'
checks=[]
def check(name,ok,detail=''):
    checks.append({'Check':name,'Passed':bool(ok),'Detail':str(detail)})
    if not ok:raise AssertionError((name,detail))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def norm(s):return re.sub(r'\s+','',str(s))

expected=json.loads((ROOT/'data/native_chart_data.json').read_text())
ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
with zipfile.ZipFile(ROOT/'Q-COST_ICDE_Research_Progress_CN.pptx') as z:
    for idx,chart in enumerate(expected,1):
        xml=etree.fromstring(z.read(f'ppt/charts/chart{idx}.xml'))
        actual_series=xml.xpath('//c:ser',namespaces=ns)
        check(f'chart{idx}: series count',len(actual_series)==len(chart['series']))
        wb=load_workbook(io.BytesIO(z.read(f'ppt/embeddings/Microsoft_Excel_Sheet{idx}.xlsx')),read_only=True,data_only=True)
        rows=list(wb.active.values)
        check(f'chart{idx}: editable categories',[str(r[0]) for r in rows[1:]]==chart['categories'])
        for j,(name,values) in enumerate(chart['series']):
            sx=actual_series[j]
            cached=[float(v) for v in sx.xpath('./c:val//c:pt/c:v/text()',namespaces=ns)]
            workbook=[r[j+1] for r in rows[1:]]
            check(f'chart{idx}/{name}: label',rows[0][j+1]==name)
            check(f'chart{idx}/{name}: cached values',len(values)==len(cached) and all(math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-13) for a,b in zip(values,cached)))
            check(f'chart{idx}/{name}: embedded workbook',all(math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-13) for a,b in zip(values,workbook)))

doc=pymupdf.open(ROOT/'Q-COST_ICDE_Research_Progress_CN.pdf')
slides=json.loads((ROOT/'notes/slide_manifest.json').read_text())
for slide,page in zip(slides,doc):
    t=norm(page.get_text())
    check(f'page{slide["number"]}: title',norm(slide['title']) in t)
    check(f'page{slide["number"]}: source statement',not slide['source'] or norm(slide['source']) in t)
    check(f'page{slide["number"]}: takeaway',not slide['takeaway'] or norm(slide['takeaway']) in t)
check('main report 8–10 minutes',480<=sum(s['seconds'] for s in slides[:16])<=600)

unique={}
for page in doc:
    for info in page.get_fonts(full=True):unique[info[0]]=info
fonts=[]
for xref,info in unique.items():
    name,ext,kind,data=doc.extract_font(xref)
    fonts.append({'Name':name,'Type':kind,'Embedded':len(data)>0,'Bytes':len(data)})
pd.DataFrame(fonts).to_csv(V/'pdf_font_embedding.csv',index=False)
check('PDF fonts embedded',all(f['Embedded'] for f in fonts),len(fonts))

for manifest,out in [('prior_integrity.csv','prior_integrity_after.csv'),('input_manifest.csv','input_integrity_after.csv')]:
    before=pd.read_csv(V/manifest);rows=[]
    for r in before.to_dict('records'):
        expected_hash=r.get('Expected',r.get('SHA256'))
        actual=sha(r['Path'])
        rows.append({'Path':r['Path'],'Before':expected_hash,'After':actual,'Unchanged':expected_hash==actual})
    pd.DataFrame(rows).to_csv(V/out,index=False)
    check(f'protected sources: {manifest}',all(r['Unchanged'] for r in rows),len(rows))

tables=json.loads((ROOT/'data/native_table_data.json').read_text())
for tab in tables:
    page=norm(doc[tab['slide']-1].get_text())
    for row in tab['rows']:
        for value in row:
            check(f'page{tab["slide"]}: rendered table value {value}',norm(value) in page)

pd.DataFrame(checks).to_csv(V/'delivery_checks.csv',index=False)
packages=['python-pptx','numpy','pandas','matplotlib','openpyxl','PyMuPDF','Pillow','fonttools','lxml']
versions={p:importlib.metadata.version(p) for p in packages}
(ROOT/'requirements.txt').write_text('\n'.join(f'{p}=={v}' for p,v in versions.items())+'\n')
env={'Python':platform.python_version(),'Platform':platform.platform(),'Packages':versions,
     'Font':'Noto Sans CJK SC','Renderer':'LibreOffice 7.3.7, locally copied core + extracted Impress/Draw',
     'SystemPackagesInstalled':False,'BenchmarkExecuted':False,'DataSource':'24 verified Excel worksheets'}
(V/'environment.json').write_text(json.dumps(env,ensure_ascii=False,indent=2))
print(json.dumps({'Checks':len(checks),'Passed':sum(x['Passed'] for x in checks),'FontCount':len(fonts),'SourcesUnchanged':True},ensure_ascii=False))
