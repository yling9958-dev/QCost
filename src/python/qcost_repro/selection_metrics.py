"""Offline metrics and node-cluster inference from timestamped real search logs."""
from pathlib import Path
import json,hashlib,math,sys
import numpy as np,pandas as pd
from scipy.stats import ttest_1samp
BUDGETS=[.25,.5,.75,1.];METHODS=['QF','RF','QN','RN']
METRICS=['Optimal_Root','Near_1pct','Near_5pct','Normalized_Regret','Anytime_AUC','Time_Optimal_Restricted_T',
 'Time_Feasible_Restricted_T','Evaluations_Optimal_Restricted','Useful_Evaluation_Ratio','Valid_Return','Root_Rank',
 'Feasible_Time_Coverage','Current_Incumbent_AUC','Conditional_Feasible_AUC','Selection_Seconds','Selection_Share',
 'Candidate_Completions','Cache_Hit_Rate','Root_Rank_Penalized']
CONTRASTS={'QMF_with_Feedback':{'QF':1,'RF':-1},'QMF_without_Feedback':{'QN':1,'RN':-1},
 'Feedback_with_QMF':{'QF':1,'QN':-1},'Feedback_with_Random':{'RF':1,'RN':-1},
 'Interaction':{'QF':1,'RF':-1,'QN':-1,'RN':1}}
def interval(v):
    v=np.asarray(v,float);v=v[np.isfinite(v)]
    if not len(v):return [np.nan]*7
    rng=np.random.default_rng(20261024);draw=v[rng.integers(0,len(v),(10000,len(v)))]
    lo,hi=np.quantile(draw.mean(1),[.025,.975]);ml,mh=np.quantile(np.median(draw,axis=1),[.025,.975])
    return [float(v.mean()),float(np.median(v)),float(v.std(ddof=1)) if len(v)>1 else 0.,float(lo),float(hi),float(ml),float(mh)]
def pvalue(v,primary=False):
    v=np.asarray(v,float);v=v[np.isfinite(v)]
    if len(v)<2:return np.nan
    if np.all(v==0):return 1.
    if primary:
        rng=np.random.default_rng(20261024);sign=rng.choice([-1,1],size=(20000,len(v)))
        return (1+np.count_nonzero(np.abs((sign*v).mean(1))>=abs(v.mean())-1e-15))/20001
    return float(ttest_1samp(v,0).pvalue) if np.std(v)>0 else 0.
def adjust(values,holm=False):
    p=np.asarray(values,float);result=np.full(len(p),np.nan);ix=np.flatnonzero(np.isfinite(p));order=ix[np.argsort(p[ix])];n=len(order)
    if n:
        ranked=p[order]*(np.arange(n,0,-1) if holm else n/np.arange(1,n+1))
        ranked=np.maximum.accumulate(ranked) if holm else np.minimum.accumulate(ranked[::-1])[::-1]
        result[order]=np.minimum(1,ranked)
    return result
