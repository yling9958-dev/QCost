#!/usr/bin/env python3
"""Report dependencies without changing the environment or loading external data."""
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess

def check():
    versions = {}
    for name in ['numpy', 'pandas', 'scipy', 'torch', 'pytest', 'PyYAML', 'qiskit', 'qiskit-aer', 'psycopg2-binary', 'matplotlib']:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    commands = {name: shutil.which(name) for name in ['cmake', 'g++', 'make', 'git', 'patch', 'pg_config', 'psql']}
    native = {}
    for command in ['cmake', 'g++', 'pg_config']:
        if commands[command]:
            native[command] = subprocess.check_output([commands[command], '--version'], text=True).splitlines()[0]
    required = ['numpy', 'pandas', 'scipy', 'torch', 'pytest', 'PyYAML']
    return dict(status='PASS' if all(versions[n] for n in required) and commands['cmake'] and commands['g++'] else 'MISSING_DEPENDENCIES',
                python=platform.python_version(), platform=platform.platform(), packages=versions,
                commands=commands, native_versions=native, cpu_only_supported=True,
                quantum='AVAILABLE' if versions['qiskit'] and versions['qiskit-aer'] else 'OPTIONAL_DEPENDENCY_MISSING')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = check()
    if a.output:
        a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
