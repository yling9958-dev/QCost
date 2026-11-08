#!/usr/bin/env python3
"""Render the actual PPTX, inspect slide boundaries, and create review sheets."""
from pathlib import Path
import collections
import hashlib
import json
import os
import subprocess
import zipfile
import pandas as pd
import pymupdf
from PIL import Image,ImageDraw
from pptx import Presentation

ROOT=Path(__file__).resolve().parents[1]
PPTX=ROOT/'Q-COST_ICDE_Research_Progress_CN.pptx'
PDF=PPTX.with_suffix('.pdf')
for name in ['lo_profile','tmp','cache','config']:(ROOT/'validation'/name).mkdir(exist_ok=True)
env=dict(os.environ,TMPDIR=str(ROOT/'validation/tmp'),XDG_CACHE_HOME=str(ROOT/'validation/cache'),
         XDG_CONFIG_HOME=str(ROOT/'validation/config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
portable=ROOT/'validation/portable_renderer/root'
renderer=portable/'usr/lib/libreoffice/program/soffice'
if renderer.exists():
    env['LD_LIBRARY_PATH']=str(portable/'usr/lib/x86_64-linux-gnu')+':'+str(renderer.parent)
cmd=[str(renderer) if renderer.exists() else 'libreoffice','-env:UserInstallation='+(ROOT/'validation/lo_profile').as_uri(),
     '--headless','--convert-to','pdf','--outdir',str(ROOT),str(PPTX)]
result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=60,check=True)
(ROOT/'validation/pdf_export.log').write_text(result.stdout+result.stderr)

doc=pymupdf.open(PDF);assert len(doc)==22
pages=[];tiles=[]
for i,page in enumerate(doc):
    image_path=ROOT/'renders'/f'slide_{i+1:02d}.png'
    page.get_pixmap(matrix=pymupdf.Matrix(1.7,1.7)).save(image_path)
    content=page.get_text()
    spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
    out=[{'text':s['text'],'bbox':s['bbox']} for s in spans if s['bbox'][0]<-.1 or s['bbox'][1]<-.1
         or s['bbox'][2]>page.rect.width+.1 or s['bbox'][3]>page.rect.height+.1]
    pages.append({'Slide':i+1,'Characters':len(content),'TextSpans':len(spans),'OutOfBounds':out,
        'MinFontPt':min((s['size'] for s in spans),default=0),'FontNames':sorted(set(s['font'] for s in spans)),
        'ReplacementCharacter': '\ufffd' in content})
    (ROOT/'renders'/f'slide_{i+1:02d}.txt').write_text(content)
    im=Image.open(image_path).convert('RGB');im.thumbnail((640,360))
    tile=Image.new('RGB',(660,390),'#E9EEF3');tile.paste(im,((660-im.width)//2,24))
    ImageDraw.Draw(tile).text((12,5),f'{i+1:02d}',fill='#223A5E');tiles.append(tile)
for start in range(0,len(tiles),6):
    canvas=Image.new('RGB',(1980,780),'white')
    for j,tile in enumerate(tiles[start:start+6]):canvas.paste(tile,((j%3)*660,(j//3)*390))
    canvas.save(ROOT/'renders'/f'CONTACT_{start//6+1:02d}.png')
(ROOT/'validation/pdf_pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))

prs=Presentation(PPTX);objects=[];table_fonts=[];slide_text=[]
for i,s in enumerate(prs.slides):
    for sh in s.shapes:
        if sh.left<0 or sh.top<0 or sh.left+sh.width>prs.slide_width+100 or sh.top+sh.height>prs.slide_height+100:
            objects.append({'Slide':i+1,'Shape':sh.name,'Problem':'outside slide'})
        if sh.has_text_frame:slide_text.append(sh.text)
        if sh.has_table:
            for row in sh.table.rows:
                for cell in row.cells:
                    for p in cell.text_frame.paragraphs:
                        size=p.font.size.pt if p.font.size else None
                        table_fonts.append({'Slide':i+1,'SizePt':size})
    assert s.has_notes_slide and '【数据口径】' in s.notes_slide.notes_text_frame.text
with zipfile.ZipFile(PPTX) as z:
    count={'Charts':sum(n.startswith('ppt/charts/chart') and n.endswith('.xml') for n in z.namelist()),
           'EmbeddedChartWorkbooks':sum(n.startswith('ppt/embeddings/') and n.endswith('.xlsx') for n in z.namelist()),
           'Notes':sum(n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml') for n in z.namelist())}
native_table=json.loads((ROOT/'data/native_table_data.json').read_text())
assert len(native_table)==sum(sh.has_table for s in prs.slides for sh in s.shapes)
for expected,actual in zip(native_table,[sh.table for s in prs.slides for sh in s.shapes if sh.has_table]):
    for i,row in enumerate([expected['headers']]+expected['rows']):
        for j,v in enumerate(row):assert str(v)==actual.cell(i,j).text
summary={'Slides':len(prs.slides),'PDFPages':len(doc),'NativeTables':len(native_table),**count,
    'OutOfBoundsObjects':objects,'OutOfBoundsPDFSpans':sum(len(p['OutOfBounds']) for p in pages),
    'MainTableMinPt':min(x['SizePt'] for x in table_fonts if x['Slide']<=16),
    'AppendixTableMinPt':min(x['SizePt'] for x in table_fonts if x['Slide']>16),
    'AllSlidesHaveNotes':True,'AllNativeTableCellsMatchData':True,'MinCharacters':min(p['Characters'] for p in pages)}
(ROOT/'validation/structural_checks.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
pd.DataFrame(table_fonts).to_csv(ROOT/'validation/native_table_fonts.csv',index=False)

# Recheck exactly the files read for this presentation.
manifest=pd.read_csv(ROOT/'validation/input_manifest.csv')
after=[]
for row in manifest.to_dict('records'):
    p=Path(row['Path']);h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    after.append({'Path':str(p),'Before':row['SHA256'],'After':h.hexdigest(),'Unchanged':row['SHA256']==h.hexdigest()})
pd.DataFrame(after).to_csv(ROOT/'validation/input_integrity_after.csv',index=False)
assert all(x['Unchanged'] for x in after)
print(json.dumps(summary,ensure_ascii=False,indent=2))
