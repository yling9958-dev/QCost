"""Read-only reanalysis of existing experiments; never imports an optimizer.

Adapted from paper_icde_qcost_results/02_plot_scripts/prepare_data.py and
Phase 4 analyze_phase4.py. Original files are archived and never written.
"""
from pathlib import Path
import io, json, hashlib
import numpy as np
import pandas as pd
from scipy.stats import t

OUT=Path(__file__).resolve().parents[1]
BASE=OUT.parent.parent
CORE=BASE/'QMF-Core-Ablation'
MOT=BASE/'QMF-Motivation-Study'
STUDY=BASE/'Q-COST-QMF-Necessity-Study'
P2=STUDY/'phase2_hybrid_optimizer'
P3=STUDY/'phase3_hybrid_comparison'
P4=STUDY/'phase4_complementarity_analysis'
DS={'geolife':'GeoLife','gowalla':'Gowalla','nyc_taxi':'NYC Taxi','skewed_2d':'Skewed 2D'}
METHOD={'r4_greedy':'R4 Greedy','cost_h1':'Cost-H1','recursive_exact_h3':'Original Recursive Exact',
 'cpu_qmf_h3':'Original Analytic QMF','CPU Analytic QMF':'Original Analytic QMF',
 'Recursive Exact':'Original Recursive Exact','Recursive Exact H3':'Original Recursive Exact',
 'EXACT':'Original Recursive Exact','M1':'Original Recursive Exact','QMF':'Original Analytic QMF',
 'M2':'Anytime Recursive (cache off)','M3':'Cached Anytime Recursive','M4':'Hybrid-Random',
 'M5':'Hybrid-Threshold','M6':'Hybrid-BestFirst','M7':'Hybrid-QMF-NoFeedback','M8':'Hybrid-QMF'}
SOURCES={}; CHECKS=[]

def raw(p):
    p=Path(p);b=p.read_bytes();st=p.stat()
    h=hashlib.sha256(b).hexdigest()
    if str(p) in SOURCES:assert SOURCES[str(p)]['sha256']==h
    SOURCES[str(p)]={'source_file':str(p),'sha256':h,'bytes':len(b),'mtime_ns':st.st_mtime_ns}
    return b
def read(p):
    d=pd.read_csv(io.BytesIO(raw(p)));d['source_file']=str(p);d['source_row']=np.arange(len(d))+2
    return d
def js(p):return json.loads(raw(p))
def save(d,name):d.to_csv(OUT/'data'/name,index=False)
def check(label,ok,detail=''):
    CHECKS.append({'check':label,'passed':bool(ok),'detail':str(detail)})
    if not ok:raise AssertionError((label,detail))
def ci(v,legacy=False):
    v=np.asarray(v,float);assert len(v) and np.isfinite(v).all()
    rng=np.random.default_rng(20261015 if legacy else 20261020)
    n=4000 if legacy else 2000
    means=v[rng.integers(0,len(v),(n,len(v)))].mean(1)
    return v.mean(),*np.quantile(means,[.025,.975])
def summarize(d,keys,metrics,legacy=False,node='node'):
    rows=[]
    for key,g in d.groupby(keys,dropna=False,sort=False):
        if not isinstance(key,tuple):key=(key,)
        for metric in metrics:
            values=g.groupby(node)[metric].mean().dropna()
            if not len(values):continue
            m,l,h=ci(values,legacy)
            rows.append(dict(zip(keys,key),metric=metric,mean=m,ci_low=l,ci_high=h,
                nodes=len(values),runs=len(g),seeds=g['seed'].nunique() if 'seed' in g else g['Seed'].nunique(),
                ci_method='seeds averaged within node; percentile node bootstrap',
                bootstrap_draws=4000 if legacy else 2000,bootstrap_seed=20261015 if legacy else 20261020))
    return pd.DataFrame(rows)

