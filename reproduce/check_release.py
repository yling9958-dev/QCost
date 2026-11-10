#!/usr/bin/env python3
"""Validate release paths, syntax, configs, source imports and credential exclusions."""
import argparse
import ast
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
import yaml

FORBIDDEN_PARTS = {'.git','.vscode','.venv','venv','env','__pycache__','.pytest_cache','.mypy_cache',
                   '.ipynb_checkpoints','node_modules','logs','log','build','runs','results','outputs',
                   'dist','external','wandb','lightning_logs'}
FORBIDDEN_SUFFIXES = {'.log','.png','.jpg','.jpeg','.svg','.pdf','.gif','.bmp','.webp','.eps',
                      '.pyc','.pyo','.so','.o','.a','.dll','.exe','.zip','.tar','.gz','.7z','.idx','.npy','.npz'}
SECRET = re.compile(r'AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{28,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
ASSIGNED_SECRET = re.compile(r'''(?i)(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*["'][^"'\n]{8,}["']''')

def check():
    files = sorted(p for p in ROOT.rglob('*') if p.is_file())
    readmes = [p.relative_to(ROOT).as_posix() for p in files if p.name.lower().startswith('readme')]
    assert readmes == ['README.md'], readmes
    checked_python = checked_shell = checked_configs = 0
    for p in files:
        relative = p.relative_to(ROOT)
        assert not p.is_symlink(), 'Release contains a symlink: ' + str(relative)
        assert not (set(relative.parts) & FORBIDDEN_PARTS), relative
        assert not any(part.startswith('.venv') for part in relative.parts), relative
        assert not re.search(r'\.(?:log|stdout|stderr)(?:\.|$)', p.name, re.I), relative
        assert not p.name.startswith('events.out.tfevents.'), relative
        assert p.suffix.lower() not in FORBIDDEN_SUFFIXES, relative
        if p.suffix.lower() in {'.pt'}:
            continue
        text = p.read_text(encoding='utf-8')
        # The scanner's own regular-expression fixture is code, not a credential.
        if p.name != 'check_release.py':
            assert SECRET.search(text) is None, 'Possible credential: ' + str(relative)
            assert ASSIGNED_SECRET.search(text) is None, 'Possible assigned credential: ' + str(relative)
        if p.suffix == '.py':
            ast.parse(text, filename=str(p))
            checked_python += 1
        elif p.suffix == '.sh':
            subprocess.run(['bash','-n',str(p)], check=True)
            checked_shell += 1
        elif p.suffix == '.json':
            json.loads(text)
            checked_configs += 1
        elif p.suffix in {'.yaml','.yml'}:
            yaml.safe_load(text)
            checked_configs += 1
    modules, optional_skipped = [], []
    for path in sorted((ROOT / 'src/python').rglob('*.py')):
        name = path.relative_to(ROOT / 'src/python').with_suffix('').as_posix().replace('/','.')
        if name.endswith('.__init__'):
            name = name[:-9]
        if name.startswith('qmf_quantum') and (importlib.util.find_spec('qiskit') is None or importlib.util.find_spec('qiskit_aer') is None):
            optional_skipped.append(name)
            continue
        importlib.import_module(name)
        modules.append(name)
    from qcost_repro.models import verify_models
    models = verify_models()
    from qcost_repro.frozen_inputs import verify_workloads
    for dataset in ['geolife','gowalla','nyc_taxi','skewed_2d']:
        verify_workloads(dataset)
    nodes = json.loads((ROOT / 'configs/NODE_MANIFEST.json').read_text())
    assert len(nodes) == 80 and sum(n['Cohort']=='Original' for n in nodes) == 40
    for node in nodes:
        assert hashlib.sha256((ROOT / node['Reference_File']).read_bytes()).hexdigest() == node['Reference_SHA256']
    readme = (ROOT / 'README.md').read_text()
    documented_paths = sorted(set(re.findall(r'\b(?:reproduce/[A-Za-z0-9_./-]+\.py|configs/[A-Za-z0-9_./-]+\.(?:json|yaml|txt))', readme)))
    for path in documented_paths:
        assert (ROOT / path).is_file(), 'Missing documented path: ' + path
    return dict(status='PASS', files=len(files), logical_bytes=sum(p.stat().st_size for p in files),
                python_syntax=checked_python, shell_syntax=checked_shell, configs=checked_configs,
                imported_source_modules=len(modules), models=len(models), frozen_node_references=len(nodes),
                frozen_query_workloads=20,
                documented_paths_checked=len(documented_paths),
                optional_modules_skipped=optional_skipped,
                readmes=readmes, sensitive_token_patterns='PASS', excluded_artifacts='PASS',
                note='Pattern scanning cannot establish ownership/licensing; optional native baseline dependencies are checked separately')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = check()
    if a.output:
        a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
