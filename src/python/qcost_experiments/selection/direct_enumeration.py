"""Direct Cartesian enumeration in the SAME incremental conditional-state DAG.

Adapted from vendor/python/qmapli/wg_qmf/configuration.py::_enumerate:
enumerate every feasible left/right continuation pair, without min-plus DP.
Only already generated candidates are visible. Thus selection, initialization,
state expansion, cache keys, feedback and proof-of-completion stay identical.
The minimum is taken only at the conditional target being updated. Substate
best values are NEVER used to prune its continuation configurations. Recursion
here traverses the configuration space; it is not recursive DP minimization.
"""
import hashlib
from .conditional_state import Plan

def configurations(e,s):
    e.meter.check()
    if s.h==0:
        yield s.best
        return
    if s.actions is None:
        return
    for task in s.actions:
        # The historical enumerator materializes both continuation lists.
        left=tuple(configurations(e,task.children[0]))
        right=tuple(configurations(e,task.children[1]))
        for l in left:
            for r in right:
                e.meter.check()
                sig=hashlib.sha256((str(task.action.axis)+float(task.action.threshold).hex()+l.signature+r.signature).encode()).hexdigest()
                with e.meter.phase('cache_management'):
                    cached=e.cache.configurations.get(sig) if e.cache.configuration_enabled else None
                    if cached is not None:
                        e.cache.cache_hits+=1;e.cache.configuration_hits+=1
                if cached is not None:
                    yield cached
                    continue
                with e.meter.phase('cost_evaluation'):
                    hits=l.hits+r.hits;scans=l.scans+r.scans
                    plan=Plan(hits,scans,e.cost(hits,scans),sig,task.action,l,r,s.bounds,s.point_count)
                    e.direct_configuration_cost_evaluations+=1
                if e.cache.configuration_enabled:
                    with e.meter.phase('cache_management'):e.cache.configurations[sig]=plan
                yield plan

def exact_available(e,s):
    best=None
    for plan in configurations(e,s):
        e.enumerated_configurations+=1
        if best is None or plan.cost<best.cost:best=plan
    return best
