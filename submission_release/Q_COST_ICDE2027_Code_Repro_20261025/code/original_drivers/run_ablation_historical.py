"""Serial, checkpointed five-way ablation of the frozen Phase4 optimizer."""
from pathlib import Path
import os,sys,json,csv,time,hashlib,argparse,gc,signal,platform,subprocess
ROOT=Path(__file__).resolve().parents[1]
P4=ROOT.parent.parent/'Q-COST-QMF-Necessity-Study/phase4_complementarity_analysis'
sys.dont_write_bytecode=True
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from src.bootstrap import setup
setup(1)
import numpy as np
from src.hybrid_optimizer import optimize
from src.reference_adapter import verify_plan
from qmapli.wg_qmf.prior import FrozenR4Prior
from qmapli.workload_action_interaction.actions import enumerate_actions

VARIANTS={
 'V1':('Full Hybrid-QMF',dict(method='M8')),
 'V2':('w/o QMF Selection',dict(method='M6')),
 'V3':('w/o Shared Cache',dict(method='M8',enable_cache=False)),
 'V4':('w/o Incumbent Feedback',dict(method='M8',enable_incumbent_feedback=False)),
 'V5':('w/o Recursive Decomposition',dict(method='M8',direct_enumeration=True)),
}
SEEDS=list(range(2026101100,2026101130))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def version():
    h=hashlib.sha256()
    for p in sorted((ROOT/'02_code').rglob('*.py')):
        if p.name in ['analyze.py','make_reports.py','paper_delivery.py']:continue
        h.update(str(p.relative_to(ROOT)).encode());h.update(p.read_bytes())
    return h.hexdigest()
