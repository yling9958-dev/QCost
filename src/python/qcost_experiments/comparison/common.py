"""Portable I/O and the preserved controlled-builder protocol."""
import csv
import json
from pathlib import Path
import torch
from qcost_repro.models import PROJECT_ROOT as ROOT, sha256 as sha

CFG = json.loads((ROOT / 'configs/controlled_build.json').read_text())
LABELS = dict(r4_greedy='R4 Greedy', cost_h1='Cost-H1',
              recursive_exact_h3='Recursive Exact', cpu_qmf_h3='Analytic QMF')

def csvout(path, rows):
    if not rows:
        return
    with Path(path).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def js(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')

def torch_setup():
    torch.set_num_threads(1)
    return torch
