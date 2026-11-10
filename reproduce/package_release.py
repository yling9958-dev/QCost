#!/usr/bin/env python3
"""Create a sorted ZIP, content manifest and SHA256, then extract and verify every file."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--validation-root', type=Path, required=True)
    a = p.parse_args()
    from check_release import check
    check()
    manifest = ROOT / 'MANIFEST.sha256'
    files = sorted(f for f in ROOT.rglob('*') if f.is_file() and f != manifest)
    manifest.write_text(''.join(digest(f) + '  ' + f.relative_to(ROOT).as_posix() + '\n' for f in files))
    files = sorted([*files, manifest])
    with zipfile.ZipFile(a.output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(f, ROOT.name + '/' + f.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(a.output) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert len([n for n in names if Path(n).name.lower().startswith('readme')]) == 1
        assert all(n.startswith(ROOT.name + '/') and '..' not in Path(n).parts for n in names)
        extracted = Path(tempfile.mkdtemp(prefix='extracted-', dir=a.validation_root))
        z.extractall(extracted)
    for f in files:
        candidate = extracted / ROOT.name / f.relative_to(ROOT)
        assert candidate.is_file() and digest(candidate) == digest(f), f
    sha = digest(a.output)
    a.output.with_name(a.output.name + '.sha256').write_text(sha + '  ' + a.output.name + '\n')
    a.output.with_suffix('.files.txt').write_text(''.join(ROOT.name + '/' + f.relative_to(ROOT).as_posix() + '\n' for f in files))
    result = dict(status='PASS', zip=str(a.output.resolve()),zip_bytes=a.output.stat().st_size,
                  sha256=sha, files=len(files),uncompressed_bytes=sum(f.stat().st_size for f in files),
                  readme_count=1,crc='PASS',extracted_files_sha256='PASS',extracted_root=str(extracted / ROOT.name))
    (a.validation_root / 'zip_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
