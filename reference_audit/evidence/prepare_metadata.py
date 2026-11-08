from pathlib import Path
import requests,json,concurrent.futures,sys
from datetime import datetime
from zoneinfo import ZoneInfo
OUT=Path(__file__).resolve().parent
choice={2:1,14:2,36:1,45:1}
extras={1:'10.1145/602259.602266',10:'10.14778/3407790.3407829',28:'10.14778/3494124.3494141',25:'10.1145/3187009.3177738'}
records={}
for n in range(1,50):
    if n in [21,22,35,42,44,46,47,48] or n in extras:continue
    data=json.loads((OUT/f'crossref_{n:02}.json').read_text())
    m=data['response']['message'];m=m.get('items',[m])[choice.get(n,0)]
    records[str(n)]=m
def extra(item):
    n,doi=item;url='https://api.crossref.org/works/'+doi
    r=requests.get(url,timeout=40)
    obj=dict(ref_id=n,queried_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),url=url,status_code=r.status_code,response=r.json() if r.ok else r.text[:500])
    (OUT/f'crossref_exact_{n:02}.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    return n,obj['response']['message'] if r.ok else None
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
    for n,m in ex.map(extra,extras.items()):
        if m:records[str(n)]=m
(OUT/'selected_crossref.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
def resolve(item):
    n,m=item;url='https://doi.org/'+m['DOI']
    out=dict(ref_id=int(n),doi=m['DOI'],url=url,queried_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    try:
        r=requests.get(url,timeout=25,allow_redirects=True)
        out.update(status_code=r.status_code,final_url=r.url,history=[{'status':h.status_code,'url':h.url,'location':h.headers.get('Location')} for h in r.history])
        if r.ok and len(r.content)<5000000:
            (OUT/f'doi_{int(n):02}.html').write_text(r.text)
    except Exception as e:out['error']=str(e)
    (OUT/f'doi_{int(n):02}_resolution.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    return out
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    for out in ex.map(resolve,records.items()):print(json.dumps(out),flush=True)
