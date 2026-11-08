"""Isolated algorithm feasibility experiments; imports frozen code read-only.

RecursiveExact never constructs the Cartesian product of complete plans. It
retains one best child solution per conditional state and reconstructs one plan.
All result writes use exclusive creation. Do not use this as a production builder.
"""
from pathlib import Path
from dataclasses import dataclass, asdict
import argparse, csv, gc, hashlib, json, math, os, pickle, resource, sys, time

RUN=Path(__file__).resolve().parents[1]
ROOT=RUN.parents[1]
PKG=ROOT/'QMF_PostGIS_100M_Repro_20260910'
sys.path.insert(0,str(PKG/'src/common/python'))
import numpy as np
import torch
import yaml
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
from qmapli.workload_action_interaction.actions import enumerate_actions, split_positions
from qmapli.wg_qmf.configuration import (
    JointConfiguration, LeafSummary, PartitionSummary, PlannedAction,
    enumerate_joint_configurations, _bounds, _stable_softmax,
)
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs
from qmapli.wg_qmf.prior import FrozenR4Prior
from qmapli.wg_qmf.index import _greedy_action
from qmapli.wg_qmf.search import uniform_qmf, exhaustive_search, beam_search, AbstractPhaseCostOracle, _qmf

CONFIG=yaml.safe_load((PKG/'config/qmf_frozen_config.yaml').read_text())
BL=float(CONFIG['beta_leaf']);BP=float(CONFIG['beta_point'])
MIN_CHILD=int(CONFIG['min_leaf_size']);K=int(CONFIG['top_k']);H=int(CONFIG['lookahead_depth'])
CHECKPOINT=PKG/CONFIG['r4_checkpoint']
JOB=Path(os.environ['QMF_DIAG_JOB'])

def write_json(path,obj):
    with Path(path).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)

