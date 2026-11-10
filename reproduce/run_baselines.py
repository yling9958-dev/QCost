#!/usr/bin/env python3
"""Build/query the retained native baseline adapters on the same prepared workload."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
from qmapli.wg_qmf.point_io import read_points
from qcost_repro.benchmarking import benchmark
from qcost_repro.models import sha256

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--points', type=Path, required=True)
    p.add_argument('--queries', type=Path, required=True)
    p.add_argument('--external', type=Path, required=True, help='fetch_baselines.py output directory')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--methods', nargs='+', choices=['rtree', 'bmtree', 'lisa', 'flood', 'tsunami', 'lmsfc'],
                   default=['rtree', 'lisa', 'flood', 'tsunami', 'lmsfc'])
    p.add_argument('--bmtree-model', type=Path)
    p.add_argument('--repetitions', type=int, default=5)
    a = p.parse_args()
    if 'bmtree' in a.methods and (a.bmtree_model is None or not a.bmtree_model.is_file()):
        p.error('BMTree requires the real official trained model export; use export_bmtree_model.py')
    for name, row in json.loads((ROOT / 'configs/baseline_dependencies.json').read_text()).items():
        target = a.external / 'baselines' / name
        actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != row['revision']:
            raise ValueError('Baseline source revision mismatch: ' + name)
    a.output.mkdir(parents=True, exist_ok=False)
    build = a.output / 'native'
    subprocess.run(['cmake', '-S', str(ROOT / 'src/baselines'), '-B', str(build),
                    '-DQMF_BASELINES=' + str((a.external / 'baselines').resolve())], check=True)
    subprocess.run(['cmake', '--build', str(build), '--parallel', '2'], check=True)
    points, ids = read_points(a.points)
    rows = []
    for method in a.methods:
        output = a.output / method
        output.mkdir()
        args = [str(build / 'bin/qmap_build_index'), '--method', method,
                '--points', str(a.points), '--train-queries', str(a.queries / 'train.csv'),
                '--validation-queries', str(a.queries / 'validation.csv'),
                '--index', str(output / 'index.idx'), '--output', str(output / 'build.csv')]
        if a.bmtree_model:
            args += ['--bmtree-model', str(a.bmtree_model)]
        subprocess.run(args, check=True)
        rows.append(benchmark(build / 'lib/libqmap_runtime.so', output / 'index.idx', method,
                              points, ids, a.queries, output, a.repetitions))
    result = dict(status='PASS', methods=rows, points_sha256=sha256(a.points),
                  historical_paper_measurements=False,
                  adapters='Original research adapters and recorded compatibility patch; see README limitations')
    (a.output / 'baseline_results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
