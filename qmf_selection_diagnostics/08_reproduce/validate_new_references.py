"""Independent original complete-configuration enumeration checks held-out references."""
from pathlib import Path
import sys,json,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'01_code_audit'));sys.dont_write_bytecode=True
from src.bootstrap import setup
setup(1)
import numpy as np
from src.conditional_state import action_id,BL,BP
from qmapli.wg_qmf.configuration import enumerate_joint_configurations
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs
from qmapli.wg_qmf.prior import FrozenR4Prior
def main():
    nodes=json.loads((R/'01_code_audit/NODE_MANIFEST.json').read_text())
    model=FrozenR4Prior(R.parent.parent/'Q-COST-QMF-Necessity-Study/phase4_complementarity_analysis/data/r4.pt');rows=[]
    for node in nodes:
        if node['Cohort']!='Validation':continue
        with np.load(node['Input_File']) as z:p=z['points'];q=z['queries']
        ref=json.loads(Path(node['Reference_File']).read_text());u=enumerate_joint_configurations(p,q,model,depth=3,top_k=4,minimum_child_count=256,maximum_configurations=16384)
        table=evaluate_subtree_costs(u.configurations,q,beta_leaf=BL,beta_point=BP);costs={}
        for plan,cost in zip(u.configurations,table.costs):
            root=action_id(plan.root_action);costs[root]=min(costs.get(root,float('inf')),float(cost))
        assert set(costs)==set(ref['root_costs']) and u.size==ref['actual_configurations']
        assert all(np.isclose(c,ref['root_costs'][k],rtol=1e-12,atol=1e-9) for k,c in costs.items())
        rows.append(dict(Node_ID=node['Node_ID'],Configurations=u.size,Root_Costs=costs,Status='PASS'))
        print(node['Node_ID'],u.size,'PASS',flush=True)
    (R/'01_code_audit/NEW_REFERENCE_VALIDATION.json').write_text(json.dumps(dict(Status='PASS',Nodes=40,Total_Configurations=sum(x['Configurations'] for x in rows),Results=rows),indent=2))
if __name__=='__main__':main()
