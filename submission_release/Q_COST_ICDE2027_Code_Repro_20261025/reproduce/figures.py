#!/usr/bin/env python3
"""Render current paper figures from recorded measurements into a fresh output tree."""
from pathlib import Path
import argparse, os, shutil, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
GROUPS={
 'section4_2':('scripts',[f'plot_fig{i}.py' for i in [6,7,8,9]],['figures','reports']),
 'section4_3_4_4':('scripts',[f'plot_fig{i}.py' for i in [10,11]],['figures','reports']),
 'section4_5_4_6':('scripts',[f'plot_fig{i}.py' for i in [14,15]],['figures','reports']),
 'revised':('08_reproduce',[f'regenerate_fig{i}.py' for i in [12,13,16]],['03_figures','07_reports']),
 'selection':('08_reproduce',['plot_results.py'],['05_figures','06_reports'])}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--groups',nargs='+',choices=list(GROUPS),default=list(GROUPS));a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    for group in a.groups:
        dest=a.output/group
        if dest.exists():raise RuntimeError(f'Use a fresh output directory: {dest}')
        shutil.copytree(ROOT/'plots'/group,dest)
        folder,scripts,outputs=GROUPS[group]
        for name in outputs:(dest/name).mkdir(parents=True,exist_ok=True)
        for script in scripts:
            with (dest/outputs[-1]/(script+'.log')).open('w') as log:
                subprocess.run([sys.executable,'-B',str(dest/folder/script)],check=True,stdout=log,stderr=subprocess.STDOUT,
                               env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(dest/outputs[-1]/'mplconfig')))
            print(group,script,'PASS',flush=True)
if __name__=='__main__':main()
