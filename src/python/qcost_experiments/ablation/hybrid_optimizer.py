from .conditional_state import ConditionalEngine,action_id
from .shared_cache import SharedCache
from .recursive_anytime import RecursiveAnytime
from .instrumentation import Instrumentation,BudgetExpired
from . import qmf_frontier_operator,classical_search
import numpy as np
METHODS={
 'M2':dict(cache=False,feedback=False,strategy='recursive'),
 'M3':dict(cache=True,feedback=False,strategy='recursive'),
 'M4':dict(cache=True,feedback=True,strategy='random'),
 'M5':dict(cache=True,feedback=True,strategy='threshold'),
 'M6':dict(cache=True,feedback=True,strategy='bestfirst'),
 'M7':dict(cache=True,feedback=False,strategy='qmf'),
 'M8':dict(cache=True,feedback=True,strategy='qmf')}
LABELS={'M1':'Original Recursive Exact','M2':'Anytime Recursive','M3':'Cached Anytime Recursive','M4':'Hybrid-Random','M5':'Hybrid-Threshold','M6':'Hybrid-BestFirst','M7':'Hybrid-QMF-NoFeedback','M8':'Hybrid-QMF'}
def optimize(points,queries,scorer,method='M8',seed=11,seconds=None,attempts=None,h=3,k=4,model_hash='',data_version='',trace=True,enable_cache=None,enable_incumbent_feedback=None,enable_qmf_operator=None,cache_flags=None,direct_enumeration=False):
    options=dict(METHODS[method])
    if enable_cache is not None:options['cache']=bool(enable_cache)
    if enable_incumbent_feedback is not None:options['feedback']=bool(enable_incumbent_feedback)
    if enable_qmf_operator is False and options['strategy']=='qmf':options['strategy']='threshold'
    meter=Instrumentation(seconds,attempts);cache=SharedCache(options['cache'],**(cache_flags or {}));e=None;events=[];initial_time=None;reason=None;initial_tau=None
    rng=np.random.default_rng(seed)
    try:
        e=ConditionalEngine(points,queries,scorer,cache,meter,h,k,model_hash=model_hash,data_version=data_version)
        e.direct_enumeration=direct_enumeration
        recursion=RecursiveAnytime(e,options['feedback'])
        # Identical first-feasible DFS initialization; strategy/feedback disabled here.
        initializer=RecursiveAnytime(e,False);initializer.initialize()
        initial_time=meter.elapsed();initial_tau=e.incumbent.cost if e.incumbent else float('inf')
        while not e.root.exact:
            meter.check()
            if attempts is not None and meter.attempts>=attempts:reason='attempt_budget';break
            with meter.phase('search_selection'):
                frontier=e.frontier()
                if not frontier:raise AssertionError('Unsolved state without frontier')
                estimates=[e.projected(t,options['feedback']) for t in frontier]
                # Schedule-only ablation: every variant keeps the live QMF threshold.
                tau=e.incumbent.cost if e.incumbent else initial_tau
                if options['strategy']=='recursive':i=recursion.next_classical(frontier);info={'strategy':'recursive'}
                elif options['strategy']=='qmf':i,info=qmf_frontier_operator.select(estimates,tau,rng)
                else:i,info=classical_search.choose(options['strategy'],estimates,tau,rng)
                selected=frontier[i];before=e.incumbent.cost if e.incumbent else None;hits=cache.cache_hits;evals=cache.exact_state_evaluations
                # Counterfactual frozen-info priorities are diagnostics, never oracle answers.
                frozen=[e.projected(t,False) for t in frontier] if options['feedback'] else estimates
                feedback_order_changed=int(np.argmin(estimates))!=int(np.argmin(frozen))
            meter.attempts+=1
            recursion.evaluate(selected);meter.check()
            if trace:
                events.append(dict(iteration=meter.attempts,selected_state=selected.state.key,selected_task=selected.uid,
                    selected_configuration=e.incumbent.signature if e.incumbent else None,cache_hit=cache.cache_hits-hits,
                    exact_evaluation_count=cache.exact_state_evaluations,exact_evaluation_increment=cache.exact_state_evaluations-evals,
                    current_incumbent=e.incumbent.cost if e.incumbent else None,incumbent_improved=e.incumbent is not None and (before is None or e.incumbent.cost<before),
                    frontier=[t.uid for t in frontier],visible_estimates=estimates,next_evaluation_priority=float(estimates[i]),
                    incumbent_feedback_changed_priority=feedback_order_changed,elapsed_time=meter.elapsed(),**info))
    except BudgetExpired as ex:reason=str(ex)
    plan=e.incumbent if e is not None else None
    stats=meter.summary();stats.update(cache.stats());stats.update(method=method,method_name=LABELS[method],seed=seed,options=options,
       status='EXACT' if e is not None and e.root.exact and plan and plan.cost==e.root.best.cost else 'INFEASIBLE' if e is not None and e.root.exact and e.root.best is None else 'FEASIBLE_BUDGET' if plan else 'NO_FEASIBLE_WITHIN_BUDGET',
       proven_optimal=bool(e is not None and e.root.exact and plan is not None and plan.cost==e.root.best.cost),
       selected_cost=plan.cost if plan else None,selected_root=action_id(plan.action) if plan else None,
       selected_configuration=plan.signature if plan else None,initialization_seconds=initial_time,
       optimizer_core_seconds=max(0.,stats['total_optimizer_time']-(initial_time or stats['total_optimizer_time'])),
       time_to_first_feasible=e.incumbent_trace[0]['elapsed'] if e is not None and e.incumbent_trace else None,
       number_of_incumbent_updates=max(0,len(e.incumbent_trace)-1) if e else 0,stop_reason=reason,
       unique_condition_states=len(e.visited_keys) if e else 0,created_state_occurrences=len(e.nodes) if e else 0,
       R4_calls=e.scoring_calls if e else 0,partition_operations=e.partition_operations if e else 0,
       full_configuration_table_size=0,root_incumbent_configurations_materialized=len(e.incumbent_trace) if e else 0,incumbent_trace=e.incumbent_trace if e else [],
       feedback_changed_priority_events=sum(x['incumbent_feedback_changed_priority'] for x in events),
       all_costs_precomputed=False,lower_bound=0.0)
    exported=e.export(plan) if plan else None
    stats.update(exact_state_calls=e.exact_state_calls if e else 0,
                 unique_exact_states=len(e.exact_keys) if e else 0,
                 enumerated_configurations=e.enumerated_configurations if e else 0,
                 direct_configuration_cost_evaluations=e.direct_configuration_cost_evaluations if e else 0)
    stats['total_optimizer_time']=meter.elapsed()
    stats['deadline_overrun_seconds']=max(0.,stats['total_optimizer_time']-seconds) if seconds is not None else 0.
    return dict(stats=stats,events=events,plan=exported,engine=e)
