"""Controlled four-method root-only construction; no evaluation data is loaded."""
import argparse,dataclasses,hashlib,heapq,json,math,resource,time
import numpy as np
from .common import ROOT,CFG,LABELS,torch_setup,js,csvout,sha
torch=torch_setup()
from qmapli.wg_qmf.prior import FrozenR4Prior
from qmapli.wg_qmf.index import _greedy_action,_intersecting_queries,_stable_seed
import qmapli.wg_qmf.configuration as config_module
from qmapli.wg_qmf.configuration import enumerate_joint_configurations
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs
from qmapli.wg_qmf.search import uniform_qmf
from qmapli.workload_action_interaction.actions import split_positions
from qmapli.tree import _new_node,_ExportableIndex
from qmapli.indexes.qmap_nai.index import PrefixHybridIndex
from qmapli.static_format import export_compact_static_index
from qcost_repro.recursive_exact import RecursiveExact,reconstruct

class ObservedR4(FrozenR4Prior):
    def __init__(self,path):
        super().__init__(path);self.records=[]
    def score_actions(self,points,queries,actions):
        result=super().score_actions(points,queries,actions)
        self.records.append({'points':len(points),'queries':len(queries),'legal_candidates':len(actions),'retained_candidates':min(4,len(actions)),
                             'actions':[a.key for a in actions],'scores':result.tolist()})
        return result

def universe(points,q,scorer,h):
    visits=0;original=config_module._enumerate
    def observed(*args,**kwargs):
        nonlocal visits
        visits+=1
        return original(*args,**kwargs)
    config_module._enumerate=observed
    try:
        result=enumerate_joint_configurations(points,q,scorer,depth=h,top_k=4,minimum_fraction=.05,
          minimum_child_count=256,temperature=1.,epsilon=1e-12,maximum_configurations=16384)
    except RuntimeError as e:
        if 'feasible' not in str(e).lower():raise
        result=None
    finally:config_module._enumerate=original
    return result,visits

def choose(points,q,scorer,method,seed,node_id):
    detail={'fallback':False,'fallback_reason':'','planning_attempt':False,'feasible_configurations':None,
            'full_configuration_evaluations':0,'conditional_internal_states':0,'selected_configuration':None,
            'selected_cost':None,'search_budget':None,'selected_action':None}
    times={k:0. for k in ['scoring','configuration_generation','cost_evaluation','search']}
    score0=scorer.score_seconds;rec0=len(scorer.records);started=time.perf_counter()
    if method=='r4_greedy' or len(points)<CFG['minimum_lookahead_points']:
        action=_greedy_action(points,q,scorer,minimum_child_count=256)
        if method!='r4_greedy':detail.update(fallback=True,fallback_reason='below_common_4096_optimization_threshold')
    elif method=='recursive_exact_h3':
        detail['planning_attempt']=True
        rec=RecursiveExact(q,scorer);solution=rec.solve(points,h=3)
        times['cost_evaluation']=rec.leaf_geometry_seconds+rec.cost_seconds
        times['search']=rec.search_seconds
        detail.update(conditional_internal_states=rec.internal_visits,recursive_stats=rec.stats())
        if solution is None:
            detail.update(fallback=True,fallback_reason='no_feasible_full_H3_plan')
            action=_greedy_action(points,q,scorer,minimum_child_count=256)
        else:
            plan=reconstruct(solution,h=3);action=plan.root_action
            detail.update(feasible_configurations=solution.count,selected_cost=solution.cost,selected_configuration=plan.identifier,
                          selected_plan_actions=[dict(path=list(p.path),**p.action.as_dict()) for p in plan.actions])
    else:
        detail['planning_attempt']=True
        h=1 if method=='cost_h1' else 3
        u,visits=universe(points,q,scorer,h);detail['conditional_internal_states']=visits
        if u is None:
            detail.update(fallback=True,fallback_reason=f'no_feasible_full_H{h}_plan')
            action=_greedy_action(points,q,scorer,minimum_child_count=256)
        else:
            t=time.perf_counter();table=evaluate_subtree_costs(u.configurations,q,beta_leaf=CFG['beta_leaf'],beta_point=CFG['beta_point'])
            times['cost_evaluation']=time.perf_counter()-t
            t=time.perf_counter()
            if method=='cost_h1':selected=int(np.argmin(table.costs))
            else:
                budget=int(math.ceil(2*math.sqrt(u.size)))
                run=uniform_qmf(table.costs,budget=budget,seed=_stable_seed(seed,node_id,'uniform_qmf'))
                selected=run.selected_index
                detail.update(search_budget=budget,oracle_accounting=dataclasses.asdict(run.accounting),
                              sampled_configuration_indices=list(run.evaluated_indices),search_best_cost_trace=list(run.best_cost_trace))
            times['search']=time.perf_counter()-t
            plan=u.configurations[selected];action=plan.root_action
            detail.update(feasible_configurations=u.size,full_configuration_evaluations=u.size,selected_configuration_index=selected,
                          selected_configuration=plan.identifier,selected_cost=float(table.costs[selected]),
                          selected_plan_actions=[dict(path=list(p.path),**p.action.as_dict()) for p in plan.actions])
    times['scoring']=scorer.score_seconds-score0
    times['configuration_generation']=time.perf_counter()-started-sum(times.values())
    assert times['configuration_generation']>=-1e-7
    detail['candidate_states']=scorer.records[rec0:]
    if action:detail.update(selected_action=action.key,selected_threshold_hex=float(action.threshold).hex())
    return action,detail,times

