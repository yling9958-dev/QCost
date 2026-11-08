"""Offline metrics and node-cluster inference from timestamped real search logs."""
from pathlib import Path
import json,hashlib,math,sys
import numpy as np,pandas as pd
from scipy.stats import ttest_1samp
R=Path(__file__).resolve().parents[1];O=R/'03_metrics'
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
def main(cohort_only=None):
    global O
    if cohort_only:
        O=O/('checkpoint_'+cohort_only.lower());O.mkdir(exist_ok=True)
    nodes={n['Node_ID']:n for n in json.loads((R/'01_code_audit/NODE_MANIFEST.json').read_text())};rows=[];histories=[];ledger=[]
    run_diagnostics=[]
    files=sorted((R/'02_raw_logs/formal').glob((cohort_only+'__' if cohort_only else '')+'*__*.json'))
    expected=4800 if cohort_only else 9600;assert len(files)==expected,('Incomplete',len(files))
    for index,p in enumerate(files):
        x=json.loads(p.read_text());assert x['Validation']=='PASS';node=nodes[x['Node_ID']];ref=json.loads(Path(node['Reference_File']).read_text())
        assert len(x['exact_events'])==x['stats']['exact_state_evaluations']
        assert sum(e[2] for e in x['cache_events'])==x['stats']['cache_hits']
        assert all(e['start']<=e['end'] for e in x['candidate_events'])
        assert all(e['elapsed']<=x['Budget_s'] and e['legality_verified_after_return'] for e in x['stats']['incumbent_trace'])
        assert x['stats']['options']==dict(cache=True,feedback=x['Feedback'],strategy='qmf' if x['Selector']=='QMF' else 'random')
        if x['stats']['proven_optimal']:
            assert abs(x['stats']['selected_cost']-ref['optimal_cost'])<=max(1e-9,abs(ref['optimal_cost'])*1e-12)
        assert x['Reference_SHA256']==hashlib.sha256(Path(node['Reference_File']).read_bytes()).hexdigest()
        for b in BUDGETS:rows.append(dict(row_at(x,node,ref,b),Source_File=str(p.resolve())))
        first_opt=next((e for e in x['stats']['incumbent_trace'] if e['offline_optimal']),None)
        run_diag={k:x[k] for k in ['Cohort','Dataset','Node_ID','Seed','Method','T_exact']}
        run_diag.update(Status=x['Status'],Full_Wall_s=x['stats']['total_optimizer_time'],
            Initialization_s=x['stats']['initialization_seconds'],Any_Selector_Used=bool(x['selection_events']),
            Optimal_During_Initialization=bool(first_opt and first_opt['initialization']),
            Optimal_Observed=first_opt is not None,Incumbent_Improvements=max(0,len(x['stats']['incumbent_trace'])-1),
            Candidate_Calls=len(x['candidate_events']),Candidate_Completions=sum(e['complete'] for e in x['candidate_events']),
            Partial_Candidate_Calls=sum(not e['complete'] for e in x['candidate_events']),
            Exact_States=x['stats']['exact_state_evaluations'],Cache_Hits=x['stats']['cache_hits'],
            Terminal_Cost_Calls=x['stats']['terminal_cost_evaluations'])
        run_diag.update({'Phase_'+k:v for k,v in x['stats']['phase_seconds'].items()});run_diagnostics.append(run_diag)
        for e in x['stats']['incumbent_trace']:
            histories.append(dict(Cohort=x['Cohort'],Dataset=x['Dataset'],Node_ID=x['Node_ID'],Seed=x['Seed'],Method=x['Method'],T_exact=x['T_exact'],**e))
        ledger.append(dict(File=str(p.resolve()),SHA256=hashlib.sha256(p.read_bytes()).hexdigest()))
        if index%1000==0:print('Read',index,'/9600',flush=True)
    d=pd.DataFrame(rows);assert len(d)==expected*4
    assert not d.duplicated(['Cohort','Node_ID','Seed','Method','Budget_Ratio']).any()
    assert d.groupby(['Cohort','Node_ID','Method','Budget_Ratio']).Seed.nunique().eq(30).all()
    d.to_csv(O/'QMF_ANYTIME_RAW.csv',index=False);pd.DataFrame(histories).to_csv(O/'INCUMBENT_TRAJECTORIES.csv',index=False)
    pd.DataFrame(ledger).to_csv(O/'RAW_SHA256.csv',index=False)
    rd=pd.DataFrame(run_diagnostics);rd.to_csv(O/'RUN_MECHANISM_RAW.csv',index=False)
    numeric=[c for c in rd.select_dtypes(include=['number','bool']).columns if c!='Seed']
    rd.groupby(['Cohort','Method','Node_ID'])[numeric].mean().groupby(['Cohort','Method']).mean().reset_index().to_csv(O/'RUN_MECHANISM_SUMMARY.csv',index=False)
    nm=d.groupby(['Cohort','Dataset','Node_ID','Method','Budget_Ratio'])[METRICS].mean().reset_index();nm.to_csv(O/'NODE_METRICS.csv',index=False)
    summaries=[]
    for cohort,co in d.groupby('Cohort'):
        for ds,dd in [('Overall',co),*list(co.groupby('Dataset'))]:
            for (method,budget),g in dd.groupby(['Method','Budget_Ratio']):
                for metric in METRICS:
                    vals=g.groupby('Node_ID')[metric].mean().dropna();mean,median,std,lo,hi,ml,mh=interval(vals)
                    summaries.append(dict(Cohort=cohort,Dataset=ds,Method=method,Budget_Ratio=budget,Metric=metric,
                        Mean=mean,Median=median,Std=std,CI95_Low=lo,CI95_High=hi,Median_CI_Low=ml,Median_CI_High=mh,
                        Nodes=len(vals),Total_Nodes=g.Node_ID.nunique(),Valid_Runs=int(g[metric].notna().sum()),Total_Runs=len(g),
                        Node_Coverage=len(vals)/g.Node_ID.nunique(),Feasible_Runs=int(g.Valid_Return.sum()),Failed_Returns=int((~g.Valid_Return).sum()),
                        Optimal_Discovery_Hits=int(g.Time_Optimal_Event.sum()),Censored_Optimal=int((~g.Time_Optimal_Event).sum()),
                        Zero_Completed_Candidate_Runs=int(g.Candidate_Completions.eq(0).sum())))
    summary=pd.DataFrame(summaries);summary.to_csv(O/'QMF_SELECTION_METRICS.csv',index=False)
    pairs=[];details=[]
    for cohort,co in d.groupby('Cohort'):
        for budget,g in co.groupby('Budget_Ratio'):
            for metric in METRICS:
                wide=g.pivot(index=['Dataset','Node_ID','Seed'],columns='Method',values=metric).astype(float)
                for contrast,coeff in CONTRASTS.items():
                    valid=wide[list(coeff)].dropna();delta=sum(valid[k]*v for k,v in coeff.items())
                    vals=delta.groupby(level=['Dataset','Node_ID']).mean();mean,median,std,lo,hi,ml,mh=interval(vals)
                    primary=contrast=='QMF_with_Feedback' and ((metric=='Optimal_Root' and budget==.5) or (metric=='Anytime_AUC' and budget==1.))
                    pairs.append(dict(Cohort=cohort,Budget_Ratio=budget,Contrast=contrast,Metric=metric,Mean_Difference=mean,Median_Difference=median,
                        Std=std,CI95_Low=lo,CI95_High=hi,Median_CI_Low=ml,Median_CI_High=mh,Nodes=len(vals),Paired_Runs=len(valid),
                        Primary=primary,P=pvalue(vals,primary),Pairing='same node/seed with all contrast members defined'))
                    for (ds,node),v in vals.items():details.append(dict(Cohort=cohort,Dataset=ds,Node_ID=node,Budget_Ratio=budget,Contrast=contrast,Metric=metric,Difference=v))
    paired=pd.DataFrame(pairs);paired['Adjusted_P']=np.nan;paired['Multiplicity']='exploratory BH-FDR'
    for cohort,g in paired.groupby('Cohort'):
        ix=g[g.Primary].index;paired.loc[ix,'Adjusted_P']=adjust(paired.loc[ix,'P'],holm=True);paired.loc[ix,'Multiplicity']='Holm two primary endpoints'
        ix=g[~g.Primary].index;paired.loc[ix,'Adjusted_P']=adjust(paired.loc[ix,'P'])
    paired.to_csv(O/'QMF_PAIRED_STATISTICS.csv',index=False);paired[paired.Contrast.ne('QMF_with_Feedback')].to_csv(O/'QMF_FEEDBACK_INTERACTION.csv',index=False)
    detail=pd.DataFrame(details);detail.to_csv(O/'PAIRED_NODE_DIFFERENCES.csv',index=False)
    # Descriptive dataset-specific paired results, and all predeclared complexity groups.
    dsrows=[]
    for keys,g in detail.groupby(['Cohort','Dataset','Budget_Ratio','Contrast','Metric']):
        mean,median,std,lo,hi,ml,mh=interval(g.Difference)
        dsrows.append(dict(zip(['Cohort','Dataset','Budget_Ratio','Contrast','Metric'],keys),Mean_Difference=mean,Median_Difference=median,CI95_Low=lo,CI95_High=hi,Nodes=len(g),Exploratory=True))
    pd.DataFrame(dsrows).to_csv(O/'PAIRED_BY_DATASET.csv',index=False)
    sub=[]
    for cohort,co in d.groupby('Cohort'):
        groups={'N<=1024':co.Configurations<=1024,'N>1024':co.Configurations>1024,
                'All roots tied':co.All_Roots_Tied,'Nonzero gap<=1%':(~co.All_Roots_Tied)&co.Relative_Root_Gap.le(.01),'Gap>1%':co.Relative_Root_Gap.gt(.01)}
        for label,mask in groups.items():
            for metric,budget in [('Optimal_Root',.5),('Anytime_AUC',1.)]:
                g=co[mask&co.Budget_Ratio.eq(budget)&co.Method.isin(['QF','RF'])];wide=g.pivot(index=['Node_ID','Seed'],columns='Method',values=metric)
                vals=(wide.QF.astype(float)-wide.RF.astype(float)).groupby(level='Node_ID').mean() if len(wide) else []
                mean,median,std,lo,hi,ml,mh=interval(vals);sub.append(dict(Cohort=cohort,Group=label,Metric=metric,Budget_Ratio=budget,
                    Nodes=len(vals),Mean_Difference=mean,Median_Difference=median,CI95_Low=lo,CI95_High=hi,Exploratory=True))
    pd.DataFrame(sub).to_csv(O/'PREDECLARED_SUBGROUPS.csv',index=False)
    diag=['Threshold_Updates','Threshold_Acceptance','Below_Incumbent_Proxy_Ratio','Mean_Marked_Fraction','Uniform_QMF_Selections','Mean_Frontier_Size','Candidate_Selections','Unique_Selected_Candidates','Repeated_Selections',
          'Candidate_Completions','Selected_Candidate_Completions','Selected_Evaluations_to_Optimal','Selected_Useful_Ratio',
          'Useful_Evaluations','Exact_State_Completions','Cache_Hits','Cache_Lookups','Cache_Hit_Rate','Selection_Seconds','Selection_Per_Call_s','Selection_Share']
    d.groupby(['Cohort','Method','Budget_Ratio','Node_ID'])[diag].mean().groupby(['Cohort','Method','Budget_Ratio']).mean().reset_index().to_csv(O/'MECHANISM_DIAGNOSTICS.csv',index=False)
    # First-hit CDF retains every administratively censored run in its denominator.
    cdf=[];final=d[d.Budget_Ratio.eq(1.)]
    for (cohort,method),g in final.groupby(['Cohort','Method']):
        for t in np.linspace(0,1,41):
            hits=g.Time_Optimal_Event & g.Time_Optimal_Restricted_T.le(t)
            vals=g.assign(hit=hits).groupby('Node_ID').hit.mean();mean,median,std,lo,hi,ml,mh=interval(vals)
            cdf.append(dict(Cohort=cohort,Method=method,Time_Texact=t,Discovery=mean,CI95_Low=lo,CI95_High=hi,Nodes=len(vals),Runs=len(g)))
    pd.DataFrame(cdf).to_csv(O/'FIRST_OPTIMAL_DISTRIBUTION.csv',index=False)
    coverage=d.groupby(['Cohort','Dataset','Node_ID','Method','Budget_Ratio']).agg(Runs=('Seed','size'),Valid=('Valid_Return','sum'),Optimal=('Optimal_Root','sum'),Optimal_Hits=('Time_Optimal_Event','sum')).reset_index()
    coverage.to_csv(O/'COVERAGE.csv',index=False)
    # Descriptive within-node seed variation; secondary, not a new primary test.
    stability=[]
    for keys,g in d.groupby(['Cohort','Dataset','Node_ID','Method','Budget_Ratio']):
        for metric in ['Optimal_Root','Normalized_Regret','Anytime_AUC','Time_Optimal_Restricted_T','Valid_Return']:
            values=g[metric].dropna().astype(float)
            stability.append(dict(zip(['Cohort','Dataset','Node_ID','Method','Budget_Ratio'],keys),Metric=metric,
                Valid_Seeds=len(values),Total_Seeds=len(g),Seed_Std=values.std(ddof=1),
                Seed_IQR=values.quantile(.75)-values.quantile(.25) if len(values) else np.nan,Exploratory=True))
    stability=pd.DataFrame(stability);stability.to_csv(O/'SEED_STABILITY.csv',index=False)
    stable_pairs=[]
    for keys,g in stability.groupby(['Cohort','Budget_Ratio','Metric']):
        wide=g.pivot(index='Node_ID',columns='Method',values='Seed_Std')[['QF','RF']].dropna()
        mean,median,std,lo,hi,ml,mh=interval(wide.QF-wide.RF)
        stable_pairs.append(dict(zip(['Cohort','Budget_Ratio','Metric'],keys),QMF_Seed_Std=wide.QF.mean(),Random_Seed_Std=wide.RF.mean(),
            Mean_Difference=mean,Median_Difference=median,CI95_Low=lo,CI95_High=hi,Nodes=len(wide),Exploratory=True))
    pd.DataFrame(stable_pairs).to_csv(O/'SEED_STABILITY_COMPARISON.csv',index=False)
    result=dict(Status='CHECKPOINT_ONLY' if cohort_only else 'PASS',Trajectories=expected,Snapshots=expected*4,Nodes=d.Node_ID.nunique(),Seeds=30,Methods=4,
                Original_Nodes=d[d.Cohort.eq('Original')].Node_ID.nunique(),Validation_Nodes=d[d.Cohort.eq('Validation')].Node_ID.nunique(),
                Invalid_Returns=int((~d.Valid_Return).sum()),Budget_Ratios=BUDGETS,Primary_Frozen=True,Secondary_Exploratory=True,
                Mean_Deadline_Overrun_s=final.Deadline_Overrun_s.mean(),Max_Deadline_Overrun_s=final.Deadline_Overrun_s.max())
    (O/'VALIDATION.json').write_text(json.dumps(result,indent=2));print(paired[paired.Primary].to_string(index=False));print(json.dumps(result))
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',choices=['Original','Validation']);main(parser.parse_args().cohort)
