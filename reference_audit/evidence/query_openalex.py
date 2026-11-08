import requests,json,concurrent.futures
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
OUT=Path(__file__).resolve().parent
records=json.loads((OUT/'selected_crossref.json').read_text())
def query(item):
 n,m=item;url='https://api.openalex.org/works/https://doi.org/'+m['DOI']
 obj={'ref_id':int(n),'queried_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'url':url}
 try:
  r=requests.get(url,timeout=35);obj['status_code']=r.status_code
  if r.ok:obj['response']=r.json()
  else:obj['error']=r.text[:200]
 except Exception as e:obj['error']=str(e)
 (OUT/f'openalex_{int(n):02}.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
 x=obj.get('response',{});return n,x.get('title'),x.get('publication_year'),[a.get('pdf_url') or a.get('landing_page_url') for a in x.get('locations',[]) if a.get('is_oa')]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
 for res in ex.map(query,records.items()):print(res,flush=True)
