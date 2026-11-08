"""Extract available timestamp-based legacy metrics for audit, never pool batches."""
from pathlib import Path
import sys,json,csv
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1];Q=R.parent
def main():
    nodes={n['Node_ID']:n for n in json.loads((R/'01_code_audit/NODE_MANIFEST.json').read_text())}
    rows=[];sources=[]
    paths=[*sorted((Q/'qmf_random_ablation_revision/03_runs/formal').glob('*__RANDOM__A.json'))]
    for key in ['V1','V4']:paths+=sorted((Q/'hybrid_qmf_ablation/03_runs/formal').glob('*__'+key+'__A.json'))
    for p in paths:
        x=json.loads(p.read_text());T=x['T_exact_s'];B=.5*T;ref=json.loads(Path(x['Reference_File']).read_text());scale=max(abs(ref['optimal_cost']),1e-9);tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
        history=[e for e in x['stats']['incumbent_trace'] if e['elapsed']<=B];last=0.;best=1.;auc=0.
        for e in history:
            auc+=best*(e['elapsed']-last);best=min(best,max(0,ref['root_costs'][e['root']]-ref['optimal_cost'])/scale,1.);last=e['elapsed']
        auc+=best*(B-last);hit=next((e for e in history if abs(ref['root_costs'][e['root']]-ref['optimal_cost'])<=tol),None)
        rows.append(dict(Cohort='Historical audit only',Node_ID=x['Node_ID'],Dataset=x['Dataset'],Seed=x['Seed'],
            Method='RF' if x.get('Variant_ID')=='RANDOM' else 'QF' if x['Variant_ID']=='V1' else 'QN',Budget_Ratio=.5,
            Valid_Return=bool(history),Optimal_Root=x['Optimal_Root'],Normalized_Regret=x['Root_Regret']/scale if history else np.nan,
            AUC_Half_Budget=auc/B,Time_Optimal_Event=bool(hit),Time_Optimal_Restricted_T=hit['elapsed']/T if hit else .5,
            Missing_Candidate_Event_Timestamps=True,Source_File=str(p.resolve()),Reuse='secondary historical audit; excluded from fresh matched campaign'))
    d=pd.DataFrame(rows);assert len(d)==3600;d.to_csv(R/'03_metrics/HISTORICAL_AVAILABLE_METRICS.csv',index=False)
    report=dict(Records=len(d),Supported=['incumbent prefix at original half-budget','returned-root metrics','half-budget AUC','censored first-root discovery'],
                Unsupported=['candidate start/end and counts-to-optimal','useful evaluation attribution','selection-only timing','other budgets beyond recorded cutoff'],
                Reuse='Extracted truthfully; not pooled with new matched environment/observer timing',
                Old_BestFirst_Records_Read=0,New_Full_Campaign_Reason='missing required event fields, missing RN, incompatible batches and observer protocol')
    (R/'01_code_audit/HISTORICAL_TRAJECTORY_AUDIT.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
