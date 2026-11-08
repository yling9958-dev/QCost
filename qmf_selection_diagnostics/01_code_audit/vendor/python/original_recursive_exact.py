from dataclasses import dataclass
import time
import numpy as np
from qmapli.workload_action_interaction.actions import enumerate_actions, split_positions
from qmapli.wg_qmf.configuration import JointConfiguration, LeafSummary, PartitionSummary, PlannedAction, _bounds, _stable_softmax
BL=1.2779084295340111e-09
BP=3.428255707467659
MIN_CHILD=256
K=4
H=3
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
        self.search_seconds=0.;self.hit_cache={};self.internal_keys=set();self.terminal_keys=set()
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
        search_started=time.perf_counter()
        total_prob=sum(pr for _,pr in feasible)
        best,best_prob=feasible[0]
        for candidate,prob in feasible[1:]:
            if candidate.cost<best.cost:best,best_prob=candidate,prob
        best.count=count
        best.prior=(best_prob/total_prob)*best.left.prior*best.right.prior
        self.search_seconds+=time.perf_counter()-search_started
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
