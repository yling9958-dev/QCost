"""Reject missing, extra or externally linked package files before execution."""
import hashlib
from pathlib import Path

root=Path(__file__).resolve().parent.parent
expected={}
for line in (root/'MANIFEST.sha256').read_text().splitlines():
    digest,separator,name=line.partition('  ')
    if not separator or len(digest)!=64 or name in expected:
        raise SystemExit('INVALID_MANIFEST_RECORD')
    path=Path(name)
    if path.is_absolute() or '..' in path.parts:
        raise SystemExit('UNSAFE_MANIFEST_PATH')
    expected[name]=digest
actual={}
for path in root.rglob('*'):
    if path.is_symlink(): raise SystemExit('SYMLINK_NOT_ALLOWED: '+str(path))
    if path.is_file() and path.name!='MANIFEST.sha256':
        name=path.relative_to(root).as_posix()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        # The public package is distributed without GeoLife data. Its explicit
        # recovery command may add this one SHA-locked file after extraction.
        if name=='data/frozen/geolife_100m.csv' and name not in expected:
            if path.stat().st_size!=104857576 or digest!='56a07a638db478485ba5e78ff45bc7300987ef45d7d4a319666a5dabbcaa555e':
                raise SystemExit('RECOVERED_DATASET_MISMATCH')
            continue
        actual[name]=digest
if actual!=expected:
    raise SystemExit('ARCHIVE_MANIFEST_MISMATCH (missing, extra or modified file)')
print('ARCHIVE_MANIFEST_PASS=YES; files='+str(len(actual)+1))
