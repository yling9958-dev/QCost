"""Archive generated artifacts before regeneration; never recurse into archive."""
from pathlib import Path
import datetime, hashlib, json, zipfile
OUT=Path(__file__).resolve().parents[1]
def main():
    a=OUT/'archive';a.mkdir(exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
    path=a/f'previous_delivery_{stamp}.zip';rows=[]
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(OUT.rglob('*')):
            if not f.is_file() or a in f.parents:continue
            data=f.read_bytes();rel=str(f.relative_to(OUT));z.writestr(rel,data)
            rows.append(dict(path=rel,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
    (a/f'previous_delivery_{stamp}_manifest.json').write_text(json.dumps(rows,indent=2))
    print(path,len(rows),'files')
if __name__=='__main__':main()