def row_at(x,node,ref,ratio):
    T=x['T_exact'];B=ratio*T;s=max(abs(ref['optimal_cost']),1e-9);tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
    history=[e for e in x['stats']['incumbent_trace'] if e['elapsed']<=B]
    root=history[-1]['root'] if history else None;F=ref['root_costs'];value=(max(0.,F[root]-ref['optimal_cost'])/s) if root else np.nan
    rank=1+sum(c<F[root]-tol for c in F.values()) if root else np.nan
    candidates=[e for e in x['candidate_events'] if e['complete'] and e['end']<=B]
    sels=[e for e in x['selection_events'] if e['selected_time']<=B]
    optimal=next((e for e in history if abs(F[e['root']]-ref['optimal_cost'])<=tol),None)
    first=history[0] if history else None
    best=1.;current=1.;last=0.;auc=0.;cur_auc=0.;uncapped=0.;previous_regret=None
    for e in history:
        dt=e['elapsed']-last;auc+=best*dt;cur_auc+=current*dt
        if previous_regret is not None:uncapped+=previous_regret*dt
        reg=max(0.,F[e['root']]-ref['optimal_cost'])/s
        best=min(best,reg,1.);current=min(1.,reg);previous_regret=reg;last=e['elapsed']
    auc+=best*(B-last);cur_auc+=current*(B-last)
    if previous_regret is not None:uncapped+=previous_regret*(B-last)
    coverage=(B-first['elapsed'])/B if first else 0.
    cache=[e for e in x['cache_events'] if e[0]<=B];hits=sum(e[2] for e in cache)
    thresholds=[e['threshold'] for e in sels] if x['Selector']=='QMF' else None
    selection_seconds=sum(max(0.,min(e['selected_time'],B)-e['selection_start']) for e in x['selection_events'] if e['selection_start']<=B)
    # A selected call still executing at B contributes elapsed selection time, never a completed candidate.
    useful=sum(e['direct_improvements']>0 for e in candidates)
    selected_complete=[e for e in candidates if e['parent'] is None and not e['initialization']]
    row={k:x[k] for k in ['Cohort','Dataset','Node_ID','Seed','Method','Feedback','Selector']}
    row.update(Budget_Ratio=ratio,Budget_s=B,T_exact=T,Optimal_Root=bool(root and abs(F[root]-ref['optimal_cost'])<=tol),
        Near_1pct=bool(root and value<=.01+tol/s),Near_5pct=bool(root and value<=.05+tol/s),Normalized_Regret=value,
        Root_Regret=(value*s if root else np.nan),Root_Rank=rank,Returned_Root=root,Returned_Root_Exact_Cost=F[root] if root else np.nan,
        Root_Rank_Penalized=rank if root else len(F)+1,
        Normalization_Scale=s,Degenerate_Optimum=abs(ref['optimal_cost'])<=1e-9,Valid_Return=bool(root),
        Anytime_AUC=auc/B,Current_Incumbent_AUC=cur_auc/B,Feasible_Time_Coverage=coverage,
        Conditional_Feasible_AUC=uncapped/(coverage*B) if coverage>0 else np.nan,
        Time_Optimal_Event=optimal is not None,Time_Optimal_s=optimal['elapsed'] if optimal else np.nan,
        Time_Optimal_Restricted_s=optimal['elapsed'] if optimal else B,Time_Optimal_Restricted_T=optimal['elapsed']/T if optimal else ratio,
        Time_Feasible_Event=first is not None,Time_Feasible_s=first['elapsed'] if first else np.nan,
        Time_Feasible_Restricted_T=first['elapsed']/T if first else ratio,
        Evaluations_Optimal_Event=optimal is not None,Evaluations_Optimal=optimal['candidate_completed'] if optimal else np.nan,
        Evaluations_Optimal_Restricted=optimal['candidate_completed'] if optimal else len(candidates),
        Candidate_Completions=len(candidates),Useful_Evaluations=useful,Useful_Evaluation_Ratio=useful/len(candidates) if candidates else np.nan,
        Selected_Candidate_Completions=len(selected_complete),
        Selected_Evaluations_to_Optimal=sum(e['end']<=optimal['elapsed'] for e in selected_complete) if optimal else np.nan,
        Selected_Useful_Ratio=sum(e['direct_improvements']>0 for e in selected_complete)/len(selected_complete) if selected_complete else np.nan,
        Candidate_Selections=len(sels),Unique_Selected_Candidates=len({e['task'] for e in sels}),Repeated_Selections=len(sels)-len({e['task'] for e in sels}),
        Exact_State_Completions=sum(e[0]<=B for e in x['exact_events']),Cache_Hits=hits,Cache_Lookups=len(cache),Cache_Hit_Rate=hits/len(cache) if cache else np.nan,
        Selection_Seconds=selection_seconds,Selection_Share=selection_seconds/B,Selection_Per_Call_s=selection_seconds/len(sels) if sels else np.nan,
        Threshold_Updates=sum(a!=b for a,b in zip(thresholds,thresholds[1:])) if thresholds is not None else np.nan,
        Threshold_Acceptance=np.mean([e['selected_marked'] for e in sels]) if thresholds else np.nan,
        Mean_Marked_Fraction=np.mean([e['marked_fraction'] for e in sels]) if thresholds else np.nan,
        Uniform_QMF_Selections=np.mean([e['marked_fraction'] in [0.,1.] for e in sels]) if thresholds else np.nan,
        Mean_Frontier_Size=np.mean([e['frontier_size'] for e in sels]) if sels else np.nan,
        Below_Incumbent_Proxy_Ratio=np.mean([e['selected_below_tau'] for e in sels]) if thresholds else np.nan,
        Configurations=node['Configurations'],Relative_Root_Gap=node['Relative_Root_Gap'],All_Roots_Tied=node['All_Roots_Tied'],
        Run_Status=x['Status'],Final_Wall_s=x['stats']['total_optimizer_time'],Deadline_Overrun_s=x['stats']['deadline_overrun_seconds'])
    assert 0<=row['Anytime_AUC']<=1+1e-12 and 0<=coverage<=1
    return row