def controlled():
    protocol=js(CORE/'configs/protocol.json')
    d=read(CORE/'results/tables/BUILD_LEVEL_METRICS.csv')
    check('historical 160 independent builds',len(d)==160)
    check('build keys unique',not d.duplicated(['Dataset','Points','Method','Seed']).any())
    check('historical correctness',d.Correctness.eq('COUNT_AND_ID_SET_PASS').all())
    d['original_method_name']=d.Method;d['method']=d.Method.map(METHOD);d['dataset']=d.Dataset.map(DS)
    d['algorithm_version']=np.where(d.Method.eq('cpu_qmf_h3'),'original full-table analytic QMF','historical controlled builder')
    d['campaign']='Core-Ablation original';d['preferred_for_later']=False
    # Recheck all 80 plotted build means directly against 15,000 clocks per build.
    evidence=[]
    for i,r in d[d.Points.eq(20000)].iterrows():
        lp=CORE/r.Folder/'queries/query_latency.csv';x=read(lp)
        check(str(lp)+':timed rows',len(x)==15000)
        check(str(lp)+':mean',np.isclose(x.latency_ns.mean()/1e6,r['Mean (ms)'],rtol=1e-10,atol=1e-12))
        d.loc[i,'latency_source_file']=str(lp)
        evidence.append({'dataset':r.dataset,'method':r.method,'seed':r.Seed,'observations':len(x),
                         'mean_ms_recomputed':x.latency_ns.mean()/1e6,'source_file':str(lp)})
    save(pd.DataFrame(evidence),'ablation_latency_validation.csv')
    save(d,'ablation_results.csv')
    groups=[]
    for (ds,m),g in d[d.Points.eq(20000)].groupby(['dataset','method'],sort=False):
        check(ds+m+':five builds',g.Seed.nunique()==5 and len(g)==5)
        v=g['Mean (ms)'];half=t.ppf(.975,4)*v.std(ddof=1)/np.sqrt(5)
        groups.append(dict(dataset=ds,method=m,mean=v.mean(),ci_low=v.mean()-half,ci_high=v.mean()+half,builds=5,
                           implementation='original analytic QMF' if m=='Original Analytic QMF' else m))
    save(pd.DataFrame(groups),'fig10_latency_summary.csv')
    r=read(CORE/'results/tables/root_decisions_formal_20000.csv')
    check('diagnostic unique',not r.duplicated(['dataset','size','method','seed','node_id']).any())
    check('diagnostic 20K',r['size'].eq(20000).all())
    r['original_method_name']=r.method;r['method']=r.method.map(METHOD);r['dataset']=r.dataset.map(DS)
    check('root optimal matches finite regret',np.array_equal(r.optimal_root_hit.astype(bool),np.isclose(r.root_regret,0,atol=1e-8)))
    root=r.groupby('method',sort=False).agg(records=('node_id','size'),hits=('optimal_root_hit','sum'),
        finite_regret=('root_regret','count')).reset_index();root['rate']=100*root.hits/root.records
    save(r,'root_diagnostic_records.csv');save(root,'fig10_root_summary.csv')
    check('old analytic diagnostics retained',int(root[root.method.eq('Original Analytic QMF')].hits.iloc[0])==138)
    # Table III is retained, with separate query pipelines/campaigns and no pooling.
    scale=d.rename(columns={'Points':'points','Seed':'seed','Build Time (s)':'build_seconds',
        'Mean (ms)':'mean_ms','P95 (ms)':'p95_ms','P99 (ms)':'p99_ms','Index Size (MiB)':'index_mib',
        'Correctness':'correctness_status'}).copy()
    scale['timing_scope']='historical controlled query campaign; not interchangeable with native Phase 3 clocks'
    frames=[scale]
    candidates=sorted((P3/'results/index20k').glob('summary_resume_*.csv'))
    p3source=candidates[-1] if candidates else P3/'results/index20k/summary.csv'
    new=read(p3source)
    check('Phase3 newest complete summary',len(new)==100 and new.status.eq('PASS').all())
    check('Phase3 five builds/cell',new.groupby(['dataset','method']).seed.nunique().eq(5).all())
    for _,row in new.iterrows():
        folder=P3/'results/index20k'/row.run_id
        build=js(folder/'build.json')
        check(row.run_id+':real root commitments',all(a['selected_root']==a['committed_root'] for a in build['decisions']))
        check(row.run_id+':build receipt',np.isclose(row.build_seconds,build['build_seconds']))
        latency=read(folder/'latency.csv')
        value=latency.latency_ns.mean()/1e6
        check(row.run_id+':new latency clocks',len(latency)==15000 and np.isclose(value,row.mean_ms,rtol=1e-10))
    new['original_method_name']=new.method;new['method']=new.method.map(METHOD);new['dataset']=new.dataset.map(DS)
    new['campaign']='Phase3 native C++';new['algorithm_version']='Phase3 comparison adapter; Hybrid=M8'
    new['preferred_for_later']=True;new['correctness_status']=new.status
    save(new,'hybrid_index_builds_phase3.csv');frames.append(new)
    pilot=read(P2/'results/indexing/pilot_four_datasets/summary.csv')
    check('Phase2 four datasets two sizes',len(pilot)==32 and pilot.status.eq('PASS').all())
    pilot['original_method_name']=pilot.method;pilot['method']=pilot.method.map(METHOD);pilot['dataset']=pilot.dataset.map(DS)
    pilot['campaign']='Phase2 native C++ pilot';pilot['algorithm_version']='Phase2 hybrid; one independent seed'
    pilot['preferred_for_later']=pilot.points.eq(50000);pilot['correctness_status']=pilot.status
    pilot['timing_scope']=pilot.scope
    save(pilot,'hybrid_index_builds_phase2.csv');frames.append(pilot)
    sc=pd.concat(frames,ignore_index=True)
    save(sc,'scalability_results_for_later.csv')

