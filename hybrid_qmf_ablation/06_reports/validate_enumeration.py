"""Additional offline correctness check; run serially AFTER the timing campaign.

For every fixed node, compare all original direct-enumeration configurations'
root-conditioned minima with the frozen Recursive Exact reference. This uses
the original Figure2 enumerator, independently of the incremental V5 reducer.
"""
from pathlib import Path
import os,sys,json,time,csv,hashlib
ROOT=Path(__file__).resolve().parents[1]
P4=ROOT.parent.parent/'Q-COST-QMF-Necessity-Study/phase4_complementarity_analysis'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'02_code'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from src.bootstrap import setup
setup(1)
import numpy as np
from qmapli.wg_qmf.prior import FrozenR4Prior
from qmapli.wg_qmf.configuration import enumerate_joint_configurations
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs
from src.conditional_state import BL,BP,action_id

def main():
    validation=json.loads((ROOT/'04_metrics/VALIDATION.json').read_text())
    assert validation['status']=='COMPLETE_VALIDATED','Do not run concurrently with formal optimizers'
    cfg=json.loads((P4/'configs/phase4_frozen.json').read_text());model=FrozenR4Prior(P4/'data/r4.pt');rows=[]
    out=ROOT/'01_audit/enumeration_checks';out.mkdir(exist_ok=True)
    for node in cfg['main_nodes']:
        dest=out/(node+'.json')
        if dest.exists():rows.append(json.loads(dest.read_text()));continue
        with np.load(P4/'data/nodes'/node/'input.npz') as z:p,q=z['points'],z['queries']
        start=time.perf_counter()
        universe=enumerate_joint_configurations(p,q,model,depth=3,top_k=4,minimum_fraction=.05,minimum_child_count=256)
        table=evaluate_subtree_costs(universe.configurations,q,beta_leaf=BL,beta_point=BP)
        minima={}
        for plan,cost in zip(universe.configurations,table.costs):
            root=action_id(plan.root_action);minima[root]=min(float(cost),minima.get(root,float('inf')))
        ref=json.loads((P4/'data/references'/f'{node}.json').read_text());tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
        assert set(minima)==set(ref['root_costs'])
        assert all(abs(cost-ref['root_costs'][root])<=tol for root,cost in minima.items())
        row=dict(Node_ID=node,Configurations=universe.size,Direct_Enumeration_Min=float(table.costs.min()),
            Recursive_Exact_Min=ref['optimal_cost'],Root_Conditioned_Minima=minima,Status='PASS',
            Validation_Wall_s=time.perf_counter()-start,Scope='offline correctness only; never pooled as optimizer timing')
        with dest.open('x') as f:json.dump(row,f,indent=2)
        rows.append(row);print(json.dumps(row),flush=True)
    with (ROOT/'01_audit/DIRECT_ENUMERATION_REFERENCE_CHECK.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('PASS: all 40 original enumerations agree with Recursive Exact per root')
if __name__=='__main__':main()
