"""Real-run validation and fixed-node paired analysis; no synthetic measurements."""
from pathlib import Path
import json,hashlib,sys
import pandas as pd,numpy as np
R=Path(__file__).resolve().parents[1];Q=R.parent;O=R/'04_metrics'
NAMES=['Full Hybrid-QMF','w/o QMF Selection','w/o Shared Cache','w/o Incumbent Feedback','w/o Recursive Decomposition']
METRICS={'Optimal_Root_Rate':('A','Optimal_Root',100.),'Mean_Root_Regret':('A','Root_Regret',1.),
 'Mean_Optimization_Time':('B','Optimization_Time_s',1.),'Mean_Exact_States':('B','Exact_State_Evaluations',1.),
 'Valid_Return_Rate':('A','Feasible',100.)}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def interval(values):
    v=np.asarray(values,float);v=v[np.isfinite(v)]
    if not len(v):return (np.nan,)*4
    rng=np.random.default_rng(20261024);samples=v[rng.integers(0,len(v),(10000,len(v)))].mean(1)
    lo,hi=np.quantile(samples,[.025,.975]);return v.mean(),v.std(ddof=1) if len(v)>1 else 0.,lo,hi
def records(folder):
    rows=[];ledger=[]
    for p in sorted(folder.glob('*__*.json')):
        x=json.loads(p.read_text());st=x['stats'];assert x['validation']=='PASS'
        for col,key in [('Optimization_Time_s','total_optimizer_time'),('Exact_State_Evaluations','exact_state_evaluations'),('Cache_Hits','cache_hits'),('Time_Budget_s','deadline_seconds')]:assert x[col]==st[key]
        if x['Variant_ID']=='RANDOM':assert st['method']=='M4' and st['options']==dict(cache=True,feedback=True,strategy='random')
        else:assert st['method']=='M8' and st['options']==dict(cache=True,feedback=True,strategy='qmf')
        trace=st['incumbent_trace']
        if x['Protocol']=='A':assert all(t['elapsed']<=x['Time_Budget_s'] for t in trace)
        if trace:
            assert x['Final_Cost']==trace[-1]['cost'] and x['Final_Root']==trace[-1]['root']
            assert all(a['cost']>=b['cost'] for a,b in zip(trace,trace[1:]))
        if x['Protocol']=='B':assert x['Status']=='EXACT' and x['Optimal_Root'] and st['proven_optimal']
        rows.append({k:v for k,v in x.items() if not isinstance(v,(dict,list))})
        ledger.append(dict(Source_File=str(p.resolve()),SHA256=sha(p)))
    return pd.DataFrame(rows),ledger
def summarize(d):
    rows=[];long=[]
    for ds,gds in [('Overall',d),*list(d.groupby('Dataset'))]:
        for name in NAMES:
            g=gds[gds.Variant.eq(name)];a=g[g.Protocol.eq('A')];b=g[g.Protocol.eq('B')]
            row=dict(Dataset=ds,Variant=name,Valid_Nodes=g.Node_ID.nunique(),Valid_Runs_A=len(a),Valid_Runs_B=len(b),
                     Feasible_Runs_A=int(a.Feasible.sum()),Regret_Valid_Nodes=a[a.Root_Regret.notna()].Node_ID.nunique(),
                     Unavailable_Runs_A=int((~a.Feasible).sum()),Timing_Repeats_B=len(b))
            for metric,(protocol,col,scale) in METRICS.items():
                vals=g[g.Protocol.eq(protocol)].groupby('Node_ID')[col].mean()*scale
                mean,std,lo,hi=interval(vals)
                row.update({metric:mean,metric+'_Std':std,metric+'_CI95_Low':lo,metric+'_CI95_High':hi})
                long.append(dict(Dataset=ds,Variant=name,Metric=metric,Mean=mean,Std=std,CI95_Low=lo,CI95_High=hi,Nodes=int(vals.notna().sum())))
            rows.append(row)
    return pd.DataFrame(rows),pd.DataFrame(long)
