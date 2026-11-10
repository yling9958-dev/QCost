"""Observer wrappers: preserve arguments, return values and traversal decisions.

The oracle's local cache counters are inspected once at return using an AST
observer. No offline optimum is present. Snapshot overhead is charged to run.
"""
from contextlib import contextmanager
from collections import Counter
import ast,copy,hashlib
from .memory_metrics import memory
from qcost_experiments.ablation.conditional_state import ConditionalEngine
from qcost_experiments.ablation.shared_cache import SharedCache
from . import comparison_adapter as adapter
from qmapli.wg_qmf import cached_oracle,cost_oracle,configuration

ACTIVE=None
class Observer:
    def __init__(self):
        self.count=Counter();self.keys=set();self.completed=set();self.configs=set();self.newconfigs=set()
    def snapshot(self):
        c=self.count
        return dict(exact_evaluations=c['exact_completed'],terminal_evaluations=c['terminal_work'],
          expanded_states=c['expanded'],cache_lookup_hits=c['lookup_hits'],
          cache_lookup_misses=c['lookup_misses'],unique_configuration_evaluations=len(self.configs),
          **memory())
    def stats(self):
        c=dict(self.count)
        c.update(unique_visited_states=len(self.keys),unique_completed_states=len(self.completed),
          repeated_completed_evaluations=self.count['exact_completed']-len(self.completed),
          unique_complete_root_configurations=len(self.configs),unique_combination_evaluations=len(self.newconfigs))
        return c

def snapshot():
    return ACTIVE.snapshot() if ACTIVE else {}

@contextmanager
def observe():
    global ACTIVE
    assert ACTIVE is None
    ob=Observer();ACTIVE=ob;patches=[]
    def patch(obj,name,value):
        patches.append((obj,name,getattr(obj,name)));setattr(obj,name,value)
    old_get=SharedCache.get_state
    def get(self,key):
        if self.state_enabled:
            hit=key in self.states;ob.count['state_hits' if hit else 'state_misses']+=1
            ob.count['lookup_hits' if hit else 'lookup_misses']+=1
        return old_get(self,key)
    patch(SharedCache,'get_state',get)
    old_record=SharedCache.record
    def record(self,s):
        if s.exact and not self.entries[s.uid].exact:
            ob.count['exact_completed']+=1;ob.completed.add(s.key)
        return old_record(self,s)
    patch(SharedCache,'record',record)
    old_state=ConditionalEngine.state
    def state(self,ids,h):
        result=old_state(self,ids,h);ob.count['state_requests']+=1;ob.keys.add(result.key);return result
    patch(ConditionalEngine,'state',state)
    old_expand=ConditionalEngine.expand
    def expand(self,s):
        if not s.exact and s.actions is None:ob.count['expanded']+=1
        return old_expand(self,s)
    patch(ConditionalEngine,'expand',expand)
    old_leaf=ConditionalEngine.leaf_work
    def leaf(self,s):
        hit=self.cache.terminal_enabled and (self.context_hash,s.bounds,s.point_count) in self.cache.terminal
        if self.cache.terminal_enabled:
            ob.count['terminal_hits' if hit else 'terminal_misses']+=1
            ob.count['lookup_hits' if hit else 'lookup_misses']+=1
        if not hit:ob.count['terminal_work']+=1
        return old_leaf(self,s)
    patch(ConditionalEngine,'leaf_work',leaf)
    old_combine=ConditionalEngine.combine
    def combine(self,t):
        before=self.cache.configuration_hits
        result=old_combine(self,t)
        if result is not None:
            hit=self.cache.configuration_hits>before
            if self.cache.configuration_enabled:
                ob.count['configuration_hits' if hit else 'configuration_misses']+=1
                ob.count['lookup_hits' if hit else 'lookup_misses']+=1
            if not hit:
                ob.count['combination_evaluations']+=1;ob.newconfigs.add(result.signature)
                if t.state is self.root:
                    ob.count['complete_root_configuration_evaluations']+=1;ob.configs.add(result.signature)
        return result
    patch(ConditionalEngine,'combine',combine)
    old_update=ConditionalEngine._update
    def update(self,s):
        n=len(self.incumbent_trace)
        result=old_update(self,s)
        # Recursive updates may append multiple events before unwinding.
        for e in self.incumbent_trace[n:]:
            if 'exact_evaluations' not in e:e.update(ob.snapshot())
        return result
    patch(ConditionalEngine,'_update',update)
    cls=adapter.OBSERVED.RecursiveExact;old_solve=cls.solve
    def solve(self,points,h=3,bounds=None):
        key=(h,hashlib.sha256(points.tobytes()).hexdigest());ob.keys.add(key);ob.count['state_requests']+=1
        if h>0:ob.count['expanded']+=1
        result=old_solve(self,points,h,bounds)
        ob.count['exact_completed']+=1;ob.completed.add(key)
        return result
    patch(cls,'solve',solve)
    old_terminal=cls.leaf_solution
    def terminal(self,points,bounds):
        hit=bounds in self.hit_cache
        ob.count['terminal_hits' if hit else 'terminal_misses']+=1
        ob.count['lookup_hits' if hit else 'lookup_misses']+=1
        if not hit:ob.count['terminal_work']+=1
        return old_terminal(self,points,bounds)
    patch(cls,'leaf_solution',terminal)
    old_enum=configuration._enumerate
    def enum(points,queries,scorer,**kw):
        key=(kw['depth'],hashlib.sha256(points.tobytes()).hexdigest());ob.keys.add(key)
        ob.count['state_requests']+=1;ob.count['expanded']+=1
        return old_enum(points,queries,scorer,**kw)
    patch(configuration,'_enumerate',enum)
    # One callback accesses local dictionaries after actual cache work finishes.
    tree=ast.parse(__import__('inspect').getsource(cached_oracle.cached_work_metrics));before=ast.dump(tree)
    fn=tree.body[0];callback=ast.parse('_phase4_observe_cache(locals())').body[0]
    fn.body.insert(-1,callback);inst=copy.deepcopy(tree);fn.body.remove(callback);assert ast.dump(tree)==before
    def cache_done(local):
        n=len(local['configurations']);leaf_count=sum(len(c.leaves) for c in local['configurations']);part_count=sum(len(c.partitions) for c in local['configurations'])
        unique_leaf=len(local['leaf_counts']);unique_part=len(local['partitions']);unique_mbr=len(local['hits'])
        ob.count.update(full_table_evaluations=n,leaf_contribution_aggregations=leaf_count,
          terminal_work=unique_leaf,mbr_geometry_evaluations=unique_mbr,
          table_leaf_cache_hits=leaf_count-unique_leaf,table_leaf_cache_misses=unique_leaf,
          table_partition_cache_hits=part_count-unique_part,table_partition_cache_misses=unique_part)
    namespace=dict(cached_oracle.__dict__,_phase4_observe_cache=cache_done)
    exec(compile(ast.fix_missing_locations(inst),'<Phase4 cache observer>','exec'),namespace)
    patch(cost_oracle,'cached_work_metrics',namespace['cached_work_metrics'])
    try:yield ob
    finally:
        for obj,name,old in reversed(patches):setattr(obj,name,old)
        ACTIVE=None


def observe_original_root(sol):
    if ACTIVE is None:return
    def signature(s):
        if s.action is None:return ('leaf',s.leaf.point_count,s.leaf.bounds)
        return (s.action.axis,float(s.action.threshold).hex(),signature(s.left),signature(s.right))
    ACTIVE.configs.add(signature(sol));ACTIVE.count['complete_root_configuration_evaluations']+=1