def historical_search():
    b=read(MOT/'results/raw/motivation3_budget_trials.csv')
    b=b[b.Dataset.ne('GeoLife reproduction')].copy()
    check('budget 40 main nodes',b.NodeUID.nunique()==40)
    check('budget unique keys',not b.duplicated(['NodeUID','Method','BudgetLabel','Seed']).any())
    b['original_method_name']=b.Method;b['method']=b.Method.map(lambda x:METHOD.get(x,x))
    b['dataset']=b.Dataset.map(DS);b['node']=b.NodeUID;b['seed']=b.Seed
    b['algorithm_version']='historical materialized-table search / exact reference'
    for m in ['CPU Analytic QMF','Random Search']:
        check(m+':30 seeds per node and budget',b[b.Method.eq(m)].groupby(['NodeUID','BudgetLabel']).Seed.nunique().eq(30).all())
    beam=b[b.Method.eq('Beam Search')]
    check('Beam deterministic one run per node/budget',beam.groupby(['NodeUID','BudgetLabel']).size().eq(1).all())
    timed=b[b.Method.isin(['CPU Analytic QMF','Random Search','Beam Search'])]
    check('phase-sum accounting',np.allclose(timed.Scoring_s+timed.Expansion_s+timed.Cost_s+timed.Selection_s+timed.BeamTrie_s,timed.ActualPhaseSumTotal_s,atol=1e-9))
    save(b,'budget_search_results.csv')
    methods=['CPU Analytic QMF','Random Search','Beam Search']
    summary=summarize(b[b.Method.isin(methods)],['method','BudgetLabel'],['OptimalConfiguration','OptimalRoot','ConfigurationGap','RootRegret'],legacy=True)
    mask=summary.metric.str.startswith('Optimal');summary.loc[mask,['mean','ci_low','ci_high']]*=100
    save(summary,'fig11_summary.csv')
    official=summary[summary.BudgetLabel.eq('2sqrtN')]
    check('official analytic 65.42 / 95.08',np.isclose(official[(official.method=='Original Analytic QMF')&(official.metric=='OptimalRoot')]['mean'].iloc[0],1141/12))
    r=read(MOT/'results/raw/motivation2_runtime.csv')
    r=r[(r.Dataset!='GeoLife reproduction')&(r.H==3)&(r.K==4)&(r.Status=='PASS')].copy()
    check('40 paired exact nodes',r.NodeUID.nunique()==40)
    agreement=r.groupby(['NodeUID','Method']).SelectedCost.median().unstack()
    check('enumeration and recursive agree',np.allclose(agreement['Exact Enumeration'],agreement['Recursive Exact'],rtol=1e-10,atol=1e-8))
    representatives=[]
    for _,g in r.groupby(['NodeUID','Method']):
        g=g.sort_values(['Total_s','Repeat']);representatives.append(g.iloc[len(g)//2])
    rep=pd.DataFrame(representatives);save(rep,'historical_exact_representative_trials.csv')
    rows=[]
    for _,q in rep.iterrows():
        check('exact phases '+q.NodeUID+q.Method,np.isclose(q.Total_s,q.Scoring_s+q.Expansion_s+q.Cost_s+q.Optimization_s,atol=1e-9))
        rows.append(dict(method=METHOD.get(q.Method,q.Method),node=q.NodeUID,dataset=DS[q.Dataset],seed=q.Seed,
          scoring=q.Scoring_s,expansion=q.Expansion_s,cost=q.Cost_s,selection=q.Optimization_s,other=0.,total=q.Total_s,
          timing_scope='historical same median-total trial',source_file=q.source_file,source_row=q.source_row))
    for _,q in b[(b.Method.isin(methods))&b.BudgetLabel.eq('2sqrtN')].iterrows():
        rows.append(dict(method=q.method,node=q.NodeUID,dataset=q.dataset,seed=q.Seed,
          scoring=q.Scoring_s,expansion=q.Expansion_s,cost=q.Cost_s,selection=q.Selection_s,other=q.BeamTrie_s,
          total=q.ActualPhaseSumTotal_s,timing_scope='historical phase sum; shared preparation + selection',source_file=q.source_file,source_row=q.source_row))
    stages=pd.DataFrame(rows);save(stages,'historical_phase_results.csv')
    save(summarize(stages,['method'],['scoring','expansion','cost','selection','other','total'],legacy=True),'historical_phase_summary.csv')
    return stages

def phase4_batch(name):
    root=P4/'results'/name;manifest=js(root/'manifest.json');receipt=js(root/'receipt.json')
    check(name+':complete',receipt['status']=='COMPLETE')
    index=read(root/'trials.csv');records=[]
    for _,r in index.iterrows():
        p=P4/r.log_path;x=js(p);row=x['row']
        check(row['run_id']+':offline only',x.get('reference_used_only_after_run') is True)
        check(row['run_id']+':correctness',row.get('correctness')=='PASS')
        for metric in ['total_optimizer_time','root_optimal','exact_state_evaluations']:
            if pd.notna(r.get(metric)) and row.get(metric) is not None:
                check(row['run_id']+':'+metric,np.isclose(float(r[metric]),float(row[metric]),rtol=1e-12))
        ref=js(row['offline_reference_path'])
        if row['selected_root'] is not None:
            rr=max(0.,ref['root_costs'][row['selected_root']]-ref['optimal_cost'])
            check(row['run_id']+':root regret',np.isclose(rr,row['root_regret'],rtol=1e-12,atol=1e-9))
        else:check(row['run_id']+':no feasible is not optimal',not row['root_optimal'])
        phase=x['stats'].get('phase_seconds',{})
        check(row['run_id']+':disjoint phases',np.isclose(sum(phase.values()),row['total_optimizer_time'],rtol=1e-10,atol=1e-9))
        row.update(source_file=str(p),source_batch=name,original_method_name=row['method'],
                   method=METHOD.get(row['method'],row['method']),dataset=DS[row['dataset']])
        records.append(row)
    d=pd.DataFrame(records);check(name+':unique',not d.run_id.duplicated().any())
    save(d,name+'_records.csv');return d

def hybrid():
    main=phase4_batch('main40_trajectories');pilot=phase4_batch('pilot_trajectories')
    deadlines=phase4_batch('pilot_deadlines');ab=phase4_batch('component_ablation');h4=phase4_batch('h4_deadlines')
    check('main 720 and all 40',len(main)==720 and main.groupby('method').node.nunique().eq(40).all())
    check('pilot 8 x 3 fixed deadlines',deadlines.groupby(['method','budget_ratio']).size().eq(24).all())
    check('matching pilot node sets',set(deadlines.node)==set(pilot.node)==set(ab.node))
    # Original blocking Exact: only its actual final return is available.
    # This is an availability projection, NEVER an early-interrupted run.
    projected=[]
    for _,r in pilot[pilot.original_method_name.eq('EXACT')].iterrows():
        for ratio in [.25,.5,.75,1.,1.5]:
            row=r.to_dict();budget=ratio*r.T_exact_frozen;avail=bool(r.feasible and r.total_optimizer_time<=budget)
            row.update(budget_ratio=ratio,requested_wall_budget=budget,protocol='original blocking return availability projection',
                feasible=avail,root_optimal=bool(avail and r.root_optimal),root_regret=r.root_regret if avail else np.nan,
                source_batch='pilot_exact_return_projection')
            projected.append(row)
    actual=pd.concat([deadlines,pd.DataFrame(projected)],ignore_index=True)
    save(actual,'fig13_budget_records.csv')
    save(summarize(actual,['method','budget_ratio'],['root_optimal','feasible','total_optimizer_time']),'fig13_budget_summary.csv')
    save(summarize(main,['method'],['total_optimizer_time','root_optimal','work_exact_completed','work_terminal_work']),'current_wallclock_summary.csv')
    phase=[c for c in main if c.startswith('phase_')]
    save(summarize(main,['method'],phase),'current_phase_summary.csv')
    save(summarize(h4,['method','budget_ratio'],['root_optimal','feasible','total_optimizer_time']),'h4_budget_summary.csv')
    # Compare ratio of node means; bootstrap the paired nodes jointly.
    work=[]
    for panel,base,methods in [('cache','M2',['M2','M3','C_STATE_OFF','C_TERM_OFF','C_CONFIG_OFF']),
                               ('feedback','M7',['M7','M8','M6'])]:
        for metric in ['work_exact_completed','work_terminal_work','total_optimizer_time']:
            wide=ab.groupby(['node','original_method_name'])[metric].mean().unstack().sort_index()
            for method in methods:
                num=wide[method].to_numpy();den=wide[base].to_numpy()
                rng=np.random.default_rng(20261020);ix=rng.integers(0,len(wide),(2000,len(wide)))
                ratios=num[ix].mean(1)/den[ix].mean(1)
                lo,hi=np.quantile(ratios,[.025,.975])
                work.append(dict(panel=panel,method=METHOD.get(method,method),original_method_name=method,
                    baseline=METHOD.get(base,base),metric=metric,mean=num.mean()/den.mean(),ci_low=lo,ci_high=hi,
                    raw_mean=num.mean(),baseline_mean=den.mean(),nodes=len(wide),runs=24,
                    mean_reduction_pct=100*(1-num.mean()/den.mean())))
    save(pd.DataFrame(work),'fig13_work_summary.csv')
    orders=[]
    for node in sorted(ab.node.unique()):
        for seed in sorted(ab.seed.unique()):
            pair=ab[(ab.node==node)&(ab.seed==seed)&ab.original_method_name.isin(['M7','M8'])]
            histories={}
            for _,row in pair.iterrows():
                x=js(row.source_file);histories[row.original_method_name]=[(e['selected_state'],e['selected_task']) for e in x['stats'].get('frontier_events',[])]
            orders.append(dict(node=node,seed=seed,feedback_changed_order=histories['M7']!=histories['M8']))
    save(pd.DataFrame(orders),'feedback_execution_order_check.csv')
    save(pd.concat([main,pilot,deadlines,ab,h4],ignore_index=True),'hybrid_results.csv')
    return main

def main():
    OUT.joinpath('data').mkdir(exist_ok=True)
    controlled();old=historical_search();current=hybrid()
    # Keep mixed timing provenance as rows, not as a common performance ranking.
    current=current.copy();current['timing_scope']='Phase4 fresh full-pipeline wall clock with observer'
    old=old.copy();old['source_batch']='historical_reference_budget';old['total_optimizer_time']=old.total
    save(pd.concat([old,current],ignore_index=True),'optimization_time_results.csv')
    for p in [P4/'src/comparison_adapter.py',P4/'src/hybrid_optimizer.py',P4/'src/shared_cache.py',
              P4/'src/trajectory_metrics.py',P4/'src/instrumentation.py',P4/'configs/phase4_frozen.json',
              P3/'src/controlled_builder.py',P2/'src/controlled_builder.py',
              CORE/'experiments/build_index.py',CORE/'experiments/plot_results.py',
              MOT/'experiments/search_worker.py']:
        if p.exists():raw(p)
    pd.DataFrame(SOURCES.values()).to_csv(OUT/'data/provenance.csv',index=False)
    pd.DataFrame(CHECKS).to_csv(OUT/'reports/data_checks.csv',index=False)
    (OUT/'reports/extraction_receipt.json').write_text(json.dumps(dict(
        checks=len(CHECKS),all_pass=all(x['passed'] for x in CHECKS),sources=len(SOURCES),
        experiments_run=0,algorithms_imported=False,old_data_modified=False),indent=2))
    print(json.dumps(dict(checks=len(CHECKS),sources=len(SOURCES),all_pass=True)),flush=True)

if __name__=='__main__':main()