def paired(d,names=NAMES):
    rows=[];node_rows=[]
    for metric,(protocol,col,scale) in METRICS.items():
        wide=d[d.Protocol.eq(protocol)].pivot(index=['Dataset','Node_ID','Seed'],columns='Variant',values=col)
        for name in names[1:]:
            delta=(wide[name].astype(float)-wide[names[0]].astype(float))*scale
            vals=delta.groupby(level=['Dataset','Node_ID']).mean().dropna();mean,std,lo,hi=interval(vals)
            rows.append(dict(Variant=name,Reference=names[0],Metric=metric,Delta_Ablated_Minus_Full=mean,Std=std,
                CI95_Low=lo,CI95_High=hi,Paired_Nodes=len(vals),Paired_Seed_Units=int(delta.notna().sum()),
                Pairing='common feasible node/seed returns' if col=='Root_Regret' else 'all paired node/seed units'))
            for (ds,node),value in vals.items():node_rows.append(dict(Dataset=ds,Node_ID=node,Variant=name,Metric=metric,Delta=value))
    return pd.DataFrame(rows),pd.DataFrame(node_rows)
def main():
    new,ledger=records(R/'03_runs/formal');control,cl=records(R/'03_runs/formal/controls')
    assert len(new)==2400 and len(control)==240,'Incomplete new campaign; cannot publish'
    manifest=json.loads((R/'03_runs/formal/manifest.json').read_text());nodes=set(manifest['nodes'])
    assert set(new.Node_ID)==nodes and len(nodes)==40 and set(new.Seed)==set(range(2026101100,2026101130))
    assert new.groupby(['Node_ID','Protocol']).Seed.nunique().eq(30).all()
    assert new.Implementation_Version.eq(manifest['code_sha256']).all()
    old=pd.read_csv(Q/'hybrid_qmf_ablation/04_metrics/ABLATION_RAW_RESULTS.csv',float_precision='round_trip')
    retained=old[~old.Variant.eq('w/o QMF Selection')].copy()
    assert len(retained)==9600 and len(old)==12000
    retained['Role']='reused_historical_variant';retained['Valid_Return']=retained.Feasible
    d=pd.concat([retained,new],ignore_index=True)
    assert len(d)==12000 and not d.duplicated(['Node_ID','Seed','Variant','Protocol']).any()
    assert d.groupby(['Node_ID','Variant','Protocol']).Seed.nunique().eq(30).all()
    assert d.H.eq(3).all() and d.K.eq(4).all()
    a=d[d.Protocol.eq('A')];b=d[d.Protocol.eq('B')]
    assert a.groupby('Node_ID').Time_Budget_s.nunique().eq(1).all()
    assert np.allclose(a.Time_Budget_s,.5*a.T_exact_s,rtol=0,atol=1e-12)
    assert b.Status.eq('EXACT').all() and b.Optimal_Root.all()
    assert d.Root_Regret.dropna().ge(0).all()
    refs={};input_hashes={}
    for x in d.itertuples():
        if x.Reference_File not in refs:
            refs[x.Reference_File]=json.loads(Path(x.Reference_File).read_text());assert sha(x.Reference_File)==x.Reference_SHA256
        ref=refs[x.Reference_File];tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
        if x.Feasible:
            regret=ref['root_costs'][x.Final_Root]-ref['optimal_cost']
            assert abs(regret-x.Root_Regret)<=tol and bool(x.Optimal_Root)==(abs(regret)<=tol)
        else:assert not x.Optimal_Root and pd.isna(x.Root_Regret)
        if x.Role=='new_random_ablation':
            p=Path(manifest['source_phase4'])/'data/nodes'/x.Node_ID/'input.npz'
            if x.Node_ID not in input_hashes:input_hashes[x.Node_ID]=sha(p)
            assert input_hashes[x.Node_ID]==x.Data_SHA256
    for x in new.Node_ID.unique():
        assert set(new[new.Node_ID.eq(x)].Data_SHA256)==set(retained[retained.Node_ID.eq(x)].Data_SHA256)
        assert set(new[new.Node_ID.eq(x)].Reference_SHA256)==set(retained[retained.Node_ID.eq(x)].Reference_SHA256)
    for frame in [new,d,control]:
        frame['Time_Budget']=frame.Time_Budget_s;frame['Optimization_Time']=frame.Optimization_Time_s;frame['Exact_States']=frame.Exact_State_Evaluations
    new.to_csv(R/'QMF_RANDOM_ABLATION_RAW.csv',index=False)
    d.to_csv(O/'FIVE_VARIANT_RAW.csv',index=False);control.to_csv(O/'CONTEMPORANEOUS_FULL_RAW.csv',index=False)
    pd.DataFrame(ledger+cl).to_csv(O/'NEW_RAW_SHA256.csv',index=False)
    summary,long=summarize(d);overall=summary[summary.Dataset.eq('Overall')]
    old_summary=pd.read_csv(Q/'hybrid_qmf_ablation/04_metrics/ABLATION_SUMMARY.csv').set_index('Variant')
    for x in overall.itertuples():
        if x.Variant=='w/o QMF Selection':continue
        for metric in list(METRICS)[:4]:assert np.isclose(getattr(x,metric),old_summary.loc[x.Variant,metric],rtol=1e-13,atol=1e-12)
    overall.to_csv(R/'QMF_RANDOM_ABLATION_SUMMARY.csv',index=False)
    summary[~summary.Dataset.eq('Overall')].to_csv(O/'BY_DATASET.csv',index=False);long.to_csv(O/'METRIC_CONFIDENCE_INTERVALS.csv',index=False)
    values=['Optimal_Root','Root_Regret','Optimization_Time_s','Exact_State_Evaluations','Feasible','Deadline_Overrun_s']
    nm=d.groupby(['Dataset','Node_ID','Variant','Protocol'])[values].agg(['mean','std','count']);nm.columns=['_'.join(c) for c in nm.columns]
    nm.reset_index().to_csv(O/'NODE_STATISTICS.csv',index=False)
    pairs,pnodes=paired(d);pairs.to_csv(O/'PAIRED_DIFFERENCES.csv',index=False);pnodes.to_csv(O/'PAIRED_NODE_DIFFERENCES.csv',index=False)
    # Primary regret means remain untouched; separate comparisons restrict both returns.
    aw=a.pivot(index=['Dataset','Node_ID','Seed'],columns='Variant',values='Root_Regret')
    common=aw.dropna();common_rows=[]
    for name in NAMES:
        vals=common[name].groupby(level=['Dataset','Node_ID']).mean();mean,std,lo,hi=interval(vals)
        common_rows.append(dict(Variant=name,Mean_Root_Regret=mean,Std=std,CI95_Low=lo,CI95_High=hi,Common_Nodes=len(vals),Common_Seed_Units=len(common)))
    pd.DataFrame(common_rows).to_csv(O/'COMMON_FEASIBLE_REGRET.csv',index=False)
    pair_common=aw[[NAMES[0],NAMES[1]]].dropna();pair_rows=[]
    for name in NAMES[:2]:
        vals=pair_common[name].groupby(level=['Dataset','Node_ID']).mean();mean,std,lo,hi=interval(vals)
        pair_rows.append(dict(Variant=name,Mean_Root_Regret=mean,Std=std,CI95_Low=lo,CI95_High=hi,Common_Nodes=len(vals),Common_Seed_Units=len(pair_common)))
    pd.DataFrame(pair_rows).to_csv(O/'FULL_RANDOM_COMMON_FEASIBLE_REGRET.csv',index=False)
    sets={name:sorted(a[a.Variant.eq(name)&a.Root_Regret.notna()].Node_ID.unique()) for name in NAMES}
    coverage=a.groupby(['Dataset','Node_ID','Variant']).agg(Runs=('Seed','size'),Feasible=('Feasible','sum'),
             Mean_Overrun_s=('Deadline_Overrun_s','mean'),Max_Overrun_s=('Deadline_Overrun_s','max')).reset_index()
    coverage.to_csv(O/'BUDGET_AVAILABILITY.csv',index=False)
    # Same-session controls quantify time drift; never replace the four historical rows.
    new_ctrl=pd.concat([control,new[new.Seed.isin(control.Seed.unique())]],ignore_index=True)
    cp,cn=paired(new_ctrl,NAMES[:2]);cp.to_csv(O/'CONTEMPORANEOUS_PAIRED_DIFFERENCES.csv',index=False)
    old_full=retained[retained.Variant.eq(NAMES[0])&retained.Seed.isin(control.Seed.unique())].copy()
    historical_b=old_full[old_full.Protocol.eq('B')].set_index(['Node_ID','Seed'])
    control_b=control[control.Protocol.eq('B')].set_index(['Node_ID','Seed'])
    replay_fields=['Final_Root','Final_Cost','Exact_State_Evaluations','Exact_State_Calls','Unique_Exact_States','Cache_Hits','Terminal_Cost_Calls']
    replay={col:bool(historical_b[col].sort_index().eq(control_b[col].sort_index()).all()) for col in replay_fields}
    (O/'FULL_COMPLETE_REPLAY_CHECK.json').write_text(json.dumps(replay,indent=2))
    assert all(replay.values()),'Contemporaneous Full complete-work mismatch; investigate before publication'
    control_named=control.copy();control_named['Variant']='Contemporaneous Full'
    drift,_=paired(pd.concat([old_full,control_named],ignore_index=True),[NAMES[0],'Contemporaneous Full'])
    drift.to_csv(O/'TIMING_BATCH_DRIFT.csv',index=False)
    calib=[]
    for label,frame in [('Historical Full (same 3 seeds)',old_full),('Contemporaneous Full',control),('Contemporaneous Random (same 3 seeds)',new[new.Seed.isin(control.Seed.unique())])]:
        row={'Campaign':label}
        for metric,(protocol,col,scale) in METRICS.items():row[metric]=frame[frame.Protocol.eq(protocol)].groupby('Node_ID')[col].mean().mean()*scale
        calib.append(row)
    pd.DataFrame(calib).to_csv(O/'CALIBRATION_SUMMARY.csv',index=False)
    # Measured internal work supports mechanism discussion without imputing causes.
    phase_rows=[]
    groups=[('Historical Full',retained[retained.Variant.eq(NAMES[0])]),('New Random',new),('Contemporaneous Full',control)]
    for campaign,frame in groups:
        for x in frame[frame.Protocol.eq('B')].itertuples():
            st=json.loads(Path(x.Source_File).read_text())['stats']
            row=dict(Campaign=campaign,Node_ID=x.Node_ID,Seed=x.Seed,Selection_Attempts=st['attempts'],
                     Exact_States=st['exact_state_evaluations'],Cache_Hits=st['cache_hits'],
                     Terminal_Cost_Calls=st['terminal_cost_evaluations'],Incumbent_Updates=st['number_of_incumbent_updates'])
            row.update({'Phase_'+k:v for k,v in st['phase_seconds'].items()});phase_rows.append(row)
    phases=pd.DataFrame(phase_rows);phases.to_csv(O/'COMPLETE_WORK_RAW.csv',index=False)
    phases.groupby(['Campaign','Node_ID']).mean(numeric_only=True).groupby('Campaign').mean().drop(columns='Seed').to_csv(O/'COMPLETE_WORK_SUMMARY.csv')
    result=dict(Status='PASS',New_Runs=2400,Control_Runs=240,Historical_Rows_Reused=9600,Excluded_Old_Selector_Rows=2400,
        Nodes=40,Seeds=30,All_Complete_Runs_Exact=True,Regret_Node_Sets=sets,Regret_Coverage_Identical=all(v==sets[NAMES[0]] for v in sets.values()),
        Common_Feasible_Seed_Units=len(common),Full_Random_Common_Feasible_Seed_Units=len(pair_common),
        Mean_Random_Overrun_s=new[new.Protocol.eq('A')].Deadline_Overrun_s.mean(),Max_Random_Overrun_s=new[new.Protocol.eq('A')].Deadline_Overrun_s.max(),
        Bootstrap_Seed=20261024,Bootstrap_Draws=10000,Independent_Unit='fixed construction node',Implementation_Version=manifest['code_sha256'])
    (O/'VALIDATION.json').write_text(json.dumps(result,indent=2))
    print(overall[['Variant',*METRICS,'Feasible_Runs_A','Regret_Valid_Nodes']].to_string(index=False))
    print(pairs[pairs.Variant.eq(NAMES[1])].to_string(index=False));print('Contemporaneous paired:');print(cp.to_string(index=False))
if __name__=='__main__':main()
