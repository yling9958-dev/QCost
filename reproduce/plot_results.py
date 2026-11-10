#!/usr/bin/env python3
"""Run final original plotting code on retained scalar exports in a fresh output tree."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
GROUPS = dict(section4_2=['7','8','9'], section4_3_4_4=['10','11'],
              section4_5_4_6=['14','15'], revised=['12','13','16'])

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--group', choices=list(GROUPS), default='section4_3_4_4')
    p.add_argument('--figure', nargs='+')
    p.add_argument('--data', type=Path, help='Optional measured scalar exports with the original schema')
    a = p.parse_args()
    figures = a.figure or GROUPS[a.group]
    if any(f not in GROUPS[a.group] + (['6'] if a.group == 'section4_2' else []) for f in figures):
        p.error('Figure is not part of the selected group')
    source = ROOT / 'experiments/plotting' / a.group
    target = a.output.resolve()
    target.mkdir(parents=True, exist_ok=False)
    for directory in source.iterdir():
        if directory.is_dir():
            shutil.copytree(directory, target / directory.name)
    if a.data:
        data_dir = target / ('02_plot_data' if a.group == 'revised' else 'data')
        shutil.copytree(a.data, data_dir, dirs_exist_ok=True)
    for name in ['figures','reports','03_figures','07_reports']:
        (target / name).mkdir(exist_ok=True)
    scripts = target / ('08_reproduce' if a.group == 'revised' else 'scripts')
    if '6' in figures and not (target / 'data/fullscale_latency_observations.csv').is_file():
        p.error('Figure 6 requires the excluded original per-query latency export via --data')
    for figure in figures:
        script = scripts / (f'regenerate_fig{figure}.py' if a.group == 'revised' else f'plot_fig{figure}.py')
        subprocess.run([sys.executable, '-B', str(script)], cwd=target, check=True)

if __name__ == '__main__':
    main()
