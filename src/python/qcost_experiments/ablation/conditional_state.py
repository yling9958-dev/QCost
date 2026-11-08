from dataclasses import dataclass,field
import hashlib,json
import numpy as np
from qmapli.workload_action_interaction.actions import enumerate_actions,split_positions
from qmapli.wg_qmf.configuration import JointConfiguration,PlannedAction,LeafSummary,PartitionSummary
BL=1.2779084295340111e-09
BP=3.428255707467659
@dataclass(frozen=True)
class Plan:
    hits:int
    scans:int
    cost:float
    signature:str
    action:object=None
    left:object=None
    right:object=None
    bounds:tuple=()
    points:int=0
@dataclass(eq=False)
class State:
    key:str
    uid:str
    ids:object
    h:int
    bounds:tuple
    point_count:int=0
    parents:list=field(default_factory=list)
    actions:object=None
    best:object=None
    exact:bool=False
    proxy:float=0.
@dataclass(eq=False)
class ActionTask:
    state:State
    rank:int
    action:object
    score:float
    children:tuple
    proxy:float
    uid:str
    started:bool=False
    frozen_estimate:float|None=None
class ConditionalEngine:
    def __init__(self,points,queries,scorer,cache,meter,h=3,k=4,min_child=256,minimum_fraction=.05,model_hash='',data_version=''):
        self.points=np.ascontiguousarray(points,dtype=np.float64);self.queries=np.ascontiguousarray(queries,dtype=np.float64)
        if not len(self.points) or not len(self.queries):raise ValueError('nonempty data and query context required')
        self.scorer=scorer;self.cache=cache;self.meter=meter;self.k=k;self.min_child=min_child;self.minimum_fraction=minimum_fraction
        self.nodes=[];self.tasks=[];self.incumbent=None;self.incumbent_trace=[];self.sequence=0;self.scoring_calls=0;self.partition_operations=0
        self.visited_keys=set();self.notify_callback=None
        self.direct_enumeration=False;self.enumerated_configurations=0;self.direct_configuration_cost_evaluations=0
        self.exact_state_calls=0;self.exact_keys=set()
        with meter.phase('cache_management'):
            context=dict(points=hashlib.sha256(self.points.tobytes()).hexdigest(),queries=hashlib.sha256(self.queries.tobytes()).hexdigest(),
              model=model_hash,data_version=data_version,k=k,min_child=min_child,fraction=minimum_fraction,BL=BL,BP=BP,
              candidate_rules='frozen-quantiles-0.25-0.375-0.5-0.625-0.75-v1',precision='float64',denominator=len(queries))
            self.context_hash=hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()
        self.root=self.state(np.arange(len(points),dtype=np.int64),h)
    def cost(self,hits,scans):return BL*(float(hits)/len(self.queries))+BP*(float(scans)/len(self.queries))
    def state(self,ids,h):
        self.meter.check()
        self.exact_state_calls+=1
        with self.meter.phase('cache_management'):
            ids=np.ascontiguousarray(ids,dtype=np.int64)
            key=self.context_hash+':'+str(h)+':'+hashlib.sha256(ids.tobytes()).hexdigest()
            self.visited_keys.add(key);old=self.cache.get_state(key)
            if old is not None:return old
        with self.meter.phase('state_expansion'):
            p=self.points[ids];bounds=tuple(float(x) for x in np.r_[p.min(0),p.max(0)])
            uid=key+':'+str(self.sequence);self.sequence+=1;s=State(key,uid,ids,h,bounds,len(ids));self.nodes.append(s)
        with self.meter.phase('cache_management'):self.cache.put_state(s)
        # One-region terminal work is a documented proxy when h>0, never an exact F_h.
        hits,scans=self.leaf_work(s);s.proxy=self.cost(hits,scans)/(2**h)
        if h==0:
            s.best=Plan(hits,scans,self.cost(hits,scans),'L:'+key,bounds=bounds,points=len(ids));s.exact=True;self.cache.record(s);self.exact_keys.add(s.key)
            s.ids=None
        return s
    def leaf_work(self,s):
        key=(self.context_hash,s.bounds,s.point_count)
        with self.meter.phase('cache_management'):
            if self.cache.terminal_enabled and key in self.cache.terminal:
                self.cache.cache_hits+=1;return self.cache.terminal[key]
            self.cache.cache_misses+=1
        with self.meter.phase('cost_evaluation'):
            q=self.queries;x0,y0,x1,y1=s.bounds
            hits=int(np.count_nonzero((q[:,2]>=x0)&(q[:,0]<=x1)&(q[:,3]>=y0)&(q[:,1]<=y1)));value=(hits,hits*s.point_count);self.cache.terminal_cost_evaluations+=1
        if self.cache.terminal_enabled:
            with self.meter.phase('cache_management'):self.cache.terminal[key]=value
        return value
    def expand(self,s):
        self.meter.check()
        if s.exact or s.actions is not None:return
        with self.meter.phase('candidate_generation'):
            p=self.points[s.ids];acts=tuple(a for a in enumerate_actions(p,self.minimum_fraction) if a.valid and min(a.left_count,a.right_count)>=self.min_child)
            if acts:
                scores=np.asarray(self.scorer.score_actions(p,self.queries,acts),dtype=float);self.scoring_calls+=1
                order=sorted(range(len(acts)),key=lambda i:(-scores[i],acts[i].key))[:self.k]
            else:order=[]
        self.meter.check();s.actions=[]
        for rank,i in enumerate(order):
            self.meter.check()
            with self.meter.phase('state_expansion'):
                a=acts[i];li,ri=split_positions(p,a);self.partition_operations+=1;leftids=s.ids[li];rightids=s.ids[ri]
            left=self.state(leftids,s.h-1);right=self.state(rightids,s.h-1)
            t=ActionTask(s,rank,a,float(scores[i]),(left,right),left.proxy+right.proxy,s.uid+':a'+str(rank))
            s.actions.append(t);left.parents.append(t);right.parents.append(t);self.tasks.append(t)
        self.update(s)
    def combine(self,t):
        l,r=t.children
        if l.best is None or r.best is None:return None
        signature=hashlib.sha256((str(t.action.axis)+float(t.action.threshold).hex()+l.best.signature+r.best.signature).encode()).hexdigest()
        with self.meter.phase('cache_management'):
            if self.cache.configuration_enabled and signature in self.cache.configurations:
                self.cache.cache_hits+=1;self.cache.configuration_hits+=1;return self.cache.configurations[signature]
        with self.meter.phase('cost_evaluation'):
            hits=l.best.hits+r.best.hits;scans=l.best.scans+r.best.scans
            p=Plan(hits,scans,self.cost(hits,scans),signature,t.action,l.best,r.best,t.state.bounds,t.state.point_count)
        if self.cache.configuration_enabled:
            with self.meter.phase('cache_management'):self.cache.configurations[signature]=p
        return p
    def update(self,s):
        with self.meter.phase('incumbent_update'):self._update(s)
    def _update(self,s):
        old=s.best;was=s.exact
        if s.h>0 and s.actions is not None:
            if self.direct_enumeration:
                from .direct_enumeration import exact_available
                s.best=exact_available(self,s)
            else:
                candidates=[self.combine(t) for t in s.actions];feasible=[p for p in candidates if p is not None]
                if feasible:s.best=min(feasible,key=lambda p:p.cost)
            s.exact=all(any(c.exact and c.best is None for c in t.children) or all(c.exact for c in t.children) for t in s.actions)
        with self.meter.phase('cache_management'):self.cache.record(s)
        if s.exact:s.ids=None;self.exact_keys.add(s.key)
        changed=(old is None and s.best is not None) or (old is not None and s.best is not None and old.cost!=s.best.cost) or was!=s.exact
        if s is self.root and s.best is not None:
            # A computation completing after the deadline is logged but cannot improve returned incumbent.
            allowed=self.meter.seconds is None or self.meter.elapsed()<=self.meter.seconds
            if allowed and (self.incumbent is None or s.best.cost<self.incumbent.cost):
                self.incumbent=s.best;self.incumbent_trace.append(dict(elapsed=self.meter.elapsed(),cost=s.best.cost,root=action_id(s.best.action),configuration=s.best.signature))
        if changed:
            for parent in s.parents:self.update(parent.state)
    def frontier(self):
        return [t for t in self.tasks if not t.started and not t.state.exact and not any(c.exact and c.best is None for c in t.children)]
    def projected(self,t,feedback=True):
        if not feedback and t.frozen_estimate is not None:return t.frozen_estimate
        memo={}
        def outside(s):
            if s is self.root:return 0.
            if s.uid in memo:return memo[s.uid]
            values=[]
            for p in s.parents:
                sibling=p.children[1] if p.children[0] is s else p.children[0]
                v=sibling.best.cost if feedback and sibling.best else sibling.proxy
                values.append(outside(p.state)+v)
            memo[s.uid]=min(values) if values else 0.;return memo[s.uid]
        val=outside(t.state)+sum(c.best.cost if feedback and c.best else c.proxy for c in t.children)
        if not feedback:t.frozen_estimate=val
        return val
    def export(self,plan):
        actions=[];leaves=[];parts=[]
        def walk(p,path):
            if p.action is None:leaves.append(LeafSummary(p.points,p.bounds));return
            actions.append(PlannedAction(path,p.action));parts.append(PartitionSummary(path,p.left.bounds,p.right.bounds));walk(p.left,path+(0,));walk(p.right,path+(1,))
        walk(plan,());return JointConfiguration(tuple(actions),tuple(leaves),tuple(parts),1.,self.root.h)
def action_id(a):return None if a is None else f'{a.axis}:{float(a.threshold).hex()}'
