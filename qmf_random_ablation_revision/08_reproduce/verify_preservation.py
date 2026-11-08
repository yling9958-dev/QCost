"""Read-only verification of every file recorded before the presentation revision."""
from pathlib import Path
import hashlib,json,time
R=Path(__file__).resolve().parents[1]
def main():
    before=json.loads((R/'01_audit/PROTECTED_BEFORE.json').read_text())
    changed=[];missing=[];total_bytes=0
    for filename,expected in before.items():
        p=Path(filename)
        if not p.is_file():
            missing.append(filename);continue
        h=hashlib.sha256()
        with p.open('rb') as f:
            while chunk:=f.read(4*1024*1024):h.update(chunk);total_bytes+=len(chunk)
        if h.hexdigest()!=expected:changed.append(filename)
    result=dict(Status='PASS' if not changed and not missing else 'FAIL',
                Files_Checked=len(before),Bytes_Checked=total_bytes,Changed=changed,Missing=missing,
                Checked_At=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    (R/'07_reports/PRESERVATION_CHECK.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2));assert result['Status']=='PASS'
if __name__=='__main__':main()
