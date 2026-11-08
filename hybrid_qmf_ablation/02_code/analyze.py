"""Recompute every statistic from immutable measured per-run JSON checkpoints."""
from pathlib import Path
import json,hashlib,argparse,csv
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
VARIANTS=['Full Hybrid-QMF','w/o QMF Selection','w/o Shared Cache','w/o Incumbent Feedback','w/o Recursive Decomposition']
METRICS={'Optimal_Root_Rate':('A','Optimal_Root',100.),'Mean_Root_Regret':('A','Root_Regret',1.),
         'Mean_Optimization_Time':('B','Optimization_Time_s',1.),'Mean_Exact_States':('B','Exact_State_Evaluations',1.)}
SEEDS=set(range(2026101100,2026101130))

def interval(values):
    v=np.asarray(values,float);v=v[np.isfinite(v)]
    if not len(v):return (np.nan,np.nan,np.nan,np.nan)
    rng=np.random.default_rng(20261024)
    means=v[rng.integers(0,len(v),(10000,len(v)))].mean(axis=1)
    low,high=np.quantile(means,[.025,.975])
    return float(v.mean()),float(v.std(ddof=1)) if len(v)>1 else 0.,float(low),float(high)

def summarize(frame,dataset='Overall'):
    rows=[];long=[]
    for variant in VARIANTS:
        g=frame[frame.Variant.eq(variant)];a=g[g.Protocol.eq('A')];b=g[g.Protocol.eq('B')]
        r=dict(Dataset=dataset,Variant=variant,Valid_Nodes=g.Node_ID.nunique(),Valid_Runs=len(g),
               Valid_Runs_A=len(a),Valid_Runs_B=len(b),Feasible_Runs_A=int(a.Feasible.sum()),
               Unavailable_Runs_A=int((~a.Feasible).sum()),Regret_Valid_Nodes=a[a.Root_Regret.notna()].Node_ID.nunique(),
               Timing_Repeats_B=len(b),Pooled_Feasible_Root_Regret=float(a.Root_Regret.mean()))
        stds={};cis={}
        for metric,(protocol,column,scale) in METRICS.items():
            v=g[g.Protocol.eq(protocol)].groupby('Node_ID')[column].mean()*scale
            mean,std,lo,hi=interval(v)
            r[metric]=mean;r[metric+'_Std']=std;r[metric+'_CI95_Low']=lo;r[metric+'_CI95_High']=hi
            stds[metric]=std;cis[metric]=[lo,hi]
            long.append(dict(Dataset=dataset,Variant=variant,Metric=metric,Mean=mean,Std=std,CI95_Low=lo,CI95_High=hi,
                             Valid_Nodes=int(v.notna().sum()),Independent_Unit='fixed node',Bootstrap_Resamples=10000))
        r['Std']=json.dumps(stds);r['CI95']=json.dumps(cis);rows.append(r)
    return rows,long

