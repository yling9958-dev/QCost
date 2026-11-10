#!/usr/bin/env python3
"""Build the optional PostgreSQL extension in a fresh output tree; no server installation."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
from qcost_repro.index_run import build_native

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    build_native(a.output / 'native')
    extension = a.output / 'extension'
    extension.mkdir()
    for name in ['Makefile','qmap_benchmark.cpp','qmap_benchmark.control','qmap_benchmark--1.0.sql']:
        shutil.copyfile(ROOT / 'src/postgres' / name, extension / name)
    subprocess.run(['make','-C',str(extension), 'with_llvm=no',
        'QMAP_PROJECT_ROOT='+str(ROOT),
        'QMAP_CPP_BUILD_ROOT='+str((a.output/'native').resolve()),
        'QMAP_RUNTIME_INSTALL_DIR='+str((a.output/'native/lib').resolve())], check=True)
    print('Built ' + str(extension / 'qmap_benchmark.so'))

if __name__ == '__main__':
    main()
