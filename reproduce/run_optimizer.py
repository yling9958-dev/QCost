#!/usr/bin/env python3
"""Portable serial wrapper around the delivered, unchanged optimizer implementations."""
from pathlib import Path
import argparse, gc, hashlib, importlib, importlib.metadata, json, os, platform, signal, sys, time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
VARIANTS = {
    'Full': ('Full Hybrid-QMF', dict(method='M8')),
    'Random': ('w/o QMF Selection', dict(method='M4')),
    'NoCache': ('w/o Shared Cache', dict(method='M8', enable_cache=False)),
    'NoFeedback': ('w/o Incumbent Feedback', dict(method='M8', enable_incumbent_feedback=False)),
    'Enumeration': ('w/o Recursive Decomposition', dict(method='M8', direct_enumeration=True)),
}
SELECTION = {'QF': dict(method='M8', enable_incumbent_feedback=True),
             'RF': dict(method='M4', enable_incumbent_feedback=True),
             'QN': dict(method='M8', enable_incumbent_feedback=False),
             'RN': dict(method='M4', enable_incumbent_feedback=False)}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p, row):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(row, f, indent=2, allow_nan=False)
        f.flush(); os.fsync(f.fileno())

def timeout(*_): raise TimeoutError('Safety timeout: this is not successful completion')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['ablation', 'selection'], default='ablation')
    p.add_argument('--inputs-root', type=Path, required=True, help='External directory containing NODE_ID/input.npz')
    p.add_argument('--output', type=Path, required=True, help='New run directory; existing matching checkpoints are resumed')
    p.add_argument('--cohort', choices=['Original', 'Validation', 'Both'], default='Original')
    p.add_argument('--protocol', choices=['A', 'B', 'both'], default='both')
    p.add_argument('--variants', nargs='+', help='Ablation: Full Random NoCache NoFeedback Enumeration; selection: QF RF QN RN')
    p.add_argument('--limit-nodes', type=int)
    p.add_argument('--limit-seeds', type=int)
    p.add_argument('--timeout', type=int, default=120)
    args = p.parse_args()
    if args.mode == 'selection' and args.protocol != 'both':
        p.error('Selection diagnostics record one trace through 1.0T_exact; omit --protocol')
    for limit in [args.limit_nodes, args.limit_seeds, args.timeout]:
        if limit is not None and limit < 1: p.error('Limits must be positive')
    code = ROOT / 'src/python/qcost_experiments' / args.mode
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        os.environ[name] = '1'
    import torch
    torch.set_num_threads(1)
    import numpy as np
    optimize = importlib.import_module('qcost_experiments.' + args.mode + '.hybrid_optimizer').optimize
    from qcost_repro.validation import verify_plan
    from qmapli.wg_qmf.prior import FrozenR4Prior
    from qmapli.workload_action_interaction.actions import enumerate_actions
    all_nodes = json.loads((ROOT / 'configs/NODE_MANIFEST.json').read_text())
    nodes = [n for n in all_nodes if args.cohort == 'Both' or n['Cohort'] == args.cohort]
    if args.mode == 'ablation' and args.cohort != 'Original': p.error('Table II uses the Original cohort only')
    nodes = nodes[:args.limit_nodes]
    seeds = json.loads((ROOT / 'configs/seeds.json').read_text())[:args.limit_seeds]
    variant_map = VARIANTS if args.mode == 'ablation' else SELECTION
    variants = args.variants or list(variant_map)
    if len(set(variants)) != len(variants) or any(v not in variant_map for v in variants): p.error('Invalid or duplicate variant')
    # Verify external inputs without opening reference answers or passing them to search.
    for node in nodes:
        path = args.inputs_root / node['Input_File']
        if not path.is_file(): p.error(f'Dataset deliberately excluded; supply external input: {path}')
        if sha(path) != node['Input_SHA256']: p.error(f'Input SHA-256 mismatch: {path}')
    source_hash = hashlib.sha256()
    for f in sorted((ROOT / 'src/python').rglob('*.py')):
        source_hash.update(str(f.relative_to(ROOT)).encode()); source_hash.update(f.read_bytes())
    manifest = dict(mode=args.mode, nodes=[n['Node_ID'] for n in nodes], seeds=seeds, variants=variants,
                    protocol=args.protocol, h=3, k=4, source_sha256=source_hash.hexdigest(),
                    model_sha256=sha(ROOT / 'models/r4.pt'), python=sys.version, platform=platform.platform(),
                    numpy=np.__version__, torch=torch.__version__, threads=1,
                    affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
                    timer='existing optimizer timer; excludes input I/O, model loading and offline evaluation',
                    budget='frozen node-level T_exact from recorded protocol, not re-estimated on this machine',
                    truncated=bool(args.limit_nodes or args.limit_seeds or args.variants), timeout=args.timeout,
                    wrapper_sha256=sha(__file__),
                    node_manifest_sha256=sha(ROOT / 'configs/NODE_MANIFEST.json'),
                    seed_manifest_sha256=sha(ROOT / 'configs/seeds.json'))
    args.output.mkdir(parents=True, exist_ok=True)
    mp = args.output / 'manifest.json'
    if mp.exists():
        if json.loads(mp.read_text()) != manifest: raise RuntimeError('Refusing incompatible resume manifest')
    else: save(mp, manifest)
    model = FrozenR4Prior(ROOT / 'models/r4.pt')
    with np.load(args.inputs_root / nodes[0]['Input_File'], allow_pickle=False) as data:
        points, queries = data['points'], data['queries']
    actions = tuple(a for a in enumerate_actions(points,.05) if a.valid and min(a.left_count,a.right_count)>=256)
    if actions: model.score_actions(points, queries, actions)
    signal.signal(signal.SIGALRM, timeout)
    completed = 0
    for ni, node in enumerate(nodes):
        with np.load(args.inputs_root / node['Input_File'], allow_pickle=False) as data:
            points, queries = data['points'], data['queries']
        for si, seed in enumerate(seeds):
            offset=(ni+si)%len(variants); order=variants[offset:]+variants[:offset]
            protocols = ['trace'] if args.mode=='selection' else (['A','B'] if args.protocol=='both' else [args.protocol])
            if (ni+si)%2: protocols=protocols[::-1]
            for protocol in protocols:
                for key in order:
                    dest=args.output/f'{node["Node_ID"]}__{seed}__{key}__{protocol}.json'
                    if dest.exists():
                        old=json.loads(dest.read_text())
                        if old.get('validation') != 'PASS': raise RuntimeError(f'Failed checkpoint requires review: {dest}')
                        completed+=1; continue
                    label,opts=VARIANTS[key] if args.mode=='ablation' else (key,SELECTION[key])
                    budget = None if protocol=='B' else node['T_exact']*(.5 if protocol=='A' else 1.)
                    row=dict(Dataset=node['Dataset'],Node_ID=node['Node_ID'],Cohort=node['Cohort'],Seed=seed,
                             Variant=label,Variant_ID=key,Protocol=protocol,H=3,K=4,T_exact_s=node['T_exact'],
                             Time_Budget_s=budget,Data_SHA256=node['Input_SHA256'],Implementation_Version=manifest['source_sha256'])
                    gc.collect(); start=time.perf_counter()
                    try:
                        signal.alarm(args.timeout)
                        result=optimize(points,queries,model,seed=seed,seconds=budget,h=3,k=4,
                                        trace=False,model_hash=manifest['model_sha256'],data_version=node['Input_SHA256'],
                                        **opts,**({'diagnostic':True} if args.mode=='selection' else {}))
                        signal.alarm(0)
                        st=result['stats']
                        # Offline reference is opened only after optimize() returns.
                        refpath=ROOT/node['Reference_File']; assert sha(refpath)==node['Reference_SHA256']
                        ref=json.loads(refpath.read_text())
                        legal,cost=verify_plan(result['plan'],points,queries) if result['plan'] is not None else (False,None)
                        tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
                        regret=ref['root_costs'][st['selected_root']]-ref['optimal_cost'] if legal else None
                        if regret is not None and abs(regret)<=tol:regret=0.
                        if legal: assert abs(cost-st['selected_cost'])<=tol and regret>=0
                        if protocol=='B': assert legal and st['proven_optimal'] and abs(cost-ref['optimal_cost'])<=tol
                        if budget is not None: assert all(e['elapsed']<=budget for e in st['incumbent_trace'])
                        row.update(Optimal_Root=bool(legal and regret==0),Root_Regret=regret,Valid_Return=legal,
                                   Optimization_Time_s=st['total_optimizer_time'],Exact_State_Evaluations=st['exact_state_evaluations'],
                                   Cache_Hits=st['cache_hits'],Terminal_Cost_Calls=st['terminal_cost_evaluations'],
                                   Final_Cost=st['selected_cost'],Final_Root=st['selected_root'],Status=st['status'],
                                   Reference_Used_Only_After_Run=True,stats=st,validation='PASS')
                        if args.mode=='selection':
                            o=result['observer']
                            for event,plan in o.incumbent_plans:
                                ok,vc=verify_plan(result['engine'].export(plan),points,queries)
                                assert ok and abs(vc-event['cost'])<=tol
                                event['legality_verified_after_return']=True
                            row.update(candidate_events=o.candidates,selection_events=o.selections,
                                       exact_events=o.exact,cache_events=o.lookups,Method=key,
                                       Selector='QMF' if key.startswith('Q') else 'Random',Feedback=opts['enable_incumbent_feedback'],
                                       T_exact=node['T_exact'],Budget_s=budget,Validation='PASS')
                        result=None
                    except Exception as ex:
                        signal.alarm(0)
                        row.update(Status='TIMEOUT' if isinstance(ex,TimeoutError) else 'FAILED',
                                   Observed_Elapsed_s=time.perf_counter()-start,error=repr(ex))
                        save(dest,row); raise
                    save(dest,row);completed+=1
            print(json.dumps(dict(node=node['Node_ID'],seed=seed,completed=completed)),flush=True)
    print(json.dumps(dict(status='COMPLETE',runs=completed,partial_protocol=manifest['truncated'])))

if __name__=='__main__':main()
