from pathlib import Path
import json, requests, re, time, concurrent.futures
from datetime import datetime
from zoneinfo import ZoneInfo
OUT=Path(__file__).resolve().parent
refs=json.loads((OUT/'references_extracted.json').read_text())
def query(r):
    dest=OUT/f'crossref_{r["id"]:02}.json'
    if dest.exists():return r['id'],'cached'
    if r['id'] in [44,46,47,48]:return r['id'],'non-Crossref'
    doi=re.search(r'doi:\s*([^\s]+)',r['raw_tex'])
    url=('https://api.crossref.org/works/'+doi[1].rstrip('.')) if doi else 'https://api.crossref.org/works'
    params={} if doi else {'query.bibliographic':r['title'],'rows':3}
    now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    try:
        resp=requests.get(url,params=params,timeout=45,headers={'User-Agent':'ReferenceAudit/1.0 (academic bibliography verification)'})
        result=dict(ref_id=r['id'],queried_at=now,source='Crossref',request_url=resp.url,status_code=resp.status_code)
        if resp.ok:result['response']=resp.json()
        else:result['error']=resp.text[:1000]
    except Exception as e:result=dict(ref_id=r['id'],queried_at=now,request_url=url,error=str(e))
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if 'response' in result:
        m=result['response']['message'];items=m.get('items',[m])
        brief=[{k:x.get(k) for k in ['title','DOI','author','container-title','published','published-online','published-print','volume','issue','page','article-number','type']} for x in items]
        return r['id'],brief
    return r['id'],result.get('error')
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    for n,res in ex.map(query,refs):print(n,json.dumps(res,ensure_ascii=False),flush=True)
