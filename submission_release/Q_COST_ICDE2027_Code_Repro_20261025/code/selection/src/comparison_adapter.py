"""Fresh whole-pipeline timing. Offline reference values are never imported here.

Unmodified original source is retained in vendor. An observer-only AST copy adds
one callback after a complete root candidate; its numerical/control statements
are unchanged. These observations are NOT an anytime return interface.
"""
from . import bootstrap
from .conditional_state import action_id,BL,BP
from .hybrid_optimizer import optimize
import ast,copy,types,sys,time,math,resource
from contextlib import contextmanager
from collections import defaultdict
import numpy as np
import original_recursive_exact as original_module
from qmapli.wg_qmf import configuration as cfg, search as search_module
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs

METHOD_NAMES={'EXACT':'Original Recursive Exact','QMF':'Original CPU Analytic QMF',
 'M2':'Anytime Recursive','M3':'Cached Anytime Recursive','M4':'Hybrid-Random',
 'M5':'Hybrid-Threshold','M6':'Hybrid-BestFirst','M7':'Hybrid-QMF-NoFeedback','M8':'Hybrid-QMF',
 'C_STATE_OFF':'Recursive / state cache OFF','C_TERM_OFF':'Recursive / terminal cache OFF',
 'C_CONFIG_OFF':'Recursive / configuration cache OFF'}

def observed_module():
    source=bootstrap.ROOT/'vendor/python/original_recursive_exact.py'
    tree=ast.parse(source.read_text());before=ast.dump(tree,include_attributes=False)
    target=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='solve')
    additions=[]
    for loop in ast.walk(target):
        if isinstance(loop,ast.For):
            for i,node in list(enumerate(loop.body)):
                if (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and
                    isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='append' and
                    isinstance(node.value.func.value,ast.Name) and node.value.func.value.id=='feasible'):
                    extra=ast.parse('if h == self.observed_h:\n    self.observer(item)').body[0]
                    loop.body.insert(i+1,extra);additions.append((loop,extra))
    assert len(additions)==1
    instrumented=copy.deepcopy(tree)
    for parent,extra in additions:parent.body.remove(extra)
    assert ast.dump(tree,include_attributes=False)==before
    module=types.ModuleType('phase3_observed_exact');sys.modules[module.__name__]=module
    exec(compile(ast.fix_missing_locations(instrumented),str(source)+'[observer-only]','exec'),module.__dict__)
    return module

OBSERVED=observed_module()
class CandidateTimer:
    direction='higher_is_better'
    def __init__(self,base):self.base=base;self.seconds=0.;self.calls=0
    def score_actions(self,*args,**kwargs):
        t=time.perf_counter()
        try:return self.base.score_actions(*args,**kwargs)
        finally:self.seconds+=time.perf_counter()-t;self.calls+=1

@contextmanager
def candidate_timer(module,timer):
    old=module.enumerate_actions
    def wrapped(*a,**kw):
        t=time.perf_counter()
        try:return old(*a,**kw)
        finally:timer.seconds+=time.perf_counter()-t
    module.enumerate_actions=wrapped
    try:yield
    finally:module.enumerate_actions=old

