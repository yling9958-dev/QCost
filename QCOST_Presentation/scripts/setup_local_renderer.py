#!/usr/bin/env python3
"""Extract matching Ubuntu Impress components locally, without installing packages.

The host has LibreOffice 7.3.7 Writer only. All new renderer files remain inside
validation/portable_renderer. Original system files are copied read-only.
"""
from pathlib import Path
import io
import json
import os
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'validation/portable_renderer'
P=R/'root'
shutil.copytree('/usr/lib/libreoffice',P/'usr/lib/libreoffice',symlinks=False,ignore_dangling_symlinks=True,dirs_exist_ok=True)
shutil.copytree('/etc/libreoffice',P/'etc/libreoffice',symlinks=False,ignore_dangling_symlinks=True,dirs_exist_ok=True)
links=[]
for deb in sorted((R/'debs').glob('*.deb')):
    raw=subprocess.check_output(['dpkg-deb','--fsys-tarfile',str(deb)])
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive.getmembers():
            relative=Path(member.name.lstrip('./'))
            assert '..' not in relative.parts
            dst=P/relative
            if member.isdir():dst.mkdir(parents=True,exist_ok=True)
            elif member.isfile():
                dst.parent.mkdir(parents=True,exist_ok=True)
                dst.write_bytes(archive.extractfile(member).read())
                dst.chmod(member.mode)
            elif member.issym() or member.islnk():links.append((dst,member.linkname,member.islnk()))
# The external drive cannot create symlinks, so resolve them into independent copies.
for dst,target,hard in links:
    original=Path(target)
    src=P/target.lstrip('/') if original.is_absolute() or hard else Path(os.path.normpath(str(dst.parent/target)))
    if src==dst:continue
    if not src.exists() and original.is_absolute():src=original
    if src.exists():
        if src.is_dir():shutil.copytree(src,dst,dirs_exist_ok=True)
        else:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
program=P/'usr/lib/libreoffice/program'
for config in (P/'usr/lib/libreoffice/share/.registry').glob('*.xcd'):
    shutil.copy2(config,P/'etc/libreoffice/registry'/config.name)
for path in program.glob('*rc'):
    if not path.is_file():continue
    try:content=path.read_text()
    except UnicodeDecodeError:continue
    content=content.replace('file:///usr/lib/libreoffice',(P/'usr/lib/libreoffice').as_uri())
    content=content.replace('file:///etc/libreoffice',(P/'etc/libreoffice').as_uri())
    path.write_text(content)
print(program/'soffice')
