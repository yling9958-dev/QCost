"""Four-row paper table independently recomputed from the unchanged raw CSV."""
from pathlib import Path
import pandas as pd,numpy as np,json
R=Path(__file__).resolve().parents[1];A=R.parent/'hybrid_qmf_ablation'
NAMES=['Full Hybrid-QMF','w/o Shared Cache','w/o Incumbent Feedback','w/o Recursive Decomposition']
def main():
    d=pd.read_csv(A/'04_metrics/ABLATION_RAW_RESULTS.csv',float_precision='round_trip')
    old=pd.read_csv(A/'04_metrics/ABLATION_SUMMARY.csv',float_precision='round_trip').set_index('Variant')
    assert len(d)==12000 and set(d.Seed)==set(range(2026101100,2026101130))
    assert d.H.eq(3).all() and d.K.eq(4).all()
    all_nodes=set(d.Node_ID);assert len(all_nodes)==40
    budgeted=d[d.Protocol.eq('A')]
    assert np.allclose(budgeted.Time_Budget_s,0.5*budgeted.T_exact_s,rtol=0,atol=1e-12)
    assert budgeted.groupby('Node_ID').Time_Budget_s.nunique().eq(1).all()
    assert budgeted.Root_Regret.dropna().ge(0).all()
    rows=[];node_sets={};nodes=[]
    for name in NAMES:
        g=d[d.Variant.eq(name)];a=g[g.Protocol.eq('A')];b=g[g.Protocol.eq('B')]
        assert len(a)==len(b)==1200 and a.Node_ID.nunique()==40
        assert set(a.Node_ID)==set(b.Node_ID)==all_nodes
        assert g.groupby(['Node_ID','Protocol']).Seed.nunique().eq(30).all()
        assert a[a.Feasible.eq(False)].Optimal_Root.eq(False).all() and a[a.Feasible.eq(False)].Root_Regret.isna().all()
        assert b.Status.eq('EXACT').all() and b.Optimal_Root.all()
        am=a.groupby('Node_ID')[['Optimal_Root','Root_Regret']].mean();bm=b.groupby('Node_ID')[['Optimization_Time_s','Exact_State_Evaluations']].mean()
        row=dict(Variant=name,Optimal_Root_Rate=100*am.Optimal_Root.mean(),Mean_Root_Regret=am.Root_Regret.mean(),
                 Mean_Optimization_Time=bm.Optimization_Time_s.mean(),Mean_Exact_States=bm.Exact_State_Evaluations.mean(),
                 Nodes=40,Seeds_Per_Node=30,Valid_Runs_A=1200,Valid_Runs_B=1200,
                 Feasible_Runs_A=int(a.Feasible.sum()),Regret_Nodes=int(am.Root_Regret.notna().sum()),
                 Raw_Source=str(A/'04_metrics/ABLATION_RAW_RESULTS.csv'))
        node_sets[name]=sorted(am.Root_Regret.dropna().index)
        for metric in ['Optimal_Root_Rate','Mean_Root_Regret','Mean_Optimization_Time','Mean_Exact_States']:
            assert np.isclose(row[metric],old.loc[name,metric],rtol=1e-13,atol=1e-12),(name,metric)
        assert row['Regret_Nodes']==38
        rows.append(row)
        for node,x in am.iterrows():nodes.append(dict(Variant=name,Node_ID=node,Optimal_Root_Rate=100*x.Optimal_Root,
            Root_Regret=x.Root_Regret,Feasible_Runs=int(a[a.Node_ID.eq(node)].Feasible.sum()),Runs=30))
    assert all(v==node_sets[NAMES[0]] for v in node_sets.values())
    out=R/'02_plot_data/ABLATION_REVISED_DATA.csv';pd.DataFrame(rows).to_csv(out,index=False)
    pd.DataFrame(nodes).to_csv(R/'02_plot_data/ABLATION_NODE_COVERAGE.csv',index=False)
    pd.DataFrame(d[d.Variant.isin(NAMES)]).to_csv(R/'02_plot_data/ABLATION_REVISED_RAW_EXPORT.csv',index=False)
    verified=pd.read_csv(out);table=[r'\begin{table}[t]',r'\centering',
        r'\caption{Ablation Study of Hybrid Optimization Components}',r'\label{tab:qcost_hybrid_ablation}',
        r'\footnotesize',r'\setlength{\tabcolsep}{2.3pt}',r'\begin{tabular}{@{}lrrrr@{}}',r'\toprule',
        r'Variant & Root (\%)$\uparrow$ & Regret$\downarrow$ & Time (s)$\downarrow$ & States$\downarrow$ \\',r'\midrule']
    for x in verified.itertuples():
        label={'w/o Incumbent Feedback':r'\shortstack[l]{w/o Incumbent\\Feedback}',
               'w/o Recursive Decomposition':r'\shortstack[l]{w/o Recursive\\Decomposition}'}.get(x.Variant,x.Variant)
        table.append(f'{label} & {x.Optimal_Root_Rate:.2f} & {x.Mean_Root_Regret:.2f} & {x.Mean_Optimization_Time:.4f} & {x.Mean_Exact_States:.1f} '+r'\\')
    counts=', '.join(map(str,verified.Feasible_Runs_A))
    table += [r'\bottomrule',r'\end{tabular}',r'\par\vspace{2pt}',r'\parbox{\columnwidth}{\scriptsize',
        r'Root and regret: $0.5T_{\mathrm{exact}}$; time and exact states: complete optimization. '
        r'Four datasets, 40 fixed nodes, 30 paired seeds per node. Means average seeds within nodes. '
        r'Unavailable roots count as failures; regret uses feasible returns on the same 38 nodes. '
        f'Feasible budgeted returns, in row order: {counts}, each out of 1,200.'+r'}',r'\end{table}']
    (R/'04_tables/ABLATION_TABLE_REVISED.tex').write_text('\n'.join(table)+'\n')
    (R/'07_reports/ABLATION_CHECK.json').write_text(json.dumps(dict(status='PASS',raw_rows=12000,paper_rows=9600,
        regret_nodes_identical=True,missing_nodes=sorted(set(d.Node_ID)-set(node_sets[NAMES[0]])),results=rows),indent=2))
    print(verified.to_string(index=False))
if __name__=='__main__':main()
