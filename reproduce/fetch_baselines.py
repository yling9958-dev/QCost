#!/usr/bin/env python3
"""Fetch the recorded external baseline revisions into a new, explicit directory."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    dependencies = json.loads((ROOT / 'configs/baseline_dependencies.json').read_text())
    for name, row in dependencies.items():
        target = a.output / 'baselines' / name
        target.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(target)], check=True)
        subprocess.run(['git', '-C', str(target), 'remote', 'add', 'origin', row['url']], check=True)
        subprocess.run(['git', '-C', str(target), '-c', 'http.version=HTTP/1.1',
                        'fetch', '--depth', '1', 'origin', row['revision']], check=True)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', row['revision']], check=True)
        actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
        assert actual == row['revision']
    target = a.output / 'learnedbench-patched'
    shutil.copytree(a.output / 'baselines/learnedbench', target,
                    ignore=shutil.ignore_patterns('.git'))
    patch = ROOT / 'src/baselines/patches/flood-lisa-no-tpie.patch'
    subprocess.run(['patch', '-d', str(target.resolve()), '-p1', '-i', str(patch)], check=True)
    (a.output / 'manifest.json').write_text(json.dumps(dependencies, indent=2) + '\n')
    print(json.dumps(dict(status='PASS', output=str(a.output), revisions=dependencies), indent=2))

if __name__ == '__main__':
    main()
