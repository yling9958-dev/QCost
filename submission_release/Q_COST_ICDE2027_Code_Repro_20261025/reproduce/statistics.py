#!/usr/bin/env python3
"""Recompute fixed-node results from supplied real measurements; no spatial inputs needed."""
from pathlib import Path
import argparse, importlib.util, json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'code/analysis'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    ab=module('analyze_random');sel=module('analyze_selection')
    raw=pd.read_csv(ROOT/'results/ablation/FIVE_VARIANT_RAW.csv',float_precision='round_trip')
    assert len(raw)==12000 and raw.Node_ID.nunique()==40
    assert set(raw.Seed)==set(range(2026101100,2026101130))
    assert not raw.duplicated(['Node_ID','Seed','Variant','Protocol']).any()
    assert raw.groupby(['Node_ID','Variant','Protocol']).Seed.nunique().eq(30).all()
    assert raw.H.eq(3).all() and raw.K.eq(4).all()
    b=raw[raw.Protocol.eq('A')]
    assert np.allclose(b.Time_Budget_s,.5*b.T_exact_s,rtol=0,atol=1e-12)
    assert b.loc[~b.Feasible,'Optimal_Root'].eq(False).all()
    assert b.loc[~b.Feasible,'Root_Regret'].isna().all()
    refs={}
    for row in raw.itertuples():
        if row.Node_ID not in refs:refs[row.Node_ID]=json.loads((ROOT/'references'/f'{row.Node_ID}.json').read_text())
        ref=refs[row.Node_ID];tol=max(1e-9,abs(ref['optimal_cost'])*1e-12)
        if row.Feasible:
            regret=ref['root_costs'][row.Final_Root]-ref['optimal_cost']
            assert abs(regret-row.Root_Regret)<=tol and bool(row.Optimal_Root)==(abs(regret)<=tol)
    summary,long=ab.summarize(raw);overall=summary[summary.Dataset.eq('Overall')]
    reference=pd.read_csv(ROOT/'results/ablation/REFERENCE_SUMMARY.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(overall.reset_index(drop=True),reference,check_exact=False,rtol=1e-12,atol=1e-12)
    summary.to_csv(a.output/'ABLATION_SUMMARY.csv',index=False);long.to_csv(a.output/'ABLATION_CI.csv',index=False)
    pair,nodes=ab.paired(raw);pair.to_csv(a.output/'ABLATION_PAIRED.csv',index=False)
    nodes.to_csv(a.output/'ABLATION_PAIRED_NODES.csv',index=False)
    table=(ROOT/'tables/ABLATION_TABLE_FIVE_VARIANTS.tex').read_text()
    lines=[]
    for x in overall.itertuples():
        label={'w/o Incumbent Feedback':r'\shortstack[l]{w/o Incumbent\\Feedback}',
               'w/o Recursive Decomposition':r'\shortstack[l]{w/o Recursive\\Decomposition}'}.get(x.Variant,x.Variant)
        lines.append(f'{label} & {x.Optimal_Root_Rate:.2f} & {x.Mean_Root_Regret:.2f} & {x.Mean_Optimization_Time:.4f} & {x.Mean_Exact_States:.1f} '+r'\\')
    generated=table.split('\\midrule\n')[0]+'\\midrule\n'+'\n'.join(lines)+'\n\\bottomrule'+table.split('\\bottomrule',1)[1]
    assert generated==table
    (a.output/'ABLATION_TABLE_FIVE_VARIANTS.tex').write_text(generated)
    print('Table II: 12000 real rows; all five rows and node-level confidence intervals agree.',flush=True)
    # These are event-derived observed snapshots, not spatial point/query inputs.
    d=pd.read_csv(ROOT/'results/selection/QMF_ANYTIME_RAW.csv',float_precision='round_trip')
    assert len(d)==38400 and d.Node_ID.nunique()==80
    assert set(d.Budget_Ratio)=={.25,.5,.75,1.}
    assert not d.duplicated(['Node_ID','Seed','Method','Budget_Ratio']).any()
    assert d.groupby(['Node_ID','Method','Budget_Ratio']).Seed.nunique().eq(30).all()
    stored=pd.read_csv(ROOT/'results/selection/QMF_SELECTION_METRICS.csv',float_precision='round_trip')
    means={}
    for cohort,co in d.groupby('Cohort'):
        for ds,dd in [('Overall',co),*list(co.groupby('Dataset'))]:
            for (method,budget),g in dd.groupby(['Method','Budget_Ratio']):
                m=g.groupby('Node_ID')[sel.METRICS].mean().mean()
                for metric,value in m.items():means[(cohort,ds,method,budget,metric)]=value
    for x in stored.itertuples():
        assert np.isclose(means[(x.Cohort,x.Dataset,x.Method,x.Budget_Ratio,x.Metric)],x.Mean,rtol=1e-12,atol=1e-12,equal_nan=True)
    recorded_pairs=pd.read_csv(ROOT/'results/selection/QMF_PAIRED_STATISTICS.csv',float_precision='round_trip')
    table_metrics=[('Optimal root (\\%)','Optimal_Root',.5,100,1),('Near-opt. 5\\% (\\%)','Near_5pct',.5,100,1),
       ('Norm. regret','Normalized_Regret',.5,1,3),('Anytime AUC','Anytime_AUC',1.,1,3),
       ('Optimal wait / $T_e$','Time_Optimal_Restricted_T',1.,1,3),('Useful eval. (\\%)','Useful_Evaluation_Ratio',1.,100,1)]
    pairs=[]
    for cohort,co in d.groupby('Cohort'):
        for label,metric,budget,scale,dec in table_metrics:
            g=co[co.Budget_Ratio.eq(budget)]
            wide=g.pivot(index=['Dataset','Node_ID','Seed'],columns='Method',values=metric).astype(float)
            for contrast,coeff in sel.CONTRASTS.items():
                valid=wide[list(coeff)].dropna();delta=sum(valid[k]*v for k,v in coeff.items())
                vals=delta.groupby(level=['Dataset','Node_ID']).mean()
                mean,median,std,lo,hi,ml,mh=sel.interval(vals)
                primary=contrast=='QMF_with_Feedback' and metric in ['Optimal_Root','Anytime_AUC']
                row=dict(Cohort=cohort,Budget_Ratio=budget,Contrast=contrast,Metric=metric,Mean_Difference=mean,
                         Median_Difference=median,CI95_Low=lo,CI95_High=hi,Nodes=len(vals),Paired_Runs=len(valid),
                         Primary=primary,P=sel.pvalue(vals,primary))
                match=recorded_pairs[(recorded_pairs.Cohort==cohort)&(recorded_pairs.Budget_Ratio==budget)&
                                    (recorded_pairs.Contrast==contrast)&(recorded_pairs.Metric==metric)].iloc[0]
                for col in ['Mean_Difference','Median_Difference','CI95_Low','CI95_High','P']:
                    assert np.isclose(row[col],match[col],rtol=1e-10,atol=1e-12,equal_nan=True),(cohort,metric,col)
                pairs.append(row)
    pdp=pd.DataFrame(pairs);pdp['Primary_Holm_P']=np.nan
    for _,g in pdp.groupby('Cohort'):
        ix=g[g.Primary].index;pdp.loc[ix,'Primary_Holm_P']=sel.adjust(pdp.loc[ix,'P'],holm=True)
    for row in pdp[pdp.Primary].itertuples():
        original=recorded_pairs[(recorded_pairs.Cohort==row.Cohort)&(recorded_pairs.Metric==row.Metric)&
                                 (recorded_pairs.Budget_Ratio==row.Budget_Ratio)&recorded_pairs.Primary].iloc[0]
        assert np.isclose(row.Primary_Holm_P,original.Adjusted_P,rtol=1e-10,atol=1e-12)
    pdp.to_csv(a.output/'SELECTION_TABLE_AND_INTERACTION_RECOMPUTED.csv',index=False)
    # Retain the published note and regenerate every numerical table body from checked data.
    tab=(ROOT/'tables/QMF_SELECTION_TABLE.tex').read_text();body=[]
    # Use the original table generator's CSV reader for decimal tie formatting.
    # All numerical means and paired CIs have already been independently checked above.
    display_summary=pd.read_csv(ROOT/'results/selection/QMF_SELECTION_METRICS.csv')
    display_pairs=pd.read_csv(ROOT/'results/selection/QMF_PAIRED_STATISTICS.csv')
    for cohort,label in [('Original','Original 40 nodes'),('Validation','Held-out 40 nodes')]:
        body.append(r'\multicolumn{4}{l}{\textit{'+label+r'}} \\')
        for label,metric,budget,scale,dec in table_metrics:
            rows=display_summary[(display_summary.Cohort==cohort)&(display_summary.Dataset=='Overall')&
                                 (display_summary.Budget_Ratio==budget)&(display_summary.Metric==metric)]
            q=rows[rows.Method=='QF'].iloc[0].Mean;r=rows[rows.Method=='RF'].iloc[0].Mean
            eff=display_pairs[(display_pairs.Cohort==cohort)&(display_pairs.Budget_Ratio==budget)&
                              (display_pairs.Metric==metric)&(display_pairs.Contrast=='QMF_with_Feedback')].iloc[0]
            fmt=lambda value:f'{value*scale:.{dec}f}'
            body.append(f'{label} & {fmt(q)} & {fmt(r)} & {fmt(eff.Mean_Difference)} [{fmt(eff.CI95_Low)}, {fmt(eff.CI95_High)}] '+r'\\')
        if cohort=='Original':body.append(r'\midrule')
    generated=tab.split('\\midrule\n',1)[0]+'\\midrule\n'+'\n'.join(body)+'\n\\bottomrule'+tab.split('\\bottomrule',1)[1]
    assert generated==tab
    (a.output/'QMF_SELECTION_TABLE.tex').write_text(generated)
    receipt=dict(status='PASS',ablation_runs=len(raw),selection_snapshots=len(d),selection_trajectories=9600,
                 selection_nodes=80,table_II_exact_match=True,table_III_exact_match=True,
                 reference_answer_checks=True,all_selection_point_estimates_verified=len(stored),
                 paired_table_and_interaction_CI_verified=len(pdp),primary_pvalues_recomputed=True,
                 input_kind='measured scalar results; no spatial inputs; no new timing experiments')
    (a.output/'VALIDATION.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
