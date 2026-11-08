"""Read existing measurements only: no Qiskit, optimizer, build or query execution."""
from pathlib import Path
import io,json,hashlib,math
import numpy as np
import pandas as pd
from scipy.stats import t

OUT=Path(__file__).resolve().parents[1]
BASE=OUT.parent.parent
STUDY=BASE/'Q-COST-QMF-Necessity-Study'
QUANTUM=BASE/'QMF-Quantum-Circuit'
OLD=BASE/'QMap-LI/paper_icde_qcost_results'
DS={'geolife':'GeoLife','gowalla':'Gowalla','nyc_taxi':'NYC Taxi','skewed_2d':'Skewed 2D'}
METHOD={'M1':'Recursive Exact','EXACT':'Recursive Exact','M3':'Cached Anytime Recursive',
 'M6':'Hybrid-BestFirst','M8':'Hybrid-QMF','M7':'Hybrid-QMF-NoFeedback','QMF':'Original Analytic QMF'}
SOURCES={};CHECKS=[]

def raw(p):
    p=Path(p);v=p.read_bytes();h=hashlib.sha256(v).hexdigest()
    if str(p) in SOURCES:assert SOURCES[str(p)]['sha256']==h
    SOURCES[str(p)]=dict(source_file=str(p),sha256=h,bytes=len(v),mtime_ns=p.stat().st_mtime_ns)
    return v
def js(p):return json.loads(raw(p))
def read(p,**kw):
    d=pd.read_csv(io.BytesIO(raw(p)),**kw)
    d=d.rename(columns={k:'upstream_'+k for k in ['source_file','source_row'] if k in d.columns})
    d['source_file']=str(p);d['source_row']=np.arange(len(d))+2
    return d
def save(d,name):d.to_csv(OUT/'data'/name,index=False)
def ck(name,value,detail=''):
    CHECKS.append(dict(check=name,passed=bool(value),detail=str(detail)))
    if not value:raise AssertionError(name+': '+str(detail))
def mean_ci(values):
    x=np.asarray(values,dtype=float);n=len(x);m=float(np.mean(x))
    half=float(t.ppf(.975,n-1)*np.std(x,ddof=1)/np.sqrt(n)) if n>1 else np.nan
    return dict(mean=m,ci_low=m-half,ci_high=m+half,independent_builds=n,
                ci_status='Student-t over independent builds' if n>1 else 'NOT_ESTIMABLE_SINGLE_BUILD')

