#!/usr/bin/env python3
"""Optional download of exact, SHA-verified portable PDF renderer components.

No apt/pip/system installation is performed. This is only needed on a host
matching the existing Ubuntu 22.04 LibreOffice 7.3.7 Writer-only environment.
"""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'validation/portable_renderer'
(R/'debs').mkdir(parents=True,exist_ok=True)
for p in json.loads((R/'package_manifest.json').read_text()):
    dst=R/'debs'/Path(p['Filename']).name
    if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest()==p['SHA256']:
        print('VERIFIED',dst.name);continue
    url='https://mirrors.aliyun.com/ubuntu/'+p['Filename']
    with urllib.request.urlopen(url,timeout=45) as response:data=response.read()
    assert len(data)==int(p['Size'])
    assert hashlib.sha256(data).hexdigest()==p['SHA256']
    dst.write_bytes(data)
    print('DOWNLOADED_AND_VERIFIED',dst.name)
