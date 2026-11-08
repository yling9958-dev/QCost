"""Freeze outcome-blind real-node selection; create independent Exact references."""
from pathlib import Path
import os,sys,json,csv,hashlib,time,statistics,gc
R=Path(__file__).resolve().parents[1];Q=R.parent;BASE=Q.parent
MOT=BASE/'QMF-Motivation-Study';P4=BASE/'Q-COST-QMF-Necessity-Study/phase4_complementarity_analysis'
sys.path.insert(0,str(R/'01_code_audit'));sys.dont_write_bytecode=True
from src.bootstrap import setup
setup(1)
import numpy as np
from src.comparison_adapter import OBSERVED,run
from src.conditional_state import action_id
from src.reference_adapter import verify_plan
from qmapli.wg_qmf.prior import FrozenR4Prior
from qmapli.workload_action_interaction.actions import enumerate_actions
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(x,f,indent=2);f.flush();os.fsync(f.fileno())
def freeze_order():
    out=R/'01_code_audit/FROZEN_NEW_NODE_ORDER.json'
    if out.exists():return json.loads(out.read_text())
    rows=list(csv.DictReader((MOT/'results/raw/deduplicated_candidate_nodes.csv').open()))
    used={p.name for p in (MOT/'results/nodes').iterdir() if p.is_dir()}
    for p in (BASE/'Q-COST-QMF-Necessity-Study').glob('*/data/nodes/*'):
        if p.is_dir():used.add(p.name)
    used.update(json.loads((P4/'configs/phase4_frozen.json').read_text())['main_nodes'])
    rng=np.random.default_rng(20261025);ordered=[]
    for ds in ['geolife','gowalla','nyc_taxi','skewed_2d']:
        pool=sorted([r for r in rows if r['Dataset']==ds and r['NodeUID'] not in used],key=lambda r:r['NodeUID'])
        features=np.array([[float(r[k]) for k in ['NodeSize','Density','QueryCount','Depth']] for r in pool])
        ranks=np.stack([np.array([(np.sum(x<v)+.5*np.sum(x==v))/len(x) for v in x]) for x in features.T],axis=1)
        ties=rng.random(len(pool));selected=[]
        while len(selected)<len(pool):
            distance=((ranks-.5)**2).sum(1) if not selected else ((ranks[:,None,:]-ranks[selected][None,:,:])**2).sum(2).min(1)
            distance[selected]=-1;i=max(range(len(pool)),key=lambda j:(distance[j],ties[j]));selected.append(i)
        ordered.extend(dict(pool[i],Frozen_Order=j) for j,i in enumerate(selected))
    result=dict(Frozen_At=time.strftime('%Y-%m-%dT%H:%M:%S%z'),Protocol_SHA256=sha(R/'01_code_audit/FROZEN_PROTOCOL.md'),
                Source_Census=str(MOT/'results/raw/deduplicated_candidate_nodes.csv'),Source_SHA256=sha(MOT/'results/raw/deduplicated_candidate_nodes.csv'),
                Previously_Used_UIDs=sorted(used),Selection_Seed=20261025,Ordered_Candidates=ordered)
    save(out,result);return result
def input_from_row(row):
    ds=row['Dataset']
    with np.load(MOT/'data'/f'{ds}_20000/points.npz') as z:allpoints=z['points']
    with np.load(MOT/row['MembershipFile']) as z:indices=np.sort(z[row['MembershipKey']])
    assert hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest()==row['StateSHA256']
    points=allpoints[indices];b=np.r_[points.min(0),points.max(0)]
    with np.load(MOT/'data'/f'{ds}_20000/queries.npz') as z:queries=z['train']
    queries=queries[(queries[:,2]>=b[0])&(queries[:,0]<=b[2])&(queries[:,3]>=b[1])&(queries[:,1]<=b[3])]
    return points,queries
