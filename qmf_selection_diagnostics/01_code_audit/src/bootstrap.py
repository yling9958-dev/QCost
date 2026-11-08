from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'vendor/python'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'logs/matplotlib'))
def setup(threads=4):
    if not 1<=threads<=4:raise ValueError('threads must be 1..4')
    if hasattr(os,'sched_setaffinity'):
        allowed=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,set(allowed[:threads]))
    for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]=str(threads)
    # Reuse the same installed Torch as the historical Motivation runner.
    import importlib.util
    if importlib.util.find_spec('torch') is None:
        sys.path.append('/home/lingyaqi/.local/lib/python3.10/site-packages')
    import torch
    torch.set_num_threads(threads)
    try:torch.set_num_interop_threads(1)
    except RuntimeError:pass
    return torch
