"""Create an integrity-manifested, deterministic ZIP of the allowlisted artifact."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
HERE=Path(__file__).resolve().parent
ROOT=HERE/'Q_COST_ICDE2027_Code_Repro_20261025'
ARCHIVE=HERE/'Q_COST_ICDE2027_Code_Repro_NoDatasets_20261025.zip'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256')
    assert not any(p.is_symlink() for p in ROOT.rglob('*'))
    (ROOT/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(ROOT).as_posix()}\n' for p in files))
    subprocess.run(['python3','-B',str(ROOT/'reproduce/check_package.py')],check=True)
    files=sorted(p for p in ROOT.rglob('*') if p.is_file())
    with zipfile.ZipFile(ARCHIVE,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9,allowZip64=True) as z:
        for p in files:
            info=zipfile.ZipInfo((Path(ROOT.name)/p.relative_to(ROOT)).as_posix(),date_time=(2026,10,25,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3
            info.external_attr=(0o100755 if p.suffix in ['.py','.sh'] else 0o100644)<<16
            with p.open('rb') as f,z.open(info,'w') as out:
                for b in iter(lambda:f.read(1024*1024),b''):out.write(b)
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(files)
        assert not any(Path(n).is_absolute() or '..' in Path(n).parts for n in z.namelist())
    digest=sha(ARCHIVE)
    ARCHIVE.with_suffix('.zip.sha256').write_text(f'{digest}  {ARCHIVE.name}\n')
    result=dict(status='PASS',archive=str(ARCHIVE),archive_sha256=digest,files=len(files),
                bytes=ARCHIVE.stat().st_size,uncompressed_bytes=sum(p.stat().st_size for p in files),
                datasets_included=False,compressed_integrity='CRC PASS')
    (HERE/'ARCHIVE_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
