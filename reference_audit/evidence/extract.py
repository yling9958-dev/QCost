from pathlib import Path
import re, json, hashlib, unicodedata
import pymupdf

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reference_audit'/'evidence'
tex=(ROOT/'IEEE-conference-template-062824.tex').read_text()
# 保留行数，排除 LaTeX 注释中的旧稿与模板示例。
active='\n'.join(re.split(r'(?<!\\)%',line)[0] for line in tex.splitlines())
start=active.index(r'\begin{thebibliography}')
end=active.index(r'\end{thebibliography}')
bib=active[start:end]
refs=[]
matches=list(re.finditer(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}',bib))
for i,m in enumerate(matches):
    raw=bib[m.end():matches[i+1].start() if i+1<len(matches) else len(bib)].strip()
    title=re.search(r"``(.*?)''",raw,re.S)
    refs.append(dict(id=i+1,key=m[1],raw_tex=raw,title=' '.join(title[1].split()) if title else '',tex_line=active[:start+m.start()].count('\n')+1))
doc=pymupdf.open(ROOT/'SecPaper_Yaqi-2.pdf')
columns=[]
for pi,page in enumerate(doc):
    for ci,(x0,x1) in enumerate([(0,page.rect.width/2),(page.rect.width/2,page.rect.width)]):
        t=page.get_text(clip=pymupdf.Rect(x0,0,x1,page.rect.height),sort=True)
        columns.append(dict(page=pi+1,column='左' if ci==0 else '右',text=t))
(OUT/'pdf_columns.json').write_text(json.dumps(columns,ensure_ascii=False,indent=2))
full='\n'.join(c['text'] for c in columns)
pdf_bib=full[full.index('REFERENCES')+len('REFERENCES'):]
pm=list(re.finditer(r'^\s*\[(\d+)\]\s',pdf_bib,re.M))
for i,m in enumerate(pm):
    n=int(m[1]); raw=pdf_bib[m.end():pm[i+1].start() if i+1<len(pm) else len(pdf_bib)].strip()
    if n<=len(refs): refs[n-1]['raw_pdf']=' '.join(raw.split())
assert [int(x[1]) for x in pm]==list(range(1,len(refs)+1))
body=active[:start]
sections=list(re.finditer(r'\\(section|subsection)\*?\{([^}]+)\}',body))
citations=[]
for ci,m in enumerate(re.finditer(r'\\cite(?:p|t)?(?:\[[^\]]*\])*\{([^}]+)\}',body),1):
    section=''; sub=''
    for s in sections:
        if s.start()>m.start(): break
        if s[1]=='section': section=' '.join(s[2].split());sub=''
        else:sub=' '.join(s[2].split())
    p0=body.rfind('\n\n',0,m.start())+2
    p1=body.find('\n\n',m.end()); p1=len(body) if p1<0 else p1
    context=' '.join(body[p0:p1].split())
    paragraph=body[p0:p1];rel_start=m.start()-p0;rel_end=m.end()-p0;s0=0;s1=len(paragraph)
    for cut in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])',paragraph):
        if cut.end()<=rel_start:s0=cut.end()
        elif cut.start()>rel_end:s1=cut.start();break
    citations.append(dict(occurrence=f'T{ci:03}',keys=[k.strip() for k in m[1].split(',')],section=section,subsection=sub,tex_line=body[:m.start()].count('\n')+1,context=context,sentence=' '.join(paragraph[s0:s1].split())))
pcites=[]
for c in columns:
    t=c['text'];t=t.split('REFERENCES')[0]
    if c['page']>12: continue
    # 同时支持 [1]–[3]、[1, 2] 和 [1]–[3], [7]。
    pat=r'\[\d+(?:\s*[,–−-]\s*\d+)*\](?:\s*[–−-]\s*\[\d+\])?(?:\s*,\s*\[\d+(?:\s*[,–−-]\s*\d+)*\](?:\s*[–−-]\s*\[\d+\])?)*'
    for m in re.finditer(pat,t):
        token=m[0]; nums=[]
        token=re.sub(r'\]\s*([–−-])\s*\[',r'\1',token)
        for group in re.findall(r'\[([^]]+)\]',token):
            for part in group.split(','):
                pair=re.split(r'[–−-]',part)
                if len(pair)==2:nums.extend(range(int(pair[0]),int(pair[1])+1))
                else:nums.append(int(part))
        pcites.append(dict(occurrence=f'P{len(pcites)+1:03}',page=c['page'],column=c['column'],token=m[0],ids=nums,context=' '.join(t[max(0,m.start()-400):min(len(t),m.end()+220)].split())))
(OUT/'references_extracted.json').write_text(json.dumps(refs,ensure_ascii=False,indent=2))
(OUT/'citations_tex.json').write_text(json.dumps(citations,ensure_ascii=False,indent=2))
(OUT/'citations_pdf.json').write_text(json.dumps(pcites,ensure_ascii=False,indent=2))
print('references:',len(refs),'active LaTeX cite groups:',len(citations),'PDF bracket groups:',len(pcites))
used={k for c in citations for k in c['keys']}
print('uncited:',[r['key'] for r in refs if r['key'] not in used])
print('missing:', sorted(used-{r['key'] for r in refs}))
for c in citations:print(c['occurrence'],c['tex_line'],c['section'],c['subsection'],','.join(c['keys']),c['context'])
