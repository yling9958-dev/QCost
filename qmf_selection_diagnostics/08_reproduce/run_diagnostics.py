"""Serial, source-frozen 2x2 anytime trajectories and preflight controls."""
from pathlib import Path
import sys,os,json,hashlib,time,gc,signal,platform,argparse,importlib.util
R=Path(__file__).resolve().parents[1];Q=R.parent;P4=Q.parent/'Q-COST-QMF-Necessity-Study/phase4_complementarity_analysis'
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'01_code_audit'))
from src.bootstrap import setup
torch=setup(1)
import numpy as np
from src.hybrid_optimizer import optimize
from src.reference_adapter import verify_plan
from qmapli.wg_qmf.prior import FrozenR4Prior
from qmapli.workload_action_interaction.actions import enumerate_actions
METHODS={'QF':('M8',True),'RF':('M4',True),'QN':('M8',False),'RN':('M4',False)}
SEEDS=list(range(2026101100,2026101130))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def version():
    h=hashlib.sha256()
    for p in [Path(__file__),*sorted((R/'01_code_audit/src').glob('*.py'))]:h.update(str(p.relative_to(R)).encode());h.update(p.read_bytes())
    return h.hexdigest()
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(x,f,separators=(',',':'),allow_nan=False);f.flush();os.fsync(f.fileno())
def load(node):
    with np.load(node['Input_File']) as z:return z['points'],z['queries']
def alarm(*_):raise TimeoutError('120s safety cap; not successful completion')
def execute_one(node,seed,method,model,ratio=1.,diagnostic=True,fn=optimize,trace=False):
    points,queries=load(node);base,feedback=METHODS[method];gc.collect()
    options=dict(method=base,seed=seed,seconds=None if ratio is None else ratio*node['T_exact'],h=3,k=4,
                 model_hash=sha(P4/'data/r4.pt'),data_version=node['Input_SHA256'],trace=trace,enable_incumbent_feedback=feedback)
    if fn is optimize:options['diagnostic']=diagnostic
    signal.alarm(120);result=fn(points,queries,model,**options);signal.alarm(0)
    stats=result['stats'];obs=result.get('observer');engine=result['engine']
    ref=json.loads(Path(node['Reference_File']).read_text());tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
    if result['plan'] is not None:
        legal,cost=verify_plan(result['plan'],points,queries)
        assert legal and abs(cost-stats['selected_cost'])<=tol
    if ratio is None:assert stats['proven_optimal'] and abs(stats['selected_cost']-ref['optimal_cost'])<=tol
    trace_inc=stats['incumbent_trace']
    assert all(a['cost']>=b['cost'] for a,b in zip(trace_inc,trace_inc[1:]))
    if ratio is not None:assert all(e['elapsed']<=ratio*node['T_exact'] for e in trace_inc)
    for e in trace_inc:
        assert e['root'] in ref['root_costs']
        regret=ref['root_costs'][e['root']]-ref['optimal_cost'];assert regret>=-tol
        e['offline_root_cost']=ref['root_costs'][e['root']];e['offline_root_regret']=max(0.,regret);e['offline_optimal']=abs(regret)<=tol
    if obs:
        for event,plan in obs.incumbent_plans:
            legal,cost=verify_plan(engine.export(plan),points,queries);assert legal and abs(cost-plan.cost)<=tol
            event['legality_verified_after_return']=True
        assert sum(x['complete'] for x in obs.candidates)==obs.completed
        assert len(obs.exact)==stats['exact_state_evaluations']
        for e in obs.candidates:assert e['start']<=e['end']
    row=dict(Cohort=node['Cohort'],Dataset=node['Dataset'],Node_ID=node['Node_ID'],Seed=seed,Method=method,
             Feedback=feedback,Selector='QMF' if method.startswith('Q') else 'Random',T_exact=node['T_exact'],Ratio=ratio,
             Budget_s=None if ratio is None else ratio*node['T_exact'],Input_SHA256=node['Input_SHA256'],
             Reference_File=node['Reference_File'],Reference_SHA256=node['Reference_SHA256'],Reference_Offline_Only=True,
             Status=stats['status'],Implementation_Version=version(),stats=stats,
             candidate_events=obs.candidates if obs else [],selection_events=obs.selections if obs else [],
             exact_events=obs.exact if obs else [],cache_events=obs.lookups if obs else [],
             original_trace=result.get('events',[]) if trace else [],Validation='PASS')
    return row
