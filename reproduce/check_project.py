#!/usr/bin/env python3
"""Check source completeness, checkpoint loading, and frozen reference identities."""
from pathlib import Path
import argparse
import ast
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
import torch
from qcost_repro.models import verify_models, sha256


def project_files():
    if (ROOT / '.git').exists():
        output = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z'])
        return [ROOT / name for name in output.decode().split('\0') if name]
    return [p for p in ROOT.rglob('*') if p.is_file()
            and not any(part in {'.venv', '__pycache__', '.pytest_cache', 'build'}
                        or part.endswith('.egg-info') for part in p.relative_to(ROOT).parts)]


def check():
    files = project_files()
    readmes = [p.relative_to(ROOT).as_posix() for p in files if p.name.lower().startswith('readme')]
    assert readmes == ['README.md'], readmes
    forbidden = {'logs', 'log', 'plots', 'plot', 'figures', 'figure', 'datasets', 'dataest', 'results'}
    for path in files:
        assert not (set(path.relative_to(ROOT).parts) & forbidden), path
        if path.suffix in {'.csv', '.npz', '.npy', '.parquet', '.log', '.png', '.svg', '.pdf'}:
            raise AssertionError('Generated/data artifact is tracked: ' + str(path))
        if path.suffix != '.pt':
            text = path.read_text(encoding='utf-8')
            assert not re.search('[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', text), path
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    manifest = json.loads((ROOT / 'configs/NODE_MANIFEST.json').read_text())
    assert len(manifest) == len({n['Node_ID'] for n in manifest}) == 80
    for node in manifest:
        assert sha256(ROOT / node['Reference_File']) == node['Reference_SHA256'], node['Node_ID']
    assert sha256(ROOT / 'configs/geolife_plt_order.txt') == '6abad47d6979fb785a388b577583e30923f82b196a4cfe238dc40bba247f5df9'
    models = verify_models()
    assert len(models) == 15
    return dict(status='PASS', project_files=len(files), original_models=len(models),
                frozen_references=len(manifest), readmes=readmes,
                note='Checks files and small inference only; does not rerun full-scale experiments.')


if __name__ == '__main__':
    torch.set_num_threads(1)
    print(json.dumps(check(), indent=2))