def save(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
def load(uid):
    with np.load(P4/'data/nodes'/uid/'input.npz') as z:return z['points'],z['queries']
def alarm(*_):raise TimeoutError('complete-run safety limit (not completion)')
def execute(args):
    cfg=json.loads((P4/'configs/phase4_frozen.json').read_text())
    inv={r['uid']:r for r in json.loads((P4/'data/node_inventory.json').read_text())}
    nodes=cfg['main_nodes'] if not args.pilot else [cfg['pilot_nodes'][0],cfg['pilot_nodes'][3]]
    seeds=SEEDS if not args.pilot else SEEDS[:3]
    if args.node_limit:nodes=nodes[:args.node_limit]
    out=ROOT/'03_runs'/('pilot' if args.pilot else 'formal');out.mkdir(parents=True,exist_ok=True)
    ver=version();manifest=dict(code_sha256=ver,model_sha256=sha(P4/'data/r4.pt'),seeds=seeds,nodes=nodes,h=3,k=4,
        threads=1,cpu_affinity=sorted(os.sched_getaffinity(0)),python=sys.version,platform=platform.platform(),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        budget_ratios=[.5],timer='Instrumentation starts before RNG, cache and engine; ends after plan export and stats',
        deadline='Cooperative checks; post-deadline computations cannot improve returned incumbent; overrun recorded',
        source_phase4=str(P4),variants=VARIANTS)
    mp=out/'manifest.json'
    if mp.exists():assert json.loads(mp.read_text())==manifest,'Refusing to mix implementation/environment versions'
    else:save(mp,manifest)
    model=FrozenR4Prior(P4/'data/r4.pt')
    p,q=load(nodes[0]);acts=tuple(a for a in enumerate_actions(p,.05) if a.valid and min(a.left_count,a.right_count)>=256)
    model.score_actions(p,q,acts)
    signal.signal(signal.SIGALRM,alarm)
    started=time.perf_counter();done=0;new=0
    for ni,node in enumerate(nodes):
        points,queries=load(node);dh=sha(P4/'data/nodes'/node/'input.npz')
        for si,seed in enumerate(seeds):
            keys=list(VARIANTS);offset=(ni+si)%5;keys=keys[offset:]+keys[:offset]
            # Balance ordering of budget and full runs; no optimizers run concurrently.
            protocols=['A','B'] if (ni+si)%2==0 else ['B','A']
            for protocol in protocols:
                for key in keys:
                    dest=out/f'{node}__{seed}__{key}__{protocol}.json'
                    if dest.exists():
                        previous=json.loads(dest.read_text());assert previous['Implementation_Version']==ver
                        if previous['Status'] in ['FAILED','TIMEOUT']:raise RuntimeError(f'Unresolved checkpoint: {dest}')
                        done+=1;continue
                    name,opts=VARIANTS[key];wall=.5*cfg['T_exact_reference'][node] if protocol=='A' else None
                    row=dict(Dataset=inv[node]['dataset'],Node_ID=node,Seed=seed,Seed_Index=SEEDS.index(seed),Variant=name,
                        Variant_ID=key,Protocol=protocol,Time_Budget_s=wall,T_exact_s=cfg['T_exact_reference'][node],
                        Implementation_Version=ver,Data_SHA256=dh,Source_File=str(dest.resolve()),H=3,K=4)
                    gc.collect();t=time.perf_counter()
                    try:
                        signal.alarm(args.timeout)
                        result=optimize(points,queries,model,seed=seed,seconds=wall,h=3,k=4,trace=False,
                                        model_hash=manifest['model_sha256'],data_version=dh,**opts)
                        signal.alarm(0);st=result['stats'];e=result['engine']
                        # Reference answers become accessible ONLY after optimization returns.
                        refpath=P4/'data/references'/f'{node}.json';ref=json.loads(refpath.read_text())
                        legal,cost=verify_plan(result['plan'],points,queries) if result['plan'] is not None else (False,None)
                        tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
                        if legal:assert abs(cost-st['selected_cost'])<=tol
                        if protocol=='B':assert st['proven_optimal'] and legal and abs(cost-ref['optimal_cost'])<=tol
                        rc=ref['root_costs'].get(st['selected_root']) if legal else None
                        regret=rc-ref['optimal_cost'] if rc is not None else None
                        if legal:assert regret is not None and regret>=-tol
                        if regret is not None and abs(regret)<=tol:regret=0.
                        if wall is not None:assert all(x['elapsed']<=wall for x in st['incumbent_trace'])
                        assert st['exact_state_evaluations']==sum(x.exact for x in e.nodes)
                        assert st['unique_exact_states']==len({x.key for x in e.nodes if x.exact})
                        if key=='V3':assert st['cache_hits']==0 and not st['cache_state_enabled']
                        if key=='V4':assert not st['options']['feedback'] and st['options']['strategy']=='qmf'
                        if key=='V2':assert st['options']==dict(cache=True,feedback=True,strategy='bestfirst')
                        trace=st['incumbent_trace'];assert all(x['cost']>=y['cost'] for x,y in zip(trace,trace[1:]))
                        if trace:assert st['selected_cost']==trace[-1]['cost']
                        row.update(Optimal_Root=bool(legal and regret==0),Root_Regret=regret,
                            Optimization_Time_s=st['total_optimizer_time'],Exact_State_Evaluations=st['exact_state_evaluations'],
                            Exact_State_Calls=st['exact_state_calls'],Unique_Exact_States=st['unique_exact_states'],
                            Terminal_Cost_Calls=st['terminal_cost_evaluations'],Cache_Hits=st['cache_hits'],
                            Final_Cost=st['selected_cost'],Final_Root=st['selected_root'],Status=st['status'],
                            Feasible=legal,Deadline_Overrun_s=st['deadline_overrun_seconds'],
                            Enumerated_Configurations=st['enumerated_configurations'],
                            Direct_Configuration_Cost_Evaluations=st['direct_configuration_cost_evaluations'],
                            Reference_File=str(refpath),Reference_SHA256=sha(refpath),Reference_Used_Only_After_Run=True)
                        payload={**row,'stats':st,'validation':'PASS'}
                        if args.pilot and protocol=='B':
                            payload['conditional_costs']={x.key:x.best.cost if x.best else None for x in e.nodes if x.exact}
                        result=None;e=None
                    except Exception as ex:
                        signal.alarm(0);import traceback
                        payload={**row,'Status':'TIMEOUT' if isinstance(ex,TimeoutError) else 'FAILED',
                            'Observed_Elapsed_s':time.perf_counter()-t,'error':repr(ex),'traceback':traceback.format_exc()}
                        save(dest,payload);print(json.dumps(payload),flush=True);raise
                    save(dest,payload);done+=1;new+=1
                print(json.dumps(dict(node=node,seed=seed,protocol=protocol,completed=done,new=new,
                                     elapsed_s=round(time.perf_counter()-started,2))),flush=True)
    receipt=dict(status='COMPLETE',expected=len(nodes)*len(seeds)*5*2,completed=done,new=new,
                 elapsed_s=time.perf_counter()-started,code_sha256=ver)
    save(out/f'receipt_{time.time_ns()}.json',receipt);print(json.dumps(receipt),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot',action='store_true');p.add_argument('--timeout',type=int,default=120)
    p.add_argument('--node-limit',type=int,default=0);execute(p.parse_args())