def main():
    order=freeze_order();model=FrozenR4Prior(P4/'data/r4.pt');nodes=[];accepted={d:0 for d in ['geolife','gowalla','nyc_taxi','skewed_2d']}
    cfg=json.loads((P4/'configs/phase4_frozen.json').read_text());inv={x['uid']:x for x in json.loads((P4/'data/node_inventory.json').read_text())}
    for uid in cfg['main_nodes']:
        ref=P4/'data/references'/f'{uid}.json';j=json.loads(ref.read_text());costs=list(j['root_costs'].values());f=j['optimal_cost'];tol=max(1e-9,abs(f)*1e-12)
        gap=min([x-f for x in costs if x>f+tol],default=0.)/max(abs(f),1e-9)
        nodes.append(dict(Cohort='Original',Node_ID=uid,Dataset=inv[uid]['dataset'],Input_File=str(P4/'data/nodes'/uid/'input.npz'),
            Input_SHA256=sha(P4/'data/nodes'/uid/'input.npz'),Reference_File=str(ref),Reference_SHA256=sha(ref),T_exact=cfg['T_exact_reference'][uid],
            Configurations=inv[uid]['N'],Relative_Root_Gap=gap,Root_Actions=len(costs),All_Roots_Tied=all(abs(x-f)<=tol for x in costs),
            Points=inv[uid]['points'],Queries=inv[uid]['queries']))
    for row in order['Ordered_Candidates']:
        ds=row['Dataset'];uid=row['NodeUID']
        if accepted[ds]>=10:continue
        dest=R/'01_code_audit/new_nodes'/uid;rp=dest/'reference.json'
        if rp.exists():ref=json.loads(rp.read_text())
        else:
            dest.mkdir(parents=True,exist_ok=True);points,queries=input_from_row(row)
            acts=[a for a in enumerate_actions(points,.05) if a.valid and min(a.left_count,a.right_count)>=256]
            if acts:model.score_actions(points,queries,acts)
            costs={};rec=OBSERVED.RecursiveExact(queries,model);rec.observed_h=3;rec.observer=lambda sol:costs.update({action_id(sol.action):sol.cost})
            sol=rec.solve(points,h=3)
            if sol is None:
                ref=dict(Status='INFEASIBLE',Node_ID=uid,Selection_Source=row);save(rp,ref);continue
            with (dest/'input.npz').open('xb') as f:np.savez(f,points=points,queries=queries)
            timings=[]
            for seed in [11,23,37]:
                gc.collect();result=run(points,queries,model,'EXACT',seed=seed,trace=False)
                legal,cost=verify_plan(result['plan'],points,queries);assert legal and np.isclose(cost,sol.cost,rtol=1e-12)
                save(dest/f'exact_repeat_{seed}.json',result['stats']);timings.append(result['stats']['total_optimizer_time'])
            tol=max(1e-9,abs(sol.cost)*1e-12)
            ref=dict(Status='EXACT',Node_ID=uid,optimal_cost=sol.cost,root_costs=costs,
                optimal_roots=[k for k,v in costs.items() if abs(v-sol.cost)<=tol],actual_configurations=sol.count,
                T_exact=statistics.median(timings),Reference_Timings=timings,Reference_Seeds=[11,23,37],
                Selection_Source=row,Points=len(points),Queries=len(queries),Frozen_Before_Search=True)
            save(rp,ref)
        if ref['Status']=='INFEASIBLE':continue
        accepted[ds]+=1;costs=list(ref['root_costs'].values());f=ref['optimal_cost'];tol=max(1e-9,abs(f)*1e-12)
        nodes.append(dict(Cohort='Validation',Node_ID=uid,Dataset=ds,Input_File=str((dest/'input.npz').resolve()),
            Input_SHA256=sha(dest/'input.npz'),Reference_File=str(rp.resolve()),Reference_SHA256=sha(rp),T_exact=ref['T_exact'],
            Configurations=ref['actual_configurations'],Relative_Root_Gap=min([x-f for x in costs if x>f+tol],default=0.)/max(abs(f),1e-9),
            Root_Actions=len(costs),All_Roots_Tied=all(abs(x-f)<=tol for x in costs),Points=ref['Points'],Queries=ref['Queries']))
        print(json.dumps(dict(dataset=ds,node=uid,accepted=accepted[ds],N=ref['actual_configurations'],T_exact=ref['T_exact'])),flush=True)
    assert all(n==10 for n in accepted.values()),accepted
    assert len(nodes)==80 and len({x['Node_ID'] for x in nodes})==80
    path=R/'01_code_audit/NODE_MANIFEST.json'
    if path.exists():assert json.loads(path.read_text())==nodes
    else:save(path,nodes)
    with (R/'01_code_audit/NODE_MANIFEST.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(nodes[0]));w.writeheader();w.writerows(nodes)
    print('FROZEN: 40 original + 40 held-out real nodes; references prepared')
if __name__=='__main__':main()
