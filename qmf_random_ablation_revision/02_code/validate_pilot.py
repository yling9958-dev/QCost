"""Gate formal execution on exactness, one-factor semantics and seeded replay."""
from pathlib import Path
import json,hashlib
import numpy as np
R=Path(__file__).resolve().parents[1]
def main():
    root=R/'03_runs/pilot';manifest=json.loads((root/'manifest.json').read_text())
    records=[json.loads(p.read_text()) for p in root.rglob('*__*[AB]*.json')]
    assert len(records)==36 and all(x['validation']=='PASS' for x in records)
    checks=[]
    def check(name,ok):checks.append({'Check':name,'Pass':bool(ok)});assert ok,name
    index={(x['Node_ID'],x['Seed'],x['Variant_ID'],x['Protocol'],x['Repeat']):x for x in records}
    comparisons=0
    for node in manifest['nodes']:
        for seed in manifest['seeds']:
            full=index[node,seed,'FULL_CONTROL','B',0];random=index[node,seed,'RANDOM','B',0]
            check('Equal exact final cost '+node+str(seed),np.isclose(full['Final_Cost'],random['Final_Cost'],rtol=1e-12))
            common=set(full['conditional_costs'])&set(random['conditional_costs'])
            for state in common:
                a=full['conditional_costs'][state];b=random['conditional_costs'][state]
                check('Conditional cost '+state,(a is None and b is None) or (a is not None and b is not None and np.isclose(a,b,rtol=1e-12)))
                comparisons+=1
            for key in ['RANDOM','FULL_CONTROL']:
                x=index[node,seed,key,'B',0];y=index[node,seed,key,'B',1]
                check('Reproducible seeded trajectory '+node+str(seed)+key,
                    [e['selected_task'] for e in x['events']]==[e['selected_task'] for e in y['events']])
                check('Reproducible final configuration '+node+str(seed)+key,x['stats']['selected_configuration']==y['stats']['selected_configuration'])
            for protocol in ['A','B']:
                x=index[node,seed,'RANDOM',protocol,0];st=x['stats']
                check('Only selector changes '+node+str(seed)+protocol,st['options']==dict(cache=True,feedback=True,strategy='random'))
                check('Same deadline '+node+str(seed)+protocol,x['Time_Budget_s']==index[node,seed,'FULL_CONTROL',protocol,0]['Time_Budget_s'])
                rng=np.random.default_rng(seed)
                for e in x['events']:
                    expected=e['frontier'][int(rng.integers(len(e['frontier'])))]
                    check('Uniform RNG replay '+e['selected_task'],e['strategy']=='uniform' and e['selected_task']==expected)
                check('Incumbent records best known '+node+str(seed)+protocol,
                    not st['incumbent_trace'] or x['Final_Cost']==min(t['cost'] for t in st['incumbent_trace']))
    identity=json.loads((R/'01_audit/OPTIMIZER_SOURCE_IDENTITY.json').read_text())
    check('Frozen solver/cache/feedback/cost sources unchanged',all(x['Unchanged'] for x in identity))
    source=(R/'02_code/src/conditional_state.py').read_text()
    check('Shared legal frontier filter',"return [t for t in self.tasks if not t.started and not t.state.exact and not any(c.exact and c.best is None for c in t.children)]" in source)
    check('Complete pilot results exact',all(x['Status']=='EXACT' and x['Feasible'] and x['Optimal_Root'] for x in records if x['Protocol']=='B'))
    result=dict(Status='PASS',Runs=36,Nodes=2,Seeds=3,Variants=2,Conditional_Comparisons=comparisons,
                Checks=len(checks),Implementation_Version=manifest['code_sha256'],Seed_Replay='Exact selection sequences match in unbudgeted runs; wall-clock cutoff may vary')
    (R/'01_audit/PILOT_CHECKS.json').write_text(json.dumps(checks,indent=2))
    (R/'01_audit/PILOT_PASS.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
