"""New output-only root-commit adapter; frozen original serialization and kernel."""
from . import bootstrap
from .comparison_adapter import run
from .reference_adapter import scorer,sha
from .conditional_state import action_id
from qmapli.wg_qmf.index import _greedy_action,_intersecting_queries,_stable_seed
from qmapli.workload_action_interaction.actions import split_positions
from qmapli.final_full_scale.database_index import _new_node,_ExportableIndex
from qmapli.indexes.qmap_nai.index import PrefixHybridIndex
from qmapli.benchmark.geolife.qmap_static_format import export_compact_static_index
import numpy as np
import time,heapq,resource

def build(points,ids,queries,method,seed,folder,attempts=32,timeout=900):
    start=time.perf_counter();model=scorer();loading=time.perf_counter()-start
    root=_new_node(points,np.empty(0,dtype=np.int64),0,0,0,local_points=points)
    queue=[(-len(points),0,root)];leaves=1;next_id=1;decisions=[];totals={'model_loading':loading,'optimization':0.,'commit':0.,'layout':0.,'serialization':0.}
    model_hash=sha(bootstrap.ROOT/'data/r4.pt')
    while queue and leaves<128:
        if time.perf_counter()-start>timeout:raise TimeoutError('build budget')
        _,_,node=heapq.heappop(queue);ix=np.arange(len(points)) if node is root else node.point_indices;p=points if node is root else points[ix]
        if node.depth>=8 or len(p)<512:continue
        q=_intersecting_queries(queries,node.mbr)
        if not len(q):continue
        t=time.perf_counter();fallback=None;stats=None
        if len(p)<4096:
            a=_greedy_action(p,q,model,minimum_child_count=256);fallback='below_common_4096'
        else:
            out=run(p,q,model,method=method,seed=_stable_seed(seed,node.node_id,'phase3-v1'),attempts=attempts if method not in ['EXACT','QMF'] else None,seconds=30 if method not in ['EXACT','QMF'] else None,model_hash=model_hash,data_version=f'build:{seed}:{node.node_id}',trace=False)
            stats=out['stats'];plan=out['plan']
            if plan is None:
                if stats['status']=='INFEASIBLE':a=_greedy_action(p,q,model,minimum_child_count=256);fallback='no_feasible_full_H3'
                else:raise TimeoutError('No feasible H3 incumbent within node cap; build aborted, no silent fallback')
            else:a=plan.root_action
        totals['optimization']+=time.perf_counter()-t
        if a is None:continue
        t=time.perf_counter();l,r=split_positions(p,a);li,ri=ix[l],ix[r]
        assert min(len(li),len(ri))>=256
        node.split_action=a;node.threshold=a.threshold
        node.children=[_new_node(points,li,node.depth+1,int(node.prefix_code)<<1,next_id),_new_node(points,ri,node.depth+1,(int(node.prefix_code)<<1)|1,next_id+1)]
        next_id+=2;leaves+=1
        for c in node.children:heapq.heappush(queue,(-len(c.point_indices),c.node_id,c))
        node.point_indices=np.empty(0,dtype=np.int64)
        totals['commit']+=time.perf_counter()-t
        decisions.append(dict(node_id=node.node_id,points=len(p),depth=node.depth,selected_root=action_id(a),committed_root=action_id(node.split_action),fallback=fallback,optimizer=stats))
    if root.is_leaf and root.point_indices.size==0:root.point_indices=np.arange(len(points))
    stack=[root]
    while stack:
        n=stack.pop()
        if n.is_leaf:n.suffix_strategy='dual_axis_intersection'
        else:stack.extend(n.children)
    t=time.perf_counter();index=PrefixHybridIndex().build(points,ids,root,static_export=True);totals['layout']=time.perf_counter()-t
    t=time.perf_counter();size=export_compact_static_index(_ExportableIndex(index),folder/'index.idx');totals['serialization']=time.perf_counter()-t
    elapsed=time.perf_counter()-start;totals['other']=elapsed-sum(totals.values())
    return dict(method=method,seed=seed,status='PASS',build_seconds=elapsed,index_bytes=size,peak_memory_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
       leaves=len(index.leaves),nodes=len(index.nodes),depth=max(n.depth for n in index.nodes),leaf_occupancies=[n.storage_end-n.storage_start for n in index.leaves],
       fallback_count=sum(x['fallback'] is not None for x in decisions),decisions=decisions,time_breakdown=totals,index_sha256=sha(folder/'index.idx'),
       timing_scope='model load through compact serialization; input loading excluded as in frozen protocol',search_budget_kind='post-initialization frontier evaluations; initialization time included')