def pilot(model,nodes):
    selected=[next(n for n in nodes if n['Node_ID']=='gowalla_b49ed4334fe4a57f'),next(n for n in nodes if n['Cohort']=='Validation')]
    path=Q/'qmf_random_ablation_revision/02_code/src/hybrid_optimizer.py'
    spec=importlib.util.spec_from_file_location('src.frozen_optimizer_pilot',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    folder=R/'02_raw_logs/pilot';checks=[];overhead=[]
    for node in selected:
        for seed in SEEDS[:3]:
            for method in METHODS:
                prefix=f"{node['Node_ID']}__{seed}__{method}"
                baseline=execute_one(node,seed,method,model,ratio=None,diagnostic=False,fn=mod.optimize,trace=True)
                bare=execute_one(node,seed,method,model,ratio=None,diagnostic=False,trace=True)
                observed=execute_one(node,seed,method,model,ratio=None,diagnostic=True)
                for label,x in [('frozen',baseline),('bare',bare),('observed',observed)]:save(folder/f'{prefix}__{label}.json',x)
                old_tasks=[e['selected_task'] for e in baseline['original_trace']]
                assert old_tasks==[e['selected_task'] for e in bare['original_trace']]==[e['task'] for e in observed['selection_events']]
                for key in ['selected_cost','selected_root','exact_state_evaluations','terminal_cost_evaluations','cache_hits']:
                    assert baseline['stats'][key]==bare['stats'][key]==observed['stats'][key],key
                checks.append(dict(Node=node['Node_ID'],Seed=seed,Method=method,Sequence_Equivalent=True,Exact_Cost_Equivalent=True))
                overhead.append(dict(Node=node['Node_ID'],Seed=seed,Method=method,Bare=bare['stats']['total_optimizer_time'],Observed=observed['stats']['total_optimizer_time']))
                for ratio in [.25,.5,.75,1.]:
                    row=execute_one(node,seed,method,model,ratio=ratio);save(folder/f'{prefix}__cut{ratio}.json',row)
                    # Actual cutoff validation: the API returns the last pre-deadline incumbent; no future root is substituted.
                    hist=[e for e in row['stats']['incumbent_trace'] if e['elapsed']<=row['Budget_s']]
                    assert row['stats']['selected_root']==(hist[-1]['root'] if hist else None)
    save(R/'01_code_audit/PILOT_PASS.json',dict(Status='PASS',Implementation_Version=version(),Pairs=checks,Overhead=overhead,Runs=168,
        Note='2 nodes x 3 seeds x 4 methods x (frozen/bare/observed complete + 4 actual deadlines); pilot never pooled'))
    print('Pilot PASS: 168 real runs; seeded decisions and counters preserved; actual interruptions verified',flush=True)
def formal(model,nodes):
    check=json.loads((R/'01_code_audit/PILOT_PASS.json').read_text());assert check['Implementation_Version']==version() and check['Status']=='PASS'
    folder=R/'02_raw_logs/formal';folder.mkdir(exist_ok=True)
    manifest=dict(Version=version(),Protocol_SHA256=sha(R/'01_code_audit/FROZEN_PROTOCOL.md'),Node_Manifest_SHA256=sha(R/'01_code_audit/NODE_MANIFEST.json'),
        Methods=METHODS,Seeds=SEEDS,H=3,K=4,CPU=sorted(os.sched_getaffinity(0)),Threads=1,Python=sys.version,Torch=torch.__version__,Numpy=np.__version__,
        Platform=platform.platform(),Budgets=[.25,.5,.75,1.],Trajectory='actual 1.0T_exact cutoff; earlier snapshots from observed prefixes',Expected=9600)
    mp=folder/'manifest.json'
    if mp.exists():assert json.loads(mp.read_text())==json.loads(json.dumps(manifest))
    else:save(mp,manifest)
    done=0;new=0;start=time.perf_counter()
    for ni,node in enumerate(nodes):
        for si,seed in enumerate(SEEDS):
            methods=list(METHODS);shift=(ni+si)%4;methods=methods[shift:]+methods[:shift]
            for method in methods:
                dest=folder/f"{node['Cohort']}__{node['Node_ID']}__{seed}__{method}.json"
                if dest.exists():
                    row=json.loads(dest.read_text());assert row['Implementation_Version']==version() and row.get('Validation')=='PASS';done+=1;continue
                try:row=execute_one(node,seed,method,model)
                except Exception as e:
                    signal.alarm(0);import traceback
                    save(dest,dict(Status='FAILED',Node=node,Seed=seed,Method=method,Error=repr(e),Traceback=traceback.format_exc(),Implementation_Version=version()));raise
                save(dest,row);done+=1;new+=1
            if si%5==4:print(json.dumps(dict(cohort=node['Cohort'],node=node['Node_ID'],seed=seed,done=done,expected=9600,elapsed=round(time.perf_counter()-start,2))),flush=True)
    save(folder/f'receipt_{time.time_ns()}.json',dict(Status='COMPLETE',Done=done,New=new,Seconds=time.perf_counter()-start));assert done==9600
def main():
    p=argparse.ArgumentParser();p.add_argument('--pilot',action='store_true');a=p.parse_args()
    nodes=json.loads((R/'01_code_audit/NODE_MANIFEST.json').read_text());model=FrozenR4Prior(P4/'data/r4.pt');points,queries=load(nodes[0])
    acts=[x for x in enumerate_actions(points,.05) if x.valid and min(x.left_count,x.right_count)>=256];model.score_actions(points,queries,acts)
    signal.signal(signal.SIGALRM,alarm)
    if a.pilot:pilot(model,nodes)
    else:formal(model,nodes)
if __name__=='__main__':main()
