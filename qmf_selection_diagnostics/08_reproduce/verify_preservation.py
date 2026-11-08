from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
def main():
    before=json.loads((R/'01_code_audit/PROTECTED_BEFORE.json').read_text());changed=[];missing=[]
    for name,expected in before.items():
        p=Path(name)
        if not p.is_file():missing.append(name);continue
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:changed.append(name)
    result=dict(Status='PASS' if not changed and not missing else 'FAIL',Files=len(before),Changed=changed,Missing=missing)
    (R/'06_reports/PRESERVATION.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert result['Status']=='PASS'
if __name__=='__main__':main()