def main(partial=False):
    paths=sorted((ROOT/'03_runs/formal').glob('*__*json'));rows=[];receipts=[]
    for p in paths:
        try:x=json.loads(p.read_text())
        except json.JSONDecodeError:
            if partial:continue
            raise
        st=x['stats']
        assert x['Optimization_Time_s']==st['total_optimizer_time']
        assert x['Exact_State_Evaluations']==st['exact_state_evaluations']
        assert x['Cache_Hits']==st['cache_hits']
        assert x['Time_Budget_s']==st['deadline_seconds']
        trace=st['incumbent_trace']
        if x['Protocol']=='A':assert all(e['elapsed']<=x['Time_Budget_s'] for e in trace)
        if trace:
            assert x['Final_Cost']==trace[-1]['cost'] and x['Final_Root']==trace[-1]['root']
            assert all(a['cost']>=b['cost'] for a,b in zip(trace,trace[1:]))
        receipts.append(dict(Source_File=str(p.resolve()),SHA256=hashlib.sha256(p.read_bytes()).hexdigest()))
        rows.append({k:v for k,v in x.items() if not isinstance(v,(dict,list))})
    d=pd.DataFrame(rows);out=ROOT/'04_metrics';out.mkdir(exist_ok=True)
    if not len(d):raise RuntimeError('No measured data')
    assert not d.duplicated(['Node_ID','Seed','Variant','Protocol']).any()
    manifest=json.loads((ROOT/'03_runs/formal/manifest.json').read_text());nodes=set(manifest['nodes'])
    complete=(len(d)==12000 and set(d.Node_ID)==nodes and len(nodes)==40 and set(d.Seed)==SEEDS)
    if not partial:assert complete,'Incomplete campaign; publication blocked'
    assert d.validation.eq('PASS').all() and d.Implementation_Version.nunique()==1
    assert d.Protocol.isin(['A','B']).all()
    b=d[d.Protocol.eq('B')];assert b.Status.eq('EXACT').all() and b.Optimal_Root.all()
    deterministic=b[b.Variant.eq('w/o QMF Selection')]
    for column in ['Final_Root','Final_Cost','Exact_State_Evaluations','Terminal_Cost_Calls']:
        assert deterministic.groupby('Node_ID')[column].nunique().le(1).all(),column
    assert (d.Root_Regret.dropna()>=0).all()
    if complete:assert d.groupby(['Node_ID','Variant','Protocol']).Seed.nunique().eq(30).all()
    for _,g in d[d.Protocol.eq('A')].groupby('Node_ID'):assert g.Time_Budget_s.nunique()==1
    assert (d[d.Variant.eq('w/o Shared Cache')].Cache_Hits==0).all()
    assert (d.Exact_State_Evaluations>=d.Unique_Exact_States).all()
    # Validate quality again directly from reference tables, not stored summary labels.
    refs={}
    for row in d.itertuples():
        if row.Reference_File not in refs:refs[row.Reference_File]=json.loads(Path(row.Reference_File).read_text())
        ref=refs[row.Reference_File]
        if row.Feasible:
            regret=ref['root_costs'][row.Final_Root]-ref['optimal_cost'];tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
            assert abs(regret-row.Root_Regret)<=tol and bool(row.Optimal_Root)==(abs(regret)<=tol)
        else:assert not row.Optimal_Root and pd.isna(row.Root_Regret)
    prefix='PARTIAL_' if partial and not complete else ''
    primary=['Dataset','Node_ID','Seed','Variant','Protocol','Time_Budget_s','Optimal_Root','Root_Regret',
             'Optimization_Time_s','Exact_State_Evaluations','Terminal_Cost_Calls','Cache_Hits','Final_Cost','Status','Source_File']
    d[primary+[c for c in d if c not in primary]].to_csv(out/(prefix+'ABLATION_RAW_RESULTS.csv'),index=False)
    pd.DataFrame(receipts).to_csv(out/(prefix+'RAW_SHA256.csv'),index=False)
    overall,long=summarize(d);by=[]
    for dataset,g in d.groupby('Dataset'):
        s,l=summarize(g,dataset);by+=s;long+=l
    summary=pd.DataFrame(overall);summary.to_csv(out/(prefix+'ABLATION_SUMMARY.csv'),index=False)
    pd.DataFrame(by).to_csv(out/(prefix+'ABLATION_BY_DATASET.csv'),index=False)
    pd.DataFrame(long).to_csv(out/(prefix+'METRIC_CONFIDENCE_INTERVALS.csv'),index=False)
    values=['Optimal_Root','Root_Regret','Optimization_Time_s','Exact_State_Evaluations','Terminal_Cost_Calls',
            'Cache_Hits','Unique_Exact_States','Exact_State_Calls','Enumerated_Configurations','Direct_Configuration_Cost_Evaluations','Deadline_Overrun_s','Feasible']
    nm=d.groupby(['Dataset','Node_ID','Variant','Protocol'])[values].agg(['mean','std','count']);nm.columns=['_'.join(c) for c in nm.columns]
    nm.reset_index().to_csv(out/(prefix+'NODE_STATISTICS.csv'),index=False)
    paired=[];differences=[]
    for metric,(protocol,column,scale) in METRICS.items():
        g=d[d.Protocol.eq(protocol)];wide=g.pivot(index=['Dataset','Node_ID','Seed'],columns='Variant',values=column)
        for variant in VARIANTS[1:]:
            if variant not in wide or VARIANTS[0] not in wide:continue
            delta=(wide[variant].astype(float)-wide[VARIANTS[0]].astype(float))*scale
            # Regret pairing uses only seed pairs that both actually returned a root.
            node_delta=delta.groupby(level=['Dataset','Node_ID']).mean().dropna()
            mean,std,lo,hi=interval(node_delta)
            paired.append(dict(Variant=variant,Reference=VARIANTS[0],Metric=metric,Delta_Ablated_Minus_Full=mean,
                Std=std,CI95_Low=lo,CI95_High=hi,Paired_Nodes=len(node_delta),Paired_Seed_Units=int(delta.notna().sum()),
                Pairing='common feasible seed pairs' if column=='Root_Regret' else 'all valid paired seed units'))
            for (dataset,node),value in node_delta.items():differences.append(dict(Dataset=dataset,Node_ID=node,Variant=variant,Metric=metric,Delta=value))
    pd.DataFrame(paired).to_csv(out/(prefix+'PAIRED_DIFFERENCES.csv'),index=False)
    pd.DataFrame(differences).to_csv(out/(prefix+'PAIRED_NODE_DIFFERENCES.csv'),index=False)
    a=d[d.Protocol.eq('A')]
    feasibility=a.pivot(index=['Dataset','Node_ID','Seed'],columns='Variant',values='Feasible')
    common=feasibility.reindex(columns=VARIANTS).eq(True).all(axis=1)
    common_keys=set(common[common].index)
    common_rows=a[[tuple(x) in common_keys for x in a[['Dataset','Node_ID','Seed']].itertuples(index=False,name=None)]]
    common_summary=[]
    for variant,g in common_rows.groupby('Variant'):
        for column in ['Root_Regret','Optimal_Root']:
            scale=100 if column=='Optimal_Root' else 1
            vals=g.groupby('Node_ID')[column].mean()*scale;mean,std,lo,hi=interval(vals)
            common_summary.append(dict(Variant=variant,Metric=column,Mean=mean,Std=std,CI95_Low=lo,CI95_High=hi,
                Common_Feasible_Nodes=len(vals),Common_Feasible_Seed_Units=len(g),
                Scope='sensitivity only; all five variants return a feasible root on exactly these paired units'))
    pd.DataFrame(common_summary).to_csv(out/(prefix+'COMMON_FEASIBLE_SENSITIVITY.csv'),index=False)
    a.groupby(['Dataset','Node_ID','Variant']).agg(Runs=('Seed','size'),Feasible=('Feasible','sum'),
        Mean_Overrun_s=('Deadline_Overrun_s','mean'),Max_Overrun_s=('Deadline_Overrun_s','max')).reset_index().to_csv(
        out/(prefix+'BUDGET_AVAILABILITY.csv'),index=False)
    validation=dict(status='COMPLETE_VALIDATED' if complete else 'PARTIAL',records=len(d),expected=12000,
        nodes=d.Node_ID.nunique(),variants=d.Variant.nunique(),seeds=d.Seed.nunique(),
        unavailable_A=int((~d[d.Protocol.eq('A')].Feasible).sum()),all_full_runs_exact=True,
        mean_deadline_overrun_s=float(d[d.Protocol.eq('A')].Deadline_Overrun_s.mean()),
        max_deadline_overrun_s=float(d[d.Protocol.eq('A')].Deadline_Overrun_s.max()),
        implementation=manifest['code_sha256'],metrics_recomputed_from_raw=True)
    (out/(prefix+'VALIDATION.json')).write_text(json.dumps(validation,indent=2))
    analysis_manifest=dict(bootstrap_seed=20261024,bootstrap_resamples=10000,
        analyze_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        raw_ledger_sha256=hashlib.sha256((out/(prefix+'RAW_SHA256.csv')).read_bytes()).hexdigest(),
        input_run_manifest_sha256=hashlib.sha256((ROOT/'03_runs/formal/manifest.json').read_bytes()).hexdigest())
    (out/(prefix+'ANALYSIS_MANIFEST.json')).write_text(json.dumps(analysis_manifest,indent=2))
    print(summary[['Variant',*METRICS,'Feasible_Runs_A','Regret_Valid_Nodes']].to_string(index=False))
    print(json.dumps(validation))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--partial',action='store_true');a=p.parse_args();main(a.partial)
