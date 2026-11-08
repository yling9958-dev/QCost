#!/usr/bin/env python3
"""Export new wrapper measurements without touching retained paper results."""
from pathlib import Path
import argparse, importlib.util, json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    manifest=json.loads((a.runs/'manifest.json').read_text());a.output.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('selection_metrics',ROOT/'code/analysis/analyze_selection.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    nodes={n['Node_ID']:n for n in json.loads((ROOT/'configs/NODE_MANIFEST.json').read_text())}
    rows=[];failures=[]
    for f in sorted(a.runs.glob('*__*.json')):
        x=json.loads(f.read_text())
        if x.get('validation')!='PASS':failures.append(dict(File=str(f),Status=x['Status']));continue
        if manifest['mode']=='selection':
            node=nodes[x['Node_ID']];ref=json.loads((ROOT/node['Reference_File']).read_text())
            for ratio in m.BUDGETS:rows.append(dict(m.row_at(x,node,ref,ratio),Source_File=str(f)))
        else:
            rows.append({k:v for k,v in x.items() if not isinstance(v,(list,dict))})
    d=pd.DataFrame(rows);d.to_csv(a.output/'RAW.csv',index=False)
    if len(d):
        keys=['Dataset','Node_ID','Variant','Protocol'] if manifest['mode']=='ablation' else ['Cohort','Dataset','Node_ID','Method','Budget_Ratio']
        numeric=[c for c in d.select_dtypes(include=['number','bool']).columns if c not in keys+['Seed']]
        node=d.groupby(keys)[numeric].mean();node.to_csv(a.output/'NODE_MEANS.csv')
    (a.output/'COVERAGE.json').write_text(json.dumps(dict(mode=manifest['mode'],rows=len(rows),failed_runs=failures,
        declared_nodes=len(manifest['nodes']),declared_seeds=len(manifest['seeds']),partial_protocol=manifest['truncated'],
        note='New-run export only. A partial run is not the complete paper cohort.'),indent=2))
    print('Wrote',len(rows),'measurement rows; failed runs:',len(failures))
if __name__=='__main__':main()