def write_csv(path,rows):
    if not rows:return
    with Path(path).open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def sha_array(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()

def load_node(name):
    t=time.perf_counter()
    with np.load(RUN/'inputs'/(name+'.npz'),allow_pickle=False) as src:
        points=src['points'];queries=src['queries']
    meta=json.loads((RUN/'inputs'/(name+'.json')).read_text())
    assert len(points)==meta['points'] and len(queries)==meta['queries']
    return points,queries,meta,time.perf_counter()-t

class Scorer:
    direction='higher_is_better'
    def __init__(self,audit=False):
        t=time.perf_counter();self.base=FrozenR4Prior(CHECKPOINT)
        self.load_seconds=time.perf_counter()-t
        self.audit=audit;self.records=[]
    @property
    def score_seconds(self):return self.base.score_seconds
    @property
    def score_calls(self):return self.base.score_calls
    def score_actions(self,points,queries,actions):
        values=self.base.score_actions(points,queries,actions)
        if self.audit:
            self.records.append({'n':len(points),'q':len(queries),'bounds':_bounds(points),
                'keys':[a.key for a in actions],'thresholds':[a.threshold.hex() for a in actions],
                'scores':[float(v).hex() for v in values]})
        return values

@dataclass
class Solution:
    hits:int
    scans:int
    cost:float
    count:int
    prior:float
    leaf:object=None
    action:object=None
    left:object=None
    right:object=None
    left_bounds:object=None
    right_bounds:object=None

class RecursiveExact:
    """Exact conditional optimization, no memoization, no cross-plan enumeration.

Every partial cost is calculated from integer aggregate hit/scan counts using
the same query denominator as the production cached cost oracle. Selection is
strict <, preserving production candidate order on exact floating-point ties.
"""
    def __init__(self,queries,scorer):
        assert len(queries)>0
        self.queries=queries;self.scorer=scorer;self.q=len(queries)
        self.internal_visits=0;self.terminal_visits=0;self.invalid_states=0
        self.action_evaluations=0;self.leaf_geometry_seconds=0.;self.cost_seconds=0.
        self.hit_cache={};self.internal_keys=set();self.terminal_keys=set()
    def cost(self,hits,scans):
        t=time.perf_counter()
        value=BL*(float(hits)/self.q)+BP*(float(scans)/self.q)
        self.cost_seconds+=time.perf_counter()-t
        return value
    def leaf_solution(self,points,bounds):
        self.terminal_visits+=1;self.terminal_keys.add((len(points),bounds))
        t=time.perf_counter()
        if bounds not in self.hit_cache:
            x0,y0,x1,y1=bounds;q=self.queries
            self.hit_cache[bounds]=int(np.count_nonzero((q[:,2]>=x0)&(q[:,0]<=x1)&(q[:,3]>=y0)&(q[:,1]<=y1)))
        hits=self.hit_cache[bounds];scans=hits*len(points)
        self.leaf_geometry_seconds+=time.perf_counter()-t
        return Solution(hits,scans,self.cost(hits,scans),1,1.,leaf=LeafSummary(len(points),bounds))
    def solve(self,points,h=H,bounds=None):
        bounds=_bounds(points) if bounds is None else bounds
        if h==0:return self.leaf_solution(points,bounds)
        self.internal_visits+=1;self.internal_keys.add((h,len(points),bounds))
        actions=tuple(a for a in enumerate_actions(points,0.05) if a.valid and min(a.left_count,a.right_count)>=MIN_CHILD)
        if not actions:
            self.invalid_states+=1;return None
        scores=np.asarray(self.scorer.score_actions(points,self.queries,actions),dtype=np.float64)
        if scores.shape!=(len(actions),) or not np.isfinite(scores).all():raise ValueError('invalid scorer output')
        order=sorted(range(len(actions)),key=lambda i:(-scores[i],actions[i].key))[:K]
        probabilities=_stable_softmax(scores[np.asarray(order)],temperature=1.0,epsilon=1e-12)
        feasible=[];count=0
        for i,probability in zip(order,probabilities,strict=True):
            action=actions[i];self.action_evaluations+=1
            lp,rp=split_positions(points,action)
            dl=np.asarray(points[lp],dtype=np.float64);dr=np.asarray(points[rp],dtype=np.float64)
            lb,rb=_bounds(dl),_bounds(dr)
            left=self.solve(dl,h-1,lb)
            right=self.solve(dr,h-1,rb)  # also evaluated if left failed: same traversal as production
            del lp,rp,dl,dr
            if left is None or right is None:continue
            count+=left.count*right.count
            hits=left.hits+right.hits;scans=left.scans+right.scans
            item=Solution(hits,scans,self.cost(hits,scans),0,0.,action=action,left=left,right=right,left_bounds=lb,right_bounds=rb)
            feasible.append((item,float(probability)))
        if not feasible:
            self.invalid_states+=1;return None
        total_prob=sum(pr for _,pr in feasible)
        best,best_prob=feasible[0]
        for candidate,prob in feasible[1:]:
            if candidate.cost<best.cost:best,best_prob=candidate,prob
        best.count=count
        best.prior=(best_prob/total_prob)*best.left.prior*best.right.prior
        return best
    def stats(self):
        return {'conditional_internal_visits':self.internal_visits,'unique_internal_states':len(self.internal_keys),
            'leaf_evaluations':self.terminal_visits,'unique_leaf_states':len(self.terminal_keys),
            'unique_leaf_mbrs':len(self.hit_cache),'action_evaluations':self.action_evaluations,
            'infeasible_states':self.invalid_states,'leaf_geometry_seconds':self.leaf_geometry_seconds,
            'cost_arithmetic_seconds':self.cost_seconds,'memoization':False}

def reconstruct(sol,h=H):
    actions=[];leaves=[];parts=[]
    def walk(s,path):
        if s.leaf is not None:leaves.append(s.leaf);return
        actions.append(PlannedAction(path,s.action))
        parts.append(PartitionSummary(path,s.left_bounds,s.right_bounds))
        walk(s.left,path+(0,));walk(s.right,path+(1,))
    walk(sol,())
    return JointConfiguration(tuple(actions),tuple(leaves),tuple(parts),sol.prior,h)

def greedy_rollout(points,queries,scorer,h=H):
    """No feasibility lookahead/backtracking; same Q context for fair H3 comparison.
    This is a local full-depth R4 rollout, not the whole production greedy builder.
    """
    if h==0:return Solution(0,0,0.,1,1.,leaf=LeafSummary(len(points),_bounds(points)))
    action=_greedy_action(points,queries,scorer,minimum_child_count=MIN_CHILD)
    if action is None:return None
    lp,rp=split_positions(points,action);dl=points[lp];dr=points[rp]
    lb,rb=_bounds(dl),_bounds(dr)
    left=greedy_rollout(dl,queries,scorer,h-1);right=greedy_rollout(dr,queries,scorer,h-1)
    if left is None or right is None:return None
    return Solution(0,0,0.,1,1.,action=action,left=left,right=right,left_bounds=lb,right_bounds=rb)

def enumerate_current(points,queries,scorer):
    return enumerate_joint_configurations(points,queries,scorer,depth=H,top_k=K,
        minimum_fraction=.05,minimum_child_count=MIN_CHILD,temperature=1.,epsilon=1e-12,maximum_configurations=16384)

def current_cost(plans,queries):
    return evaluate_subtree_costs(plans,queries,beta_leaf=BL,beta_point=BP,query_split='train')

def plan_signature(plan):
    return [(a.path,a.action.key,a.action.threshold.hex(),a.action.left_count,a.action.right_count) for a in plan.actions]

def serialize_plan(plan):
    return {'actions':[{'path':a.path,**a.action.as_dict(),'threshold_hex':a.action.threshold.hex()} for a in plan.actions],
        'leaves':[asdict(l) for l in plan.leaves], 'partitions':[asdict(part) for part in plan.partitions],
        'prior_product':plan.prior_product,'depth':plan.depth}

def cost_metrics(value,costs):
    optimum=float(np.min(costs));maximum=float(np.max(costs));tol=8*float(np.spacing(max(abs(optimum),1.)))
    return {'selected_cost':float(value),'optimal_cost':optimum,
        'normalized_gap':float((value-optimum)/max(maximum-optimum,1e-12)),
        'exact_optimum_hit':bool(value==optimum),'within_8ulp_optimum':bool(abs(value-optimum)<=tol),'cost_tolerance':tol}

def inspect_node(name):
    points,queries,meta,load_s=load_node(name)
    scorer=Scorer(audit=True);t=time.perf_counter();universe=None;error=None
    try:universe=enumerate_current(points,queries,scorer)
    except RuntimeError as ex:error=str(ex)
    enum_s=time.perf_counter()-t
    reference_trace=scorer.records
    recursive_scorer=Scorer(audit=True);rec=RecursiveExact(queries,recursive_scorer)
    t=time.perf_counter();solution=rec.solve(points);rec_s=time.perf_counter()-t
    out={'node':name,'input_manifest':meta,'load_seconds':load_s,'enumeration_seconds':enum_s,
        'recursive_seconds':rec_s,'enumeration_score_calls':scorer.score_calls,
        'recursive_score_calls':recursive_scorer.score_calls,'scorer_traces_identical':reference_trace==recursive_scorer.records,
        'enumeration_error':error,'recursive_stats':rec.stats(),'rss_hwm_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        'frozen_config':CONFIG,'cpu_affinity':sorted(os.sched_getaffinity(0)),
        'torch_threads':torch.get_num_threads(),'torch_interop_threads':torch.get_num_interop_threads()}
    assert out['scorer_traces_identical'],'conditional scorer traversal differs'
    if universe is None:
        assert solution is None,'enumerator rejected but recursive returned a full plan'
        out.update(status='PASS_BOTH_INFEASIBLE',configuration_count=0,complete_configurations_materialized_recursive=0)
        write_json(JOB/'result.json',out);print(json.dumps(out,ensure_ascii=False));return
    assert solution is not None
    t=time.perf_counter();table=current_cost(universe.configurations,queries);cost_s=time.perf_counter()-t
    exact_index=int(np.argmin(table.costs));exact=universe.configurations[exact_index]
    plan=reconstruct(solution);selected=float(current_cost((plan,),queries).costs[0])
    tol=8*float(np.spacing(max(abs(float(table.costs[exact_index])),1.)))
    assert abs(selected-float(table.costs[exact_index]))<=tol,(selected,table.costs[exact_index])
    assert solution.count==universe.size,(solution.count,universe.size)
    candidates={tuple(plan_signature(z)):i for i,z in enumerate(universe.configurations)}
    sig=tuple(plan_signature(plan));assert sig in candidates,'recursive plan not in production universe'
    recursive_index=candidates[sig]
    assert selected==float(table.costs[recursive_index]),'standalone production evaluation differs from table'
    # Direct independent leaf additivity identity, checked for every enumerated configuration.
    q=len(queries);max_difference=0.
    hits={}
    for z,c in zip(universe.configurations,table.costs):
        leafsum=0.
        for l in z.leaves:
            if l.bounds not in hits:
                x0,y0,x1,y1=l.bounds
                hits[l.bounds]=int(np.count_nonzero((queries[:,2]>=x0)&(queries[:,0]<=x1)&(queries[:,3]>=y0)&(queries[:,1]<=y1)))
            leafsum+=(BL+BP*l.point_count)*(hits[l.bounds]/q)
        max_difference=max(max_difference,abs(leafsum-float(c)))
    additive_tol=16*float(np.spacing(max(float(table.costs.max()),1.)))
    assert max_difference<=additive_tol,(max_difference,additive_tol)
    greedy_scorer=Scorer();greedy=greedy_rollout(points,queries,greedy_scorer)
    greedy_plan=reconstruct(greedy) if greedy else None
    greedy_index=candidates.get(tuple(plan_signature(greedy_plan))) if greedy_plan else None
    out.update(status='PASS',configuration_count=universe.size,cost_evaluation_seconds=cost_s,
        **cost_metrics(selected,table.costs),recursive_aggregate_cost=solution.cost,
        literal_cost_equal=selected==float(table.costs[exact_index]),
        full_configuration_equal=plan_signature(plan)==plan_signature(exact),
        root_action_equal=plan_signature(plan)[0]==plan_signature(exact)[0],
        exact_index=exact_index,recursive_index=recursive_index,
        exact_tie_count=int(np.count_nonzero(table.costs==table.costs[exact_index])),
        unique_configuration_signatures=len(candidates),
        additive_identity_max_abs_difference=max_difference,additive_identity_tolerance=additive_tol,
        complete_configurations_materialized_recursive=1,
        recursive_plan=serialize_plan(plan),exact_plan=serialize_plan(exact),
        feasible_greedy_index=universe.greedy_index,
        actual_greedy_rollout_index=greedy_index,
        greedy_rollout_matches_feasible_proxy=greedy_index==universe.greedy_index,
        greedy_rollout_feasible=greedy_plan is not None,
        cost_table_sha256=sha_array(table.costs))
    art=RUN/'artifacts'/name;art.mkdir(exist_ok=False)
    with (art/'universe.pkl').open('xb') as f:pickle.dump(universe,f,protocol=pickle.HIGHEST_PROTOCOL)
    with (art/'costs.npz').open('xb') as f:np.savez(f,costs=table.costs,leaf=table.mean_visited_leaves,scan=table.mean_refined_points)
    write_json(art/'candidate_scores.json',reference_trace)
    write_json(art/'validation.json',out)
    write_json(JOB/'result.json',out)
    print(json.dumps({k:v for k,v in out.items() if k not in ['recursive_plan','exact_plan','input_manifest','frozen_config']},ensure_ascii=False),flush=True)

def random_search(costs,budget,seed):
    rng=np.random.default_rng(int(seed))
    order=rng.choice(len(costs),size=min(budget,len(costs)),replace=False)
    pos=int(np.argmin(costs[order]));index=int(order[pos])
    return index,[int(i) for i in order]

def search_experiment(name):
    art=RUN/'artifacts'/name
    with (art/'universe.pkl').open('rb') as f:universe=pickle.load(f)
    with np.load(art/'costs.npz') as z:costs=z['costs']
    meta=json.loads((art/'validation.json').read_text());N=len(costs)
    seeds=list(range(20261009,20261029));rows=[];profiles=[]
    for factor in [.5,1.,2.,4.]:
        budget=max(1,int(math.ceil(factor*math.sqrt(N))))
        for seed in seeds:
            for method in ['qmf','random','argmin','exact_enumeration_scan','feasible_greedy_proxy']:
                t=time.perf_counter();threshold=0;verify=0;initial=None;logical=None
                if method=='qmf':
                    r=uniform_qmf(costs,budget=budget,seed=seed)
                    idx=r.selected_index;inspected=list(r.evaluated_indices)
                    threshold=r.accounting.threshold_oracle_calls;verify=r.accounting.verification_cost_calls
                    logical=threshold+verify;initial=float(r.best_cost_trace[0])
                elif method=='random':idx,inspected=random_search(costs,budget,seed);initial=float(costs[inspected[0]])
                elif method=='argmin':idx=int(np.argmin(costs));inspected=range(N)
                elif method=='exact_enumeration_scan':
                    r=exhaustive_search(costs);idx=r.selected_index;inspected=r.evaluated_indices
                else:idx=universe.greedy_index;inspected=[idx]
                elapsed=time.perf_counter()-t
                row={'node':name,'method':method,'budget_factor':factor,'budget':budget,'seed':seed,
                    'N':N,'search_seconds':elapsed,**cost_metrics(float(costs[idx]),costs),
                    'selected_index':idx,'selected_root':universe.configurations[idx].root_action.key,
                    'inspected_candidates':len(inspected),'unique_inspected_candidates':len(set(inspected)),
                    'abstract_threshold_calls':threshold if method=='qmf' else None,
                    'verification_cost_calls':verify if method=='qmf' else None,
                    'abstract_total_calls':logical,'initial_cost':initial,
                    'improved_over_initial':bool(costs[idx]<initial) if initial is not None else None,
                    'uses_all_costs_in_classical_preprocessing':method=='qmf',
                    'status':'PASS','cost_table_sha256':meta['cost_table_sha256']}
                rows.append(row)
            # Measure production subfunctions without modifying their code, same random trace.
            t=time.perf_counter();order=np.argsort(costs,kind='mergesort');sort_s=time.perf_counter()-t
            t=time.perf_counter();oracle=AbstractPhaseCostOracle(costs);setup_s=time.perf_counter()-t
            prior=np.full(N,1./N)
            t=time.perf_counter();profiled=_qmf(oracle,prior,budget=budget,seed=seed,method='Uniform-QMF');sampling_s=time.perf_counter()-t
            canonical=next(r for r in reversed(rows) if r['method']=='qmf')
            assert profiled.selected_index==canonical['selected_index']
            profiles.append({'node':name,'seed':seed,'budget_factor':factor,'budget':budget,
                'standalone_same_mergesort_seconds':sort_s,'oracle_constructor_including_sort_seconds':setup_s,
                'qmf_loop_seconds':sampling_s,'selected_index_matches_official':True})
        # Beam is deterministic. Evaluate once per budget, report its actual inspections.
        for method,width in [('beam16',16),('beam_budget_width',budget)]:
            t=time.perf_counter();r=beam_search(costs,universe,width=width,budget=budget);elapsed=time.perf_counter()-t
            idx=r.selected_index
            rows.append({'node':name,'method':method,'budget_factor':factor,'budget':budget,'seed':None,
                'N':N,'search_seconds':elapsed,**cost_metrics(float(costs[idx]),costs),
                'selected_index':idx,'selected_root':universe.configurations[idx].root_action.key,
                'inspected_candidates':len(r.evaluated_indices),'unique_inspected_candidates':len(set(r.evaluated_indices)),
                'abstract_threshold_calls':None,'verification_cost_calls':None,'abstract_total_calls':None,
                'initial_cost':float(r.best_cost_trace[0]),'improved_over_initial':bool(r.best_cost_trace[-1]<r.best_cost_trace[0]),
                'uses_all_costs_in_classical_preprocessing':False,'status':'PASS','cost_table_sha256':meta['cost_table_sha256']})
    write_csv(JOB/'search_results.csv',rows);write_csv(JOB/'qmf_time_components.csv',profiles)
    write_json(JOB/'result.json',{'status':'PASS','node':name,'rows':len(rows),'seeds':seeds,'budget_factors':[.5,1.,2.,4.],
        'cost_table_sha256':meta['cost_table_sha256'],'data_source':str(art),
        'recursive_exact_search_only':'N/A: requires conditional data/states, not merely an unstructured cost table; measured end-to-end',
        'greedy_note':'feasible production-universe greedy proxy; validation records whether actual fixed-Q R4 rollout matches',
        'time_component_note':'standalone mergesort and paired production subfunctions separately timed; not subtracted from the canonical timing',
        'rss_hwm_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
    print('SEARCH_DONE',name,len(rows),flush=True)

def local_experiment(name,method,seed):
    points,queries,meta,load_s=load_node(name);scorer=Scorer()
    score_before=scorer.score_seconds;rss_before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    start=time.perf_counter();enum_s=cost_s=search_s=0.;universe=None;plan=None;stats={};error=None
    N=None;materialized=0;inspected=0;threshold=verify=None
    try:
        if method=='recursive_exact':
            rec=RecursiveExact(queries,scorer);solution=rec.solve(points)
            if solution is None:raise RuntimeError('no feasible full micro-subtree configuration')
            plan=reconstruct(solution);N=solution.count;stats=rec.stats();materialized=1
            cost_s=rec.leaf_geometry_seconds+rec.cost_seconds
            value=solution.cost
        elif method=='greedy':
            solution=greedy_rollout(points,queries,scorer)
            if solution is None:raise RuntimeError('greedy rollout cannot form full H3')
            plan=reconstruct(solution);materialized=1
            t=time.perf_counter();value=float(current_cost((plan,),queries).costs[0]);cost_s=time.perf_counter()-t
        else:
            t=time.perf_counter();universe=enumerate_current(points,queries,scorer);enum_s=time.perf_counter()-t
            N=universe.size;materialized=N
            t=time.perf_counter();table=current_cost(universe.configurations,queries);cost_s=time.perf_counter()-t
            budget=max(1,int(math.ceil(2.*math.sqrt(N))))
            t=time.perf_counter()
            if method=='qmf':
                r=uniform_qmf(table.costs,budget=budget,seed=seed);idx=r.selected_index
                inspected=len(r.evaluated_indices);threshold=r.accounting.threshold_oracle_calls;verify=r.accounting.verification_cost_calls
            elif method=='random':idx,seen=random_search(table.costs,budget,seed);inspected=len(seen)
            elif method in ['beam16','beam_budget_width']:
                r=beam_search(table.costs,universe,width=16 if method=='beam16' else budget,budget=budget);idx=r.selected_index;inspected=len(r.evaluated_indices)
            elif method=='exact_enumeration':r=exhaustive_search(table.costs);idx=r.selected_index;inspected=N
            elif method=='argmin':idx=int(np.argmin(table.costs));inspected=N
            else:raise ValueError(method)
            search_s=time.perf_counter()-t
            plan=universe.configurations[idx];value=float(table.costs[idx])
    except RuntimeError as ex:error=str(ex)
    end=time.perf_counter();total=end-start
    scoring=scorer.score_seconds-score_before
    if method=='recursive_exact':
        generation=max(total-scoring-cost_s,0.)
    elif method=='greedy':generation=max(total-scoring-cost_s,0.)
    else:generation=max(enum_s-scoring,0.)
    result={'status':'PASS' if plan else 'NO_FEASIBLE_PLAN','node':name,'method':method,'seed':seed,
        'input_path':meta['input_path'],'input_sha256':meta['input_sha256'],'points':len(points),'queries':len(queries),
        'H':H,'K':K,'minimum_child_count':MIN_CHILD,'load_seconds':load_s,'model_load_seconds':scorer.load_seconds,
        'candidate_scoring_seconds':scoring,'configuration_generation_seconds_excluding_scoring':generation,
        'cost_evaluation_seconds':cost_s,'search_seconds':search_s,'total_local_seconds':total,
        'local_start_monotonic':start,'local_end_monotonic':end,
        'process_hwm_before_bytes':rss_before,'process_hwm_after_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'score_calls':scorer.score_calls,'feasible_configuration_count':N,'complete_configurations_materialized':materialized,
        'inspected_candidates':inspected,'abstract_threshold_calls':threshold,'verification_cost_calls':verify,
        'error':error,'recursive_stats':stats,'source_scope':'local diagnostic; no index build, no PostgreSQL'}
    if plan:
        # Validation is deliberately outside measured local optimization time.
        canonical_value=float(current_cost((plan,),queries).costs[0])
        validation=json.loads((RUN/'artifacts'/name/'validation.json').read_text())
        with np.load(RUN/'artifacts'/name/'costs.npz') as src:reference_costs=src['costs']
        result.update(**cost_metrics(canonical_value,reference_costs),optimizer_cost_before_reference_check=value,
            selected_root=plan.root_action.key,selected_root_threshold_hex=plan.root_action.threshold.hex(),
            selected_plan=serialize_plan(plan),reference_cost_table_sha256=validation['cost_table_sha256'])
        if method in ['recursive_exact','exact_enumeration','argmin']:
            assert result['within_8ulp_optimum'],result
    write_json(JOB/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='selected_plan'},ensure_ascii=False),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['inspect','search','local'])
    ap.add_argument('node');ap.add_argument('--method');ap.add_argument('--seed',type=int,default=20261009)
    a=ap.parse_args()
    if a.phase=='inspect':inspect_node(a.node)
    elif a.phase=='search':search_experiment(a.node)
    else:local_experiment(a.node,a.method,a.seed)

if __name__=='__main__':main()