def gate():
    rows=[];resources=[];tests=[]
    for n in [4,8,16,32,64]:
        folder=QUANTUM/f'results/stage_{n if n!=64 else "64_aer"}'
        p=folder/'result.json';d=js(p);receipt=js(folder/'receipt.json')
        ck(f'gate N{n} recorded PASS',d['status']==receipt['status']=='PASS')
        for k,r in enumerate(d['measurement_results']):
            expected=math.sin((2*r['j']+1)*math.asin(math.sqrt(r['M']/r['space'])))**2
            ck(f'gate {n}/{k} analytic',abs(r['theory']-expected)<1e-12)
            ck(f'gate {n}/{k} statevector',abs(r['statevector_probability']-expected)<1e-8)
            hits=r['measured_probability']*r['shots']
            ck(f'gate {n}/{k} integer shots',abs(hits-round(hits))<1e-9)
            rows.append(r|dict(hits=int(round(hits)),source_file=str(p),source_record=f'measurement_results[{k}]',
              recorded_status=d['status'],input_scope=d['provenance'],marked_address=n//2))
        for k,r in enumerate(d['resource_results']):
            v=r['resources'];count=sum(r['counts'].values())
            ck(f'gate resource {n}/{k} shots',count==r['shots']==2048)
            ck(f'gate resource {n}/{k} basis',set(v['gate_counts'])<=set(['u','cx']) and v['residual_multi_qubit_gates']==0)
            matching=[x for x in rows if x['N']==n and x['bits']==r['bits'] and x['j']==r['j'] and x['seed']==r['seed_simulator']]
            hits=sum(c for a,c in r['counts'].items() if int(a,2)==n//2)
            ck(f'gate resource {n}/{k} matches shots',len(matching)==1 and matching[0]['hits']==hits)
            resources.append(dict(N=n,bits=r['bits'],j=r['j'],seed=r['seed_simulator'],shots=r['shots'],
              threshold=r['threshold'],address_qubits=v['address_qubits'],cost_qubits=v['cost_qubits'],
              flag_qubits=v['flag_qubits'],ancilla_qubits=v['ancilla_qubits'],total_qubits=v['total_circuit_qubits'],
              circuit_depth=v['transpiled_depth'],single_qubit_gates=v['single_qubit_gates'],
              two_qubit_gates=v['two_qubit_gates'],gate_count=sum(v['gate_counts'].values()),
              gate_counts_json=json.dumps(v['gate_counts']),basis=json.dumps(v['basis']),optimization_level=v['optimization_level'],
              synthesis_seconds=r['synthesis_seconds'],transpilation_seconds=r['transpilation_seconds'],
              simulation_seconds=r['simulation_seconds'],cache_hit=r['cache_hit'],
              source_file=str(p),source_record=f'resource_results[{k}]',
              scope='compiled measured circuit; depth includes measurement; gate count excludes measurement/barriers'))
        for k,r in enumerate(d['tests']):tests.append(dict(N=n,test=r['test'],name=r['name'],status=r['status'],source_file=str(p),source_record=f'tests[{k}]'))
    d=pd.DataFrame(rows);keys=['N','bits','j','M','space','seed']
    ck('gate duplicate streams agree',d.groupby(keys).measured_probability.nunique().le(1).all())
    unique=d.drop_duplicates(keys).copy();save(d,'gate_measurements_all_raw.csv');save(unique,'gate_measurements_unique.csv')
    primary=unique[unique.bits==4].copy();save(primary,'gate_measurements_4bit.csv')
    ck('13 primary configurations',primary.groupby(['N','j']).ngroups==13)
    ck('65 independent simulator seed streams',len(primary)==65)
    ck('five seeds per primary config',primary.groupby(['N','j']).seed.nunique().eq(5).all())
    ck('2048 shots per seed',primary.shots.eq(2048).all())
    ck('133120 primary shots',primary.shots.sum()==133120)
    results=[]
    for (n,j),g in primary.groupby(['N','j']):
        ck(f'gate N{n} j{j} marked and uniform',g.M.eq(1).all() and g.space.eq(n).all() and g.theory.nunique()==1)
        hits=int(g.hits.sum());shots=int(g.shots.sum());measured=hits/shots;theory=float(g.theory.iloc[0])
        z=1.959963984540054;mid=(measured+z*z/(2*shots))/(1+z*z/shots)
        half=z*np.sqrt(measured*(1-measured)/shots+z*z/(4*shots*shots))/(1+z*z/shots)
        results.append(dict(N=n,j=j,bits=4,marked_states=1,marked_address=n//2,
          analytical_pct=100*theory,aer_pct=100*measured,absolute_deviation_pp=100*abs(theory-measured),
          hits=hits,shots=shots,seeds=g.seed.nunique(),seed_values=';'.join(map(str,g.seed)),
          wilson_low_pct=100*(mid-half),wilson_high_pct=100*(mid+half),
          source_file=g.source_file.iloc[0],source_records=';'.join(g.source_record)))
    s=pd.DataFrame(results);save(s,'gate_validation_results.csv')
    c=pd.DataFrame(resources);save(c,'circuit_complexity.csv');save(c[c.bits.isin([6,8])],'wide_register_component_checks.csv')
    save(pd.DataFrame(tests),'gate_recorded_tests.csv')
    historical=read(OLD/'07_reporting_tables/csv/T16_gate_validation.csv')
    save(historical,'historical_gate_table.csv')
    for rel in ['experiments/run_stage.py','experiments/run_stage_qiskit_v1.py','src/qmf_quantum/quantum_backend.py',
                'src/qmf_quantum/resource_profiler.py','src/qmf_quantum/grover_diffusion.py','src/qmf_quantum/phase_oracle.py']:
        raw(QUANTUM/rel)
    for rel in ['environment.json','requirements.lock.txt']:
        raw(QUANTUM/rel)
    return dict(configurations=len(s),seeds_per_config=5,shots_per_seed=2048,total_shots=int(s.shots.sum()),
      max_deviation_pp=float(s.absolute_deviation_pp.max()),max_deviation_configuration=s.loc[s.absolute_deviation_pp.idxmax(),['N','j']].tolist(),
      duplicates_excluded=len(d)-len(unique),wide_register_records=int(unique.bits.ne(4).sum()),
      resource_records=len(c),circuit_depth_min=int(c[c.bits==4].circuit_depth.min()),circuit_depth_max=int(c[c.bits==4].circuit_depth.max()))

def sensitivity():
    p=BASE/'QMF-Motivation-Study/results/raw/motivation2_runtime.csv';r=read(p)
    r=r[r.Dataset!='GeoLife reproduction'].copy();r=r[r.H.isin([1,2,3])&r.K.isin([2,3,4])]
    ck('sensitivity original40',r.NodeUID.nunique()==40)
    ck('sensitivity unique trials',not r.duplicated(['NodeUID','H','K','Method','Repeat']).any())
    save(r,'parameter_runtime_records.csv')
    med=r[r.Status=='PASS'].groupby(['Dataset','NodeUID','H','K','Method']).agg(
      selected_cost=('SelectedCost','median'),optimization_seconds=('Total_s','median'),
      repetitions=('Repeat','nunique'),source_file=('source_file','first'),source_rows=('source_row',lambda x:';'.join(map(str,x)))).reset_index()
    exact=med[med.Method=='Recursive Exact'].copy()
    pairs=med.pivot(index=['NodeUID','H','K'],columns='Method',values='selected_cost').dropna()
    ck('sensitivity all exact enumeration optima agree',np.allclose(pairs['Recursive Exact'],pairs['Exact Enumeration'],rtol=1e-10,atol=1e-8))
    common=exact.groupby('NodeUID').size();common=sorted(common[common==9].index)
    ck('sensitivity common25',len(common)==25)
    balanced=exact[exact.NodeUID.isin(common)].copy()
    baseline=balanced[(balanced.H==1)&(balanced.K==4)][['NodeUID','selected_cost']].rename(columns={'selected_cost':'baseline_H1K4_cost'})
    balanced=balanced.merge(baseline,on='NodeUID',validate='many_to_one')
    ck('sensitivity positive baseline',balanced.baseline_H1K4_cost.gt(0).all())
    balanced['cost_reduction_pct']=100*(1-balanced.selected_cost/balanced.baseline_H1K4_cost)
    save(balanced,'parameter_common25_records.csv')
    feasibility=exact.groupby(['H','K']).NodeUID.nunique().rename('feasible_nodes').reset_index()
    result=balanced.groupby(['H','K']).agg(cost_reduction_pct=('cost_reduction_pct','mean'),
      optimization_seconds=('optimization_seconds','mean'),common_nodes=('NodeUID','nunique')).reset_index().merge(feasibility,on=['H','K'],validate='one_to_one')
    result['evaluated_nodes']=40;result['method']='Recursive Exact';result['cost_baseline']='per-node H1/K4';result['time_statistic']='mean of per-node repeat medians'
    result['source_file']=str(p);result['theoretical_upper_bound']=[int(k)**(2**int(h)-1) for h,k in zip(result.H,result.K)]
    save(result,'parameter_sensitivity.csv')
    old=read(OLD/'07_reporting_tables/csv/T17_sensitivity.csv')
    compared=result.merge(old,on=['H','K'],validate='one_to_one',suffixes=('','_historical'))
    compared['reduction_difference_pp']=compared.cost_reduction_pct-compared.Improvement_pct
    compared['time_difference_s']=compared.optimization_seconds-compared.Total_s
    compared['feasible_difference']=compared.feasible_nodes-compared.Feasible_of_40
    ck('sensitivity historical reduction match',np.allclose(compared.cost_reduction_pct,compared.Improvement_pct,atol=1e-10))
    ck('sensitivity historical time match',np.allclose(compared.optimization_seconds,compared.Total_s,atol=1e-10))
    ck('sensitivity historical feasibility match',compared.feasible_difference.eq(0).all())
    save(compared,'sensitivity_historical_difference.csv')
    population=pd.DataFrame({'node':sorted(r.NodeUID.unique())});population['in_common25']=population.node.isin(common)
    population['feasible_settings']=population.node.map(exact.groupby('NodeUID').size())
    save(population,'sensitivity_population.csv')
    available=[]
    for phase,sub in [('phase3_hybrid_comparison','scaling'),('phase4_complementarity_analysis','scalability'),('phase4_complementarity_analysis','h4_deadlines')]:
        folder=STUDY/phase/'results'/sub;js(folder/'manifest.json');x=read(folder/'trials.csv')
        save(x,f'{phase}_{sub}_records.csv')
        available.append(dict(campaign=f'{phase}/{sub}',records=len(x),columns=';'.join(x.columns),source_file=str(folder/'trials.csv')))
    save(pd.DataFrame(available),'hybrid_parameter_inventory.csv')
    hybrid_parameter_comparison()
    return dict(settings=len(result),paired_nodes=len(common),evaluated_nodes=r.NodeUID.nunique(),
      original_trials=len(r),exact_pairs_checked=len(pairs),historical_table_match=True,
      h3k4_reduction_pct=float(result.query('H==3 and K==4').cost_reduction_pct.iloc[0]),
      h3k4_time_seconds=float(result.query('H==3 and K==4').optimization_seconds.iloc[0]))

def hybrid_parameter_comparison():
    root=STUDY/'phase4_complementarity_analysis'
    d=read(root/'results/scalability/trials.csv')
    g=d[d.method.isin(['EXACT','M8'])].copy()
    ck('Hybrid alternate grid72 runs',len(g)==72 and g.node.nunique()==4)
    ck('Hybrid alternate grid complete',g.groupby(['h','k','method']).size().eq(4).all() and g.groupby(['h','k']).ngroups==9)
    ck('Hybrid alternate grid all solved',g.proven_optimal.eq(True).all() and g.correctness.eq('PASS').all())
    for _,r in g.iterrows():
        logged=js(root/r.log_path)['row']
        ck(r.run_id+' recorded cost and time',np.isclose(r.selected_cost,logged['selected_cost'],rtol=1e-12) and np.isclose(r.total_optimizer_time,logged['total_optimizer_time'],rtol=1e-12))
        reference=raw(r.offline_reference_path)
        ck(r.run_id+' reference hash',hashlib.sha256(reference).hexdigest()==r.offline_reference_sha256)
    pairs=g.pivot(index=['node','h','k','seed'],columns='method',values='selected_cost')
    ck('Hybrid alternate grid same exact optimum',np.allclose(pairs.EXACT,pairs.M8,rtol=1e-10,atol=1e-8))
    for key,v in g.groupby(['node','h','k','seed']):
        ck(str(key)+' identical problem hashes',v.data_sha256.nunique()==1 and v.offline_reference_sha256.nunique()==1)
    g['display_method']=g.method.map({'EXACT':'Recursive Exact','M8':'Q-COST'})
    save(g,'hybrid_parameter_matched_records.csv')
    summary=g.groupby(['h','k','display_method']).agg(mean_seconds=('total_optimizer_time','mean'),
      nodes=('node','nunique'),runs=('node','size'),optimal_runs=('proven_optimal','sum')).reset_index()
    save(summary,'hybrid_parameter_matched_summary.csv')

def index_campaign(phase,sub,summary_name,expected):
    root=STUDY/phase;folder=root/'results'/sub;manifest=js(folder/'manifest.json');s=read(folder/summary_name)
    ck(phase+' unique build ids',not s.duplicated(['dataset','points','method','seed']).any())
    ck(phase+' full count',len(s)==expected and s.status.eq('PASS').all())
    rows=[]
    for _,r in s.iterrows():
        runid=f'{r.dataset}_{r.points}_{r.method}_s{r.seed}';run=folder/runid
        b=js(run/'build.json');m=js(run/'metrics.json');lat=read(run/'latency.csv');correct=read(run/'latency.csv.correctness.csv',keep_default_na=False)
        persisted=raw(run/'index.idx')
        ck(runid+phase+' actual persisted index SHA',hashlib.sha256(persisted).hexdigest()==b['index_sha256'] and len(persisted)==b['index_bytes'])
        ck(runid+phase+' unique latency',len(lat)==15000 and not lat.duplicated(['query_id','repetition']).any() and lat.query_id.nunique()==3000 and lat.repetition.nunique()==5)
        ck(runid+phase+' nonnegative latency',np.isfinite(lat.latency_ns).all() and lat.latency_ns.ge(0).all())
        mean=float(lat.latency_ns.mean()/1e6)
        ck(runid+phase+' latency mean verified',np.isclose(mean,r.mean_ms,rtol=1e-10,atol=1e-14) and np.isclose(mean,m['mean_ms'],rtol=1e-10))
        ck(runid+phase+' build time verified',np.isclose(b['build_seconds'],r.build_seconds,rtol=1e-12))
        ck(runid+phase+' count correctness',len(correct)==1000 and correct.query_id.nunique()==1000 and correct.expected.eq(correct['count']).all())
        ck(runid+phase+' actual root commits',all(d['selected_root']==d['committed_root'] for d in b['decisions']))
        data=root/'data/indexing'/f'{r.dataset}_{r.points}'
        provpath=data/'provenance.json'
        if provpath.exists():prov=js(provpath)
        else:prov=None
        if phase.startswith('phase2'):
            for item in prov:ck(runid+phase+' input copy '+Path(item['copy']).name,hashlib.sha256(raw(item['copy'])).hexdigest()==item['sha256'])
            datahash=next(x['sha256'] for x in prov if x['copy'].endswith('points.npz'))
            queryhash=next(x['sha256'] for x in prov if x['copy'].endswith('queries.csv'))
            kernelhash=m['query_kernel_sha256']
        else:
            datahash=r.data_sha256;queryhash=r.query_sha256;kernelhash=r.kernel_sha256
        row=dict(dataset=DS[r.dataset],dataset_id=r.dataset,points=int(r.points),method=METHOD[r.method],
          display_method='Q-COST' if r.method=='M8' else METHOD[r.method],original_method_name=r.method,seed=int(r.seed),
          campaign=phase,algorithm_version='Hybrid-QMF (M8)' if r.method=='M8' else METHOD[r.method],
          build_seconds=float(b['build_seconds']),mean_ms=mean,p95_ms=float(lat.latency_ns.quantile(.95)/1e6),
          p99_ms=float(lat.latency_ns.quantile(.99)/1e6),index_mib=float(b['index_bytes']/1024**2),index_sha256=b['index_sha256'],
          root_commits=len(b['decisions']),fallback_count=b['fallback_count'],timing_observations=len(lat),query_rounds=5,
          correctness_queries=len(correct),correctness_status='PASS_RECORDED_COUNTS',kernel_sha256=kernelhash,
          data_sha256=datahash,query_sha256=queryhash,model_sha256=manifest['model_hash'],
          build_timing_scope=b['timing_scope'],query_timing_scope=m.get('scope',m.get('timing_scope','native C++ range-count')),
          source_file=str(folder/summary_name),source_row=int(r.source_row),build_log=str(run/'build.json'),
          latency_file=str(run/'latency.csv'),metrics_file=str(run/'metrics.json'),
          protocol_attempts=int(manifest['parameters'].get('attempts',32)),manifest_file=str(folder/'manifest.json'))
        rows.append(row)
    d=pd.DataFrame(rows)
    for key,g in d.groupby(['dataset','points','seed']):
        for col in ['data_sha256','query_sha256','kernel_sha256','model_sha256']:
            ck(phase+str(key)+' shared '+col,g[col].nunique()==1)
    raw(root/'src/controlled_builder.py');raw(root/'experiments/index_worker.py');raw(root/'experiments/run_index_benchmark.py')
    if phase.startswith('phase2'):
        ck('Phase2 frozen source kernel SHA',hashlib.sha256(raw(root/'vendor/cpp/src/static_qmap_index.cpp')).hexdigest()==d.kernel_sha256.iloc[0])
    return d

def summarize_builds(d):
    rows=[]
    for (ds,n,method,campaign),g in d.groupby(['dataset','points','method','campaign']):
        for metric in ['build_seconds','mean_ms']:
            rows.append(dict(dataset=ds,points=n,method=method,display_method=g.display_method.iloc[0],campaign=campaign,
              metric=metric,seeds=';'.join(map(str,g.seed)),source_files=';'.join(g.metrics_file),**mean_ci(g[metric])))
    return pd.DataFrame(rows)

def scalability():
    phase2=index_campaign('phase2_hybrid_optimizer','indexing/pilot_four_datasets','summary.csv',32)
    phase3folder=STUDY/'phase3_hybrid_comparison/results/index20k'
    summaries=sorted(phase3folder.glob('summary_resume_*.csv'))
    ck('Phase3 final resume summary located',len(summaries)>0)
    phase3=index_campaign('phase3_hybrid_comparison','index20k',summaries[-1].name,100)
    save(phase2,'scalability_results.csv');save(summarize_builds(phase2),'scalability_summary.csv')
    save(phase3,'hybrid_20k_five_build_results.csv');save(summarize_builds(phase3),'hybrid_20k_five_build_summary.csv')
    inventory=read(OUT.parent/'figures_sec4_3_4_4/data/scalability_results_for_later.csv')
    save(inventory,'scalability_historical_and_new_inventory.csv')
    requested=[]
    for ds in DS.values():
        for n in [20000,50000]:
            for method in ['R4 Greedy','Cost-H1','Recursive Exact','Hybrid-QMF']:
                g=phase2[(phase2.dataset==ds)&(phase2.points==n)&(phase2.method==method)]
                requested.append(dict(dataset=ds,points=n,requested_method=method,
                   status='AVAILABLE_SINGLE_BUILD' if len(g) else 'NOT_FOUND_IN_MATCHED_HYBRID_CAMPAIGN',
                   independent_builds=len(g),source_file=';'.join(g.metrics_file)))
    save(pd.DataFrame(requested),'requested_scalability_coverage.csv')
    # Retain every completed contemporaneous comparator and every older version separately.
    compared=[]
    for phase,d in [('phase2_hybrid_optimizer',phase2),('phase3_hybrid_comparison',phase3)]:
        for (ds,n,seed),g in d.groupby(['dataset','points','seed']):
            compared.append(dict(campaign=phase,dataset=ds,points=n,seed=seed,
              methods=';'.join(g.method),distinct_index_sha256=g.index_sha256.nunique(),all_indices_identical=g.index_sha256.nunique()==1))
    save(pd.DataFrame(compared),'scalability_structure_comparison.csv')
    return dict(main_campaign='phase2_hybrid_optimizer',main_build_records=len(phase2),
      main_methods=sorted(phase2.method.unique()),main_independent_builds_per_cell=1,
      datasets=4,sizes=[20000,50000],five_build_20k_records=len(phase3),
      requested_methods_missing=['R4 Greedy','Cost-H1'],old_analytic_in_main=False,
      main_indices_identical_within_paired_dataset_size_seed=all(x['all_indices_identical'] for x in compared if x['campaign']=='phase2_hybrid_optimizer'))

def main():
    report={}
    try:
        report['gate']=gate();report['sensitivity']=sensitivity();report['scalability']=scalability()
    finally:
        pd.DataFrame(CHECKS).to_csv(OUT/'reports/data_checks.csv',index=False)
        pd.DataFrame(SOURCES.values()).to_csv(OUT/'data/provenance.csv',index=False)
    report['checks_passed']=len(CHECKS);report['source_files']=len(SOURCES)
    encoded=json.dumps(report,indent=2,ensure_ascii=False,default=lambda v:v.item() if isinstance(v,np.generic) else str(v))
    (OUT/'reports/extraction_receipt.json').write_text(encoded)
    print(encoded)

if __name__=='__main__':main()
