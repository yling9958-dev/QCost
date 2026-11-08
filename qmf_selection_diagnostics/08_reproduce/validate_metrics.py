"""Independent timestamp/quadrature and denominator checks, without optimizer calls."""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1]
KEY=['Cohort','Node_ID','Seed','Method']
def main(cohort=None):
    folder=R/'03_metrics'
    if cohort:folder=folder/('checkpoint_'+cohort.lower())
    raw=pd.read_csv(folder/'QMF_ANYTIME_RAW.csv')
    history=pd.read_csv(folder/'INCUMBENT_TRAJECTORIES.csv')
    trajectories={k:g.sort_values('elapsed') for k,g in history.groupby(KEY)}
    nodes=json.loads((R/'01_code_audit/NODE_MANIFEST.json').read_text())
    refs={n['Node_ID']:json.loads(Path(n['Reference_File']).read_text()) for n in nodes}
    checked=0
    for row in raw.itertuples(index=False):
        key=tuple(getattr(row,k) for k in KEY);events=trajectories.get(key)
        events=events[events.elapsed<=row.Budget_s] if events is not None else pd.DataFrame()
        reference=refs[row.Node_ID];scale=max(abs(reference['optimal_cost']),1e-9)
        tolerance=max(1e-9,abs(reference['optimal_cost'])*1e-12)
        if len(events):
            current=events.iloc[-1];value=reference['root_costs'][current.root]
            regrets=np.maximum(0,events.offline_root_regret.to_numpy())/scale
            assert row.Valid_Return and row.Returned_Root==current.root
            assert np.isclose(row.Normalized_Regret,regrets[-1],rtol=1e-12,atol=1e-12)
            assert row.Optimal_Root==(abs(value-reference['optimal_cost'])<=tolerance)
            assert row.Root_Rank==1+sum(c<value-tolerance for c in reference['root_costs'].values())
            assert row.Near_1pct==(regrets[-1]<=.01+tolerance/scale)
            assert row.Near_5pct==(regrets[-1]<=.05+tolerance/scale)
            knots=np.r_[0.,events.elapsed.to_numpy(),row.Budget_s]
            losses=np.r_[1.,np.minimum.accumulate(np.minimum(1.,regrets))]
            auc=np.diff(knots)@losses/row.Budget_s
            first_opt=events[events.offline_optimal]
            assert row.Time_Optimal_Event==bool(len(first_opt))
            if len(first_opt):
                first=first_opt.iloc[0]
                assert np.isclose(row.Time_Optimal_s,first.elapsed)
                assert row.Evaluations_Optimal==first.candidate_completed
            else:
                assert np.isnan(row.Time_Optimal_s) and np.isnan(row.Evaluations_Optimal)
                assert row.Evaluations_Optimal_Restricted==row.Candidate_Completions
            assert np.isclose(row.Time_Feasible_s,events.iloc[0].elapsed)
        else:
            auc=1.
            assert not row.Valid_Return and not row.Optimal_Root and not row.Near_1pct and not row.Near_5pct
            assert np.isnan(row.Normalized_Regret) and np.isnan(row.Root_Rank)
            assert not row.Time_Optimal_Event and not row.Time_Feasible_Event
        assert np.isclose(row.Anytime_AUC,auc,rtol=1e-12,atol=1e-12)
        assert np.isclose(row.Time_Optimal_Restricted_s,row.Time_Optimal_s if row.Time_Optimal_Event else row.Budget_s)
        if row.Candidate_Completions:
            assert np.isclose(row.Useful_Evaluation_Ratio,row.Useful_Evaluations/row.Candidate_Completions)
        else:assert np.isnan(row.Useful_Evaluation_Ratio)
        if row.Selector=='Random':
            assert np.isnan(row.Threshold_Updates) and np.isnan(row.Threshold_Acceptance)
        checked+=1
    # Recompute conditional pairing with an independent explicit join.
    effects=pd.read_csv(folder/'QMF_PAIRED_STATISTICS.csv');summary=pd.read_csv(folder/'QMF_SELECTION_METRICS.csv')
    pairs=[]
    for (co,b),g in raw.groupby(['Cohort','Budget_Ratio']):
        q=g[g.Method.eq('QF')];r=g[g.Method.eq('RF')]
        merged=q.merge(r,on=['Node_ID','Seed'],suffixes=('_QMF','_Random'),validate='one_to_one')
        assert len(merged)==1200
        for metric in ['Optimal_Root','Normalized_Regret','Anytime_AUC','Useful_Evaluation_Ratio','Root_Rank']:
            a=metric+'_QMF';c=metric+'_Random';valid=merged.dropna(subset=[a,c]).copy()
            valid['delta']=valid[a].astype(float)-valid[c].astype(float)
            node=valid.groupby('Node_ID');mean=node.delta.mean().mean()
            recorded=effects[effects.Cohort.eq(co)&effects.Budget_Ratio.eq(b)&effects.Contrast.eq('QMF_with_Feedback')&effects.Metric.eq(metric)].iloc[0]
            assert np.isclose(recorded.Mean_Difference,mean,atol=1e-12)
            assert recorded.Nodes==valid.Node_ID.nunique() and recorded.Paired_Runs==len(valid)
            pairs.append(dict(Cohort=co,Budget_Ratio=b,Metric=metric,Common_Nodes=valid.Node_ID.nunique(),Common_Runs=len(valid),
                QMF_Common_Mean=node[a].mean().mean(),Random_Common_Mean=node[c].mean().mean(),Paired_Difference=mean))
        for method,mg in g.groupby('Method'):
            counts=summary[summary.Cohort.eq(co)&summary.Dataset.eq('Overall')&summary.Method.eq(method)&summary.Budget_Ratio.eq(b)]
            assert counts.Total_Runs.eq(1200).all() and counts.Feasible_Runs.eq(mg.Valid_Return.sum()).all()
            assert counts.Failed_Returns.eq((~mg.Valid_Return).sum()).all()
    pd.DataFrame(pairs).to_csv(folder/'COMMON_VALID_COMPARISON.csv',index=False)
    receipt=dict(Status='PASS',Snapshots=checked,Independent_AUC_Quadrature=True,Root_Ties_And_Regret=True,
        Failures_In_Denominator=True,Censoring_Retained=True,Common_Valid_Pairing=True,Random_Threshold_NA=True,
        Source='Actual incumbent timestamps and independent root-cost reference maps; no optimizer reruns')
    (folder/'INDEPENDENT_METRIC_CHECK.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',choices=['Original','Validation']);main(parser.parse_args().cohort)
