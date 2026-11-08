"""Compile an isolated query runtime; never invoke an index builder."""
from pathlib import Path
import shutil
import subprocess
import os

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'QMF_PostGIS_100M_Repro_20260910'
OUT=Path(os.environ.get('FLOOD_DIAGNOSTIC_ROOT','/var/tmp/qmf-flood-correctness-memfix-20260915'))
def main():
    native=OUT/'native'; extension=OUT/'extension'
    subprocess.run(['cmake','-S',str(BASE/'src/qmap/cpp'),'-B',str(native),'-DCMAKE_BUILD_TYPE=Release',
        '-DQMF_BASELINES=/var/tmp/qmf-paper-protocol-20260911/common/baselines'],check=True)
    subprocess.run(['cmake','--build',str(native),'--target','qmap_runtime','-j','2'],check=True)
    extension.mkdir(exist_ok=True)
    for path in (BASE/'src/postgres').iterdir():
        if path.is_file():shutil.copy2(path,extension/path.name)
    alias=OUT/'repro-source'
    if not alias.exists():alias.symlink_to(BASE,target_is_directory=True)
    subprocess.run(['make','-C',str(extension),'with_llvm=no',
        'PG_CPPFLAGS=-I'+str(alias/'src/qmap/cpp/include'),
        'QMAP_CPP_BUILD_ROOT='+str(native),'QMAP_RUNTIME_INSTALL_DIR='+str(native/'lib')],check=True)
    subprocess.run(['g++','-O3','-DNDEBUG','-march=native','-std=c++17','-I/usr/include/postgresql',
        str(ROOT/'scripts/paper_eval/postgres_full.cpp'),'-lpq','-pthread','-o',str(OUT/'qmf_postgres_full')],check=True)
    # Five temporary C bindings for this one Flood backend. The database's
    # installed functions and existing runtime library are never overwritten.
    sql=(BASE/'src/postgres/qmap_benchmark--1.0.sql').read_text().split('CREATE FUNCTION qmf_range_count')[0]
    sql=sql.replace('CREATE FUNCTION qmap_','CREATE FUNCTION pg_temp.qmap_')
    sql=sql.replace('MODULE_PATHNAME',str(extension/'qmap_benchmark'))
    (OUT/'session_setup.sql').write_text('CREATE TEMP TABLE flood_binding_anchor (unused int);\n'+sql+'\nSET search_path=pg_temp,public;\n')
if __name__=='__main__':main()
