"""Presentation-only filtering, with independent checks against measured records."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];Q=R.parent
P=Q/'figures_sec4_3_4_4/data';S=Q/'figures_sec4_5_4_6/data'
CHECKS=[];SOURCES={}
def read(p):
    p=Path(p);SOURCES[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return pd.read_csv(p,float_precision='round_trip')
def js(p):
    p=Path(p);SOURCES[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();return json.loads(p.read_text())
def check(name,ok):
    CHECKS.append(dict(Check=name,Pass=bool(ok)))
    assert ok,name
def same(a,b):return np.allclose(a,b,rtol=1e-12,atol=1e-14,equal_nan=True)
def select(d,panel,source,methods=None):
    g=d[~d.method.eq('Hybrid-BestFirst')].copy()
    if methods is not None:g=g[g.method.isin(methods)].copy()
    g.insert(0,'Panel',panel);g['Source_File']=str(source);g['Source_Row']=g.index+2
    # Exact preservation of every retained source cell before CSV round trip.
    pd.testing.assert_frame_equal(g[d.columns],d.loc[g.index],check_exact=True)
    return g
def main():
    wall=read(P/'current_wallclock_summary.csv');hist=read(P/'historical_phase_summary.csv')
    budget=read(P/'fig13_budget_summary.csv');work=read(P/'fig13_work_summary.csv');scale=read(S/'scalability_summary.csv')
    m12=['Original Recursive Exact','Original Analytic QMF','Cached Anytime Recursive','Hybrid-QMF']
    m13=['Original Recursive Exact','Cached Anytime Recursive','Hybrid-QMF-NoFeedback','Hybrid-QMF']
    m16=['Recursive Exact','Cached Anytime Recursive','Hybrid-QMF']
    a=select(wall[wall.metric.eq('total_optimizer_time')],'a',P/'current_wallclock_summary.csv',m12)
    b=select(hist,'b',P/'historical_phase_summary.csv')
    pd.concat([a,b],ignore_index=True).to_csv(R/'02_plot_data/FIG12_REVISED_DATA.csv',index=False)
    parts=[select(budget[budget.metric.eq('root_optimal')],'a',P/'fig13_budget_summary.csv',m13),
           select(wall[wall.metric.eq('total_optimizer_time')],'b',P/'current_wallclock_summary.csv',m13),
           select(work[work.panel.eq('cache')],'c',P/'fig13_work_summary.csv',['Anytime Recursive (cache off)','Cached Anytime Recursive']),
           select(work[work.panel.eq('feedback')],'d',P/'fig13_work_summary.csv',['Hybrid-QMF-NoFeedback','Hybrid-QMF'])]
    pd.concat(parts,ignore_index=True).to_csv(R/'02_plot_data/FIG13_REVISED_DATA.csv',index=False)
    parts=[]
    for panel,n,metric in [('a',20000,'build_seconds'),('b',50000,'build_seconds'),('c',20000,'mean_ms'),('d',50000,'mean_ms')]:
        parts.append(select(scale[(scale.points==n)&(scale.metric==metric)],panel,S/'scalability_summary.csv',m16))
    pd.concat(parts,ignore_index=True).to_csv(R/'02_plot_data/FIG16_REVISED_DATA.csv',index=False)
    # Preserve original axis bounds, including where the removed method determined a maximum.
    axes={'fig12a':[0,float(wall[wall.metric.eq('total_optimizer_time')&wall.method.isin(m12+['Hybrid-BestFirst'])].ci_high.max()*1.08)],
          'fig12b':[0,float(hist[hist.metric.eq('total')].ci_high.max()*1.08)],
          'fig13a':[-3,105],
          'fig13b':[0,float(wall[wall.metric.eq('total_optimizer_time')&wall.method.isin(m13+['Hybrid-BestFirst'])].ci_high.max()*1.08)]}
    for panel,methods in [('cache',['Anytime Recursive (cache off)','Cached Anytime Recursive']),('feedback',['Hybrid-QMF-NoFeedback','Hybrid-QMF'])]:
        axes['fig13'+('c' if panel=='cache' else 'd')]=[0,float(work[work.panel.eq(panel)&work.method.isin(methods)].ci_high.max()*1.07)]
    for panel,n,metric in [('a',20000,'build_seconds'),('b',50000,'build_seconds'),('c',20000,'mean_ms'),('d',50000,'mean_ms')]:
        axes['fig16'+panel]=[0,float(scale[(scale.points==n)&(scale.metric==metric)]['mean'].max()*1.13)]
    (R/'02_plot_data/ORIGINAL_AXIS_LIMITS.json').write_text(json.dumps(axes,indent=2))
    # Verify historical full-time means and the EXACT same bootstrap recipe.
    raw=read(P/'main40_trajectories_records.csv')
    for method in m12+['Hybrid-QMF-NoFeedback']:
        g=raw[raw.method.eq(method)];check(method+' 40 nodes x 3 seeds',len(g)==120 and g.node.nunique()==40)
        for x in g.itertuples():
            original=js(x.source_file);check(x.run_id+' raw time',same(original['stats']['total_optimizer_time'],x.total_optimizer_time))
        vals=g.groupby('node').total_optimizer_time.mean().to_numpy();rng=np.random.default_rng(20261020)
        ci=np.quantile(vals[rng.integers(0,len(vals),(2000,len(vals)))].mean(1),[.025,.975])
        old=wall[wall.method.eq(method)&wall.metric.eq('total_optimizer_time')].iloc[0]
        check(method+' preserved historical mean/CI',same([vals.mean(),*ci],[old['mean'],old.ci_low,old.ci_high]))
    br=read(P/'fig13_budget_records.csv')
    for method in m13:
        for ratio in [.25,.5,.75,1,1.5]:
            g=br[br.method.eq(method)&br.budget_ratio.eq(ratio)];check(method+str(ratio)+' 24 observations',len(g)==24)
            vals=g.groupby('node').root_optimal.mean().to_numpy();rng=np.random.default_rng(20261020)
            ci=np.quantile(vals[rng.integers(0,8,(2000,8))].mean(1),[.025,.975])
            old=budget[budget.method.eq(method)&budget.budget_ratio.eq(ratio)&budget.metric.eq('root_optimal')].iloc[0]
            check(method+str(ratio)+' preserved root rate/CI',same([vals.mean(),*ci],[old['mean'],old.ci_low,old.ci_high]))
    sr=read(S/'scalability_results.csv');sr=sr[sr.method.isin(m16)]
    for row in sr.itertuples():
        build=js(row.build_log);lat=read(row.latency_file);correct=read(row.latency_file+'.correctness.csv')
        check(row.dataset+str(row.points)+row.method+' time/latency original',same([build['build_seconds'],lat.latency_ns.mean()/1e6],[row.build_seconds,row.mean_ms]))
        check(row.dataset+str(row.points)+row.method+' 1000 correctness queries',len(correct)==1000 and correct.expected.eq(correct['count']).all())
        check(row.dataset+str(row.points)+row.method+' 5 query repeats',len(lat)==15000 and lat.repetition.nunique()==5)
        for metric in ['build_seconds','mean_ms']:
            old=scale[scale.dataset.eq(row.dataset)&scale.points.eq(row.points)&scale.method.eq(row.method)&scale.metric.eq(metric)].iloc[0]
            check(row.dataset+str(row.points)+row.method+metric+' unchanged mean',same(old['mean'],getattr(row,metric)))
    check('Figure16 single build, no invented CI',scale.independent_builds.eq(1).all() and scale.ci_low.isna().all() and scale.ci_high.isna().all())
    pd.DataFrame(CHECKS).to_csv(R/'07_reports/DATA_VALIDATION.csv',index=False)
    (R/'01_audit/DATA_SOURCE_SHA256.json').write_text(json.dumps(SOURCES,indent=2))
    print(f'PASS: {len(CHECKS)} raw-record checks; export-only exclusion; original means, CIs and axes retained.')
if __name__=='__main__':main()