def run(points,queries,model,method,seed=11,seconds=None,attempts=None,h=3,k=4,
        model_hash='',data_version='',trace=True):
    # Model construction/input I/O are shared preconditions; feature prep starts inside.
    t0=time.perf_counter();cpu0=time.process_time();events=[];phases={};plan=None
    if method=='EXACT':
        timer=CandidateTimer(model);observer_time=0.;best=math.inf
        def observer(sol):
            nonlocal observer_time,best
            tick=time.perf_counter()
            from .work_observer import snapshot, observe_original_root
            observe_original_root(sol)
            if sol.cost<best:
                best=sol.cost;events.append(dict(elapsed=tick-t0,cost=sol.cost,root=action_id(sol.action),visibility='internal_observation',**snapshot()))
            observer_time+=time.perf_counter()-tick
        old_k=OBSERVED.K;OBSERVED.K=k
        rec=OBSERVED.RecursiveExact(queries,timer);rec.observed_h=h;rec.observer=observer
        try:
            with candidate_timer(OBSERVED,timer):solution=rec.solve(points,h=h)
        finally:OBSERVED.K=old_k
        t_rebuild=time.perf_counter();plan=OBSERVED.reconstruct(solution,h=h) if solution else None
        rebuilding=time.perf_counter()-t_rebuild
        total=time.perf_counter()-t0
        phases=dict(candidate_generation=timer.seconds,cost_evaluation=rec.leaf_geometry_seconds+rec.cost_seconds,
            search_selection=rec.search_seconds,incumbent_update=observer_time,other=rebuilding)
        phases['state_expansion']=max(0.,total-sum(phases.values()))
        stats=dict(status='EXACT' if plan else 'INFEASIBLE',proven_optimal=plan is not None,
          selected_cost=solution.cost if solution else None,selected_root=action_id(plan.root_action) if plan else None,
          exact_state_evaluations=rec.internal_visits+rec.terminal_visits,terminal_cost_evaluations=len(rec.hit_cache),
          terminal_visits=rec.terminal_visits,unique_condition_states=None,
          cache_hits=rec.terminal_visits-len(rec.hit_cache),cache_misses=len(rec.hit_cache),
          cache_hit_rate=(rec.terminal_visits-len(rec.hit_cache))/max(1,rec.terminal_visits),
          materialized_configurations=int(plan is not None),actual_feasible_configurations=solution.count if solution else 0,
          R4_calls=timer.calls,cache_maintenance_seconds=None,
          original_breakdown_scope='cache operations included in leaf geometry; separate cache time unavailable',
          observer_only=True,original_return_is_blocking=True,frontier_events=[])
    elif method=='QMF':
        if h>3 or k**(2**h-1)>16384:
            return dict(stats=dict(status='NOT_RUN_RESOURCE_GUARD',method=method,h=h,k=k),plan=None)
        timer=CandidateTimer(model)
        try:
            with candidate_timer(cfg,timer):
                universe=cfg.enumerate_joint_configurations(points,queries,timer,depth=h,top_k=k,minimum_child_count=256,maximum_configurations=16384)
        except RuntimeError as ex:
            if 'no feasible full' not in str(ex):raise
            return dict(stats=dict(status='INFEASIBLE',method=method,selected_cost=None,selected_root=None,
                proven_optimal=False,total_optimizer_time=time.perf_counter()-t0,incumbent_trace=[]),plan=None)
        expanded=time.perf_counter()
        table=evaluate_subtree_costs(universe.configurations,queries,beta_leaf=BL,beta_point=BP)
        evaluated=time.perf_counter();best=math.inf;update_seconds=0.
        class ObservedOracle(search_module.AbstractPhaseCostOracle):
            def evaluate(self,index):
                nonlocal best,update_seconds
                value=super().evaluate(index);tick=time.perf_counter()
                from .work_observer import snapshot
                if value<best:
                    best=value;events.append(dict(elapsed=tick-t0,cost=value,root=action_id(universe.configurations[index].root_action),index=int(index),visibility='internal_observation',**snapshot()))
                update_seconds+=time.perf_counter()-tick
                return value
        sort_start=time.perf_counter();oracle=ObservedOracle(table.costs);sorting=time.perf_counter()-sort_start
        budget=int(math.ceil(2*math.sqrt(universe.size))) # frozen formal builder, no reinterpretation
        result=search_module._qmf(oracle,np.full(universe.size,1/universe.size),budget=budget,seed=seed,method='Uniform-QMF')
        plan=universe.configurations[result.selected_index];total=time.perf_counter()-t0
        phases=dict(candidate_generation=timer.seconds,state_expansion=expanded-t0-timer.seconds,
            cost_evaluation=evaluated-expanded,search_selection=total-(evaluated-t0)-update_seconds,
            incumbent_update=update_seconds,other=0.)
        stats=dict(status='FEASIBLE_SEARCH_COMPLETE',proven_optimal=False,selected_cost=result.selected_cost,
            selected_root=action_id(plan.root_action),exact_state_evaluations=None,terminal_cost_evaluations=None,
            materialized_configurations=universe.size,actual_feasible_configurations=universe.size,
            full_cost_evaluations=universe.size,sort_seconds=sorting,abstract_oracle_calls=result.accounting.configuration_cost_evaluations,
            verification_reads=result.accounting.verification_cost_calls,unique_verification_reads=len(set(result.evaluated_indices)),
            search_trials=result.accounting.measurements-1,unsuccessful_trials=result.accounting.measurements-len(events),
            table_preparation_seconds=evaluated-t0,sort_and_table_preparation_seconds=evaluated-t0+sorting,
            cache_hits=None,cache_misses=None,cache_hit_rate=None,cache_maintenance_seconds=None,
            original_breakdown_scope='cached cost-table geometry and lookup combined; sorting included in search',
            R4_calls=timer.calls,observer_only=True,original_return_is_blocking=True,frontier_events=[])
    else:
        base='M3' if method.startswith('C_') else {'B_NOFEEDBACK':'M6','T_NOFEEDBACK':'M5','R_NOFEEDBACK':'M4'}.get(method,method)
        flags={'state_cache':method!='C_STATE_OFF','terminal_cache':method!='C_TERM_OFF','configuration_cache':method!='C_CONFIG_OFF'}
        offset=time.perf_counter()-t0
        result=optimize(points,queries,model,method=base,seed=seed,seconds=None if seconds is None else max(0,seconds-offset),
            attempts=attempts,h=h,k=k,model_hash=model_hash,data_version=data_version,trace=trace,cache_flags=flags,enable_incumbent_feedback=False if method.endswith('_NOFEEDBACK') else None)
        stats=result['stats'];plan=result['plan'];phases=dict(stats.pop('phase_seconds'));events=stats.pop('incumbent_trace')
        for e in events:e['elapsed']+=offset;e['visibility']='available_incumbent'
        total=time.perf_counter()-t0
        phases['other']=phases.get('other',0.)+max(0.,total-sum(phases.values()))
        stats.update(materialized_configurations=stats['root_incumbent_configurations_materialized'],actual_feasible_configurations=None,
            cache_maintenance_seconds=phases.get('cache_management',0.),original_return_is_blocking=False,
            frontier_events=result['events'])
        # Explicitly release cyclic state graphs outside the scientific timer.
        del result
    total=time.perf_counter()-t0
    phases['other']=phases.get('other',0.)+max(0,total-sum(phases.values()))
    stats.update(method=method,method_name=METHOD_NAMES.get(method,method),seed=seed,h=h,k=k,
        total_optimizer_time=total,cpu_seconds=time.process_time()-cpu0,phase_seconds=phases,
        peak_memory_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        memory_scope='worker lifetime RSS high-water mark, not isolated per optimization',
        incumbent_trace=events,time_to_first_feasible=events[0]['elapsed'] if events else None,
        returned_solution_time=total if plan is not None else None,
        proof_time=total if stats.get('proven_optimal') else None,
        number_of_incumbent_updates=max(0,len(events)-1),requested_wall_budget=seconds,
        deadline_overrun_seconds=max(0,total-seconds) if seconds is not None and method not in ['EXACT','QMF'] else None,
        algorithm_version='0.4.0-observation',initialization_policy='original native policy' if method in ['EXACT','QMF'] else 'shared R4 first-feasible DFS',
        full_table_precomputed=method=='QMF')
    return dict(stats=stats,plan=plan)