def build_index(dataset,workload,method,config,seed,folder):
    points,ids=dataset;queries=workload
    assert config==CFG and method in LABELS
    started=time.perf_counter();scorer=ObservedR4(ROOT/'models/r4.pt');model_seconds=time.perf_counter()-started
    root=_new_node(points,np.empty(0,dtype=np.int64),0,0,0,local_points=points)
    queue=[(-len(points),0,root)];leaves=1;next_id=1;decisions=[];members={}
    totals={k:0. for k in ['scoring','configuration_generation','cost_evaluation','search','layout','serialization']}
    stop_counts={'maximum_depth':0,'minimum_child_size':0,'no_intersecting_training_queries':0,'no_legal_root':0}
    while queue and leaves<CFG['max_leaves']:
        if time.perf_counter()-started>CFG['build_timeout_seconds']:raise TimeoutError('complete build exceeded fixed timeout')
        _,_,node=heapq.heappop(queue);identity=node is root
        indices=np.arange(len(points),dtype=np.int64) if identity else node.point_indices
        local=points if identity else points[indices]
        if node.depth>=CFG['max_depth']:stop_counts['maximum_depth']+=1;continue
        if len(local)<512:stop_counts['minimum_child_size']+=1;continue
        q=_intersecting_queries(queries,node.mbr)
        if not len(q):stop_counts['no_intersecting_training_queries']+=1;continue
        action,detail,times=choose(local,q,scorer,method,seed,node.node_id)
        for k,v in times.items():totals[k]+=v
        detail.update(node_id=node.node_id,depth=node.depth,points=len(local),queries=len(q),bounds=list(node.mbr),seed=seed,
                      node_seed=_stable_seed(seed,node.node_id,'uniform_qmf'),time_breakdown=times)
        decisions.append(detail)
        # Copy membership for after-build diagnostics; this same bookkeeping is used by every method.
        members[f'node_{node.node_id}']=indices.copy()
        if action is None:stop_counts['no_legal_root']+=1;continue
        lp,rp=split_positions(local,action);assert min(len(lp),len(rp))>=256
        li,ri=indices[lp],indices[rp]
        node.split_action=action;node.threshold=action.threshold
        node.children=[_new_node(points,li,node.depth+1,int(node.prefix_code)<<1,next_id),
                       _new_node(points,ri,node.depth+1,(int(node.prefix_code)<<1)|1,next_id+1)]
        next_id+=2;leaves+=1
        for child in node.children:heapq.heappush(queue,(-len(child.point_indices),child.node_id,child))
        node.point_indices=np.empty(0,dtype=np.int64)
        detail.update(committed_action=action.key,committed_threshold_hex=float(action.threshold).hex(),left_points=len(li),right_points=len(ri))
    if root.is_leaf and root.point_indices.size==0:root.point_indices=np.arange(len(points),dtype=np.int64)
    stack=[root]
    while stack:
        node=stack.pop()
        if node.is_leaf:node.suffix_strategy='dual_axis_intersection'
        else:stack.extend(node.children)
    t=time.perf_counter();index=PrefixHybridIndex().build(points,ids,root,static_export=True);totals['layout']=time.perf_counter()-t
    t=time.perf_counter();serialized=export_compact_static_index(_ExportableIndex(index),folder/'index.idx');totals['serialization']=time.perf_counter()-t
    elapsed=time.perf_counter()-started
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    totals['model_loading']=model_seconds;totals['other_construction']=elapsed-sum(totals.values())
    assert totals['other_construction']>=0
    parents={c.node_id:n.node_id for n in index.nodes for c in n.children}
    tree=[{'node_id':n.node_id,'parent_id':parents.get(n.node_id,-1),'depth':n.depth,'axis':n.split_action.axis if n.children else -1,
           'threshold_hex':float(n.threshold).hex() if n.children else '',
           'left_child':n.children[0].node_id if n.children else -1,'right_child':n.children[1].node_id if n.children else -1,
           'storage_start':n.storage_start,'storage_end':n.storage_end} for n in index.nodes]
    csvout(folder/'tree.csv',tree)
    with (folder/'decision_members.npz').open('xb') as f:np.savez(f,**members)
    plans=[d for d in decisions if d['feasible_configurations'] is not None]
    return {'status':'PASS','method':method,'seed':seed,'points':len(points),'build_seconds':elapsed,'serialized_bytes':serialized,
            'index_sha256':sha(folder/'index.idx'),'structure_fingerprint':sha(folder/'tree.csv'),'peak_build_rss_mib':peak,
            'leaf_count':len(index.leaves),'node_count':len(index.nodes),'tree_depth':max(n.depth for n in index.nodes),
            'leaf_occupancies':[n.storage_end-n.storage_start for n in index.leaves],
            'fallback_count':sum(d['fallback'] for d in decisions),'lookahead_calls':sum(d['planning_attempt'] for d in decisions),
            'successful_planning_calls':len(plans),'h3_planning_calls':len(plans) if method.endswith('h3') else 0,
            'average_feasible_configurations':float(np.mean([d['feasible_configurations'] for d in plans])) if plans else None,
            'total_full_configuration_evaluations':sum(d['full_configuration_evaluations'] for d in decisions),
            'conditional_internal_states':sum(d['conditional_internal_states'] for d in decisions),'stop_counts':stop_counts,
            'candidate_scoring_calls':scorer.score_calls,'time_breakdown_seconds':totals,'decisions':decisions,
            'build_timing':CFG['timing'],'postbuild_diagnostics_excluded':True,'torch_version':torch.__version__}

