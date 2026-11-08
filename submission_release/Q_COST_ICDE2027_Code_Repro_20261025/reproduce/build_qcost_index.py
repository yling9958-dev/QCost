#!/usr/bin/env python3
"""Relocatable entry point to the delivered production Q-COST builder."""
from pathlib import Path
import os, sys
ROOT=Path(__file__).resolve().parents[1]
os.environ['REPRO_ROOT']=str(ROOT/'code/fullscale')
os.environ['QMAP_PROJECT_ROOT']=str(ROOT/'code/fullscale')
os.environ.setdefault('QMF_RUNTIME','/var/tmp/qcost-artifact-runtime')
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
sys.path.insert(0,str(ROOT/'code/fullscale/src/common/python'))
from qmapli.wg_qmf.build_static_qw_index import main
from qmapli.repro import install_tree_audit
if __name__=='__main__':
    if '--index' in sys.argv:
        path=Path(sys.argv[sys.argv.index('--index')+1]);path.parent.mkdir(parents=True,exist_ok=True)
        install_tree_audit(path.parent/'tree_decision_manifest.csv')
    raise SystemExit(main())
