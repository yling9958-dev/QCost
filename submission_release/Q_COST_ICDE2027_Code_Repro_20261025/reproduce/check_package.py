#!/usr/bin/env python3
"""Verify delivered hashes, source syntax, frozen model and input exclusion."""
from pathlib import Path
import ast, csv, hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def main():
    manifest=ROOT/'MANIFEST.sha256'
    if not manifest.exists():raise SystemExit('Missing delivery manifest')
    count=0
    for line in manifest.read_text().splitlines():
        expected,name=line.split('  ',1);p=ROOT/name
        assert p.is_file() and not p.is_symlink(),name
        assert digest(p)==expected,name;count+=1
    for p in ROOT.rglob('*'):
        if not p.is_file():continue
        assert p.suffix.lower() not in ['.npz','.npy','.parquet','.pq','.db','.sqlite','.idx','.bin','.h5','.hdf5','.zip','.tar','.gz','.pyc','.so','.o','.a'],p
        assert not any(x in p.parts for x in ['.git','__pycache__','dataest','data_cache']),p
        if p.suffix=='.py':ast.parse(p.read_text(),filename=str(p))
        if p.suffix=='.sh':subprocess.run(['bash','-n',str(p)],check=True)
        if p.suffix=='.csv':
            with p.open(newline='') as f:columns=set(next(csv.reader(f),[]))
            assert not {'x','y'}.issubset(columns),p
            assert not {'xmin','ymin','xmax','ymax'}.issubset(columns),p
            assert not {'longitude','latitude'}.issubset(columns),p
        if p.suffix=='.pt':assert digest(p)=='0d10709b1440549e2aec605b1b68754aff0e8fbb9d793e0f31a64df9da213b5d',p
    nodes=json.loads((ROOT/'configs/NODE_MANIFEST.json').read_text())
    assert len(nodes)==80 and len({n['Node_ID'] for n in nodes})==80
    assert len([n for n in nodes if n['Cohort']=='Original'])==40
    assert json.loads((ROOT/'configs/seeds.json').read_text())==list(range(2026101100,2026101130))
    for n in nodes:
        assert not Path(n['Input_File']).is_absolute()
        assert digest(ROOT/n['Reference_File'])==n['Reference_SHA256']
    print(json.dumps(dict(status='PASS',manifest_files=count,external_nodes=80,
                         spatial_datasets_included=False,query_workloads_included=False)))
if __name__=='__main__':main()
