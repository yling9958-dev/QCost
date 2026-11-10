#!/usr/bin/env python3
"""Validate the documented Python CLI paths without starting experiments."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    paths = sorted(set(re.findall(r'\breproduce/[A-Za-z0-9_./-]+\.py', (ROOT/'README.md').read_text())))
    rows=[]
    environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for path in paths:
        run=subprocess.run([sys.executable,'-B',str(ROOT/path),'--help'],cwd=ROOT,
                           env=environment,capture_output=True,text=True,timeout=60)
        rows.append(dict(script=path,status='PASS' if run.returncode==0 else 'FAIL',returncode=run.returncode))
        if run.returncode:
            print(run.stderr, file=sys.stderr)
    result=dict(status='PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL',entries=rows,
                scope='Existing README CLI scripts and argument parsers; external data/deployment are not supplied by --help')
    if a.output:
        a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 1)

if __name__=='__main__':
    main()
