from pathlib import Path
import requests,json,concurrent.futures,hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
import pymupdf
from bs4 import BeautifulSoup
OUT=Path(__file__).resolve().parent
sources={
'ref06':'https://www.vldb.org/pvldb/vol13/p1162-ferragina.pdf',
'ref09':'https://www.vldb.org/pvldb/vol14/p74-ding.pdf',
'ref10':'https://www.vldb.org/pvldb/vol13/p2341-qi.pdf',
'ref11':'https://www.vldb.org/pvldb/vol16/p2605-gao.pdf',
'ref14':'https://www.vldb.org/pvldb/vol14/p1-marcus.pdf',
'ref16':'https://www.vldb.org/pvldb/vol11/p1661-pandey.pdf',
'ref17':'https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/experiment-learned-index.pdf',
'ref20':'https://www.vldb.org/pvldb/vol17/p3615-kesarwani.pdf',
'ref21':'https://www.vldb.org/conf/1987/P507.PDF',
'ref22':'https://www.vldb.org/conf/1994/P500.PDF',
'ref25':'https://www.vldb.org/pvldb/vol11/p621-qi.pdf',
'ref27':'https://www.vldb.org/pvldb/vol14/p1276-wu.pdf',
'ref28':'https://www.vldb.org/pvldb/vol15/p597-lu.pdf',
'ref35':'https://www.vldb.org/conf/1997/P146.PDF',
'ref37':'https://www.vldb.org/conf/2004/IND4P3.PDF',
'ref38':'https://www.vldb.org/conf/2004/IND4P1.PDF',
'ref41':'https://www.vldb.org/pvldb/vol18/p1278-wu.pdf',
'ref42':'https://www.vldb.org/conf/1997/P186.PDF',
'ref43':'https://www.vldb.org/pvldb/vol14/p3376-ding.pdf',
'ref44':'https://arxiv.org/pdf/quant-ph/9607014',
'ref45':'https://arxiv.org/pdf/quant-ph/9605034',
'ref46':'https://www.microsoft.com/en-us/download/details.aspx?id=52367',
'ref47':'https://snap.stanford.edu/data/loc-gowalla.html',
'ref48':'https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page',
'ref49':'https://www.vldb.org/pvldb/vol16/p2158-li.pdf',
}
def fetch(item):
    name,url=item
    log=dict(name=name,url=url,queried_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    try:
        r=requests.get(url,timeout=45)
        log.update(status_code=r.status_code,final_url=r.url,content_type=r.headers.get('Content-Type'),sha256=hashlib.sha256(r.content).hexdigest())
        if r.ok:
            if r.content[:4]==b'%PDF':
                (OUT/(name+'.pdf')).write_bytes(r.content)
                d=pymupdf.open(stream=r.content,filetype='pdf');log['pages']=len(d)
                txt='\n'.join(f'\n--- SOURCE PAGE {i+1} ---\n'+p.get_text() for i,p in enumerate(d))
            else:
                (OUT/(name+'.html')).write_text(r.text)
                soup=BeautifulSoup(r.text,'html.parser')
                for e in soup(['script','style','nav']):e.decompose()
                txt=soup.get_text('\n',strip=True)
            (OUT/(name+'.txt')).write_text(txt)
    except Exception as e:log['error']=str(e)
    (OUT/(name+'_fetch.json')).write_text(json.dumps(log,ensure_ascii=False,indent=2))
    return log
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for result in ex.map(fetch,sources.items()):print(json.dumps(result),flush=True)
