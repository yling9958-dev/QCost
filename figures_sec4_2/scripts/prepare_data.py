"""Read-only reconstruction of Section 4.2; never runs an experiment.

All quantiles are linear quantiles of the complete retained timing vector.
Every source read is hashed; a subsequent run refuses changed inputs.
"""
from pathlib import Path
import hashlib, io, json, shutil, subprocess
import numpy as np
import pandas as pd
from scipy.stats import t

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parent.parent
PAPER = ROOT / 'QMap-LI/paper_icde_qcost_results'
CORE = ROOT / 'QMF-Core-Ablation'
KIT = 'QMF_Baseline_7Method_Parallel_Kit_20260930'
DS = {'GeoLife':'geolife_2d_4p2G', 'Gowalla':'gowalla_2d_4p2G',
      'NYC Taxi':'nyc_taxi_2d_4p2G', 'Skewed 2D':'skewed_2d'}
POINTS = dict(zip(DS, [181000000,183000000,181000000,204986702]))
METHODS = ['Q-COST','BMTree','LISA','Tsunami','Flood','PostGIS GiST','LMSFC']
CORE_METHODS = {'r4_greedy':'R4 Greedy','cost_h1':'Cost-H1',
                'recursive_exact_h3':'Recursive Exact','cpu_qmf_h3':'Q-COST'}
SOURCE = {}; CHECKS = []; STORAGE = []

def check(name, passed, detail=''):
    CHECKS.append({'check':name,'passed':bool(passed),'detail':str(detail)})
    if not passed:
        pd.DataFrame(CHECKS).to_csv(OUT/'reports/data_checks.csv',index=False)
        raise ValueError(f'{name}: {detail}')

def raw(path):
    p=Path(path); b=p.read_bytes(); s=p.stat()
    SOURCE[str(p)]={'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),
                    'bytes':len(b),'mtime_ns':s.st_mtime_ns}
    return b

def read(path):
    b=raw(path)
    if str(path).endswith('.zst'):
        b=subprocess.run(['zstd','-qdc'],input=b,capture_output=True,check=True).stdout
    return pd.read_csv(io.BytesIO(b))

def js(path): return json.loads(raw(path))
def save(frame,name): frame.to_csv(OUT/'data'/name,index=False)

def protect_existing():
    f=OUT/'reports/source_sha256.csv'
    if f.exists():
        for r in pd.read_csv(f).itertuples():
            check('unchanged_before:'+r.path,hashlib.sha256(Path(r.path).read_bytes()).hexdigest()==r.sha256)
    # Small original figure/script/text files, including both historical CDF versions.
    paths=[]
    for d in ['02_plot_scripts','05_analysis']:
        paths += list((PAPER/d).glob('*'))
    paths += list((PAPER/'03_pdf').glob('fig0[789]*'))
    paths += list((PAPER/'revisions/advisor_baselines_20261015/03_pdf').glob('fig0[789]*'))
    paths += list((PAPER/'08_postgis_gist_completion/07_paper_updates').rglob('fig0[78]*.pdf'))
    for p in paths:
        if p.is_file(): raw(p)
    for p in paths:
        if p.name=='fig07_query_latency.pdf':
            dest=OUT/'reports/backups'/('fig07_original_CDF_'+hashlib.sha256(str(p).encode()).hexdigest()[:8]+'.pdf')
            if not dest.exists(): dest.write_bytes(raw(p))
    for root in [ROOT/'QMF',ROOT/'Mthod',ROOT/'QMap-LI']:
        r=subprocess.run(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],capture_output=True,text=True)
        (OUT/'reports'/('git_status_'+root.name.replace(' ','_')+'.txt')).write_text(r.stdout+r.stderr)

def context():
    kit=ROOT/'Mthod/Tsunami'/KIT
    for rel in ['protocol/TIMING_PROTOCOL.md','protocol/METRIC_DEFINITIONS.md',
                'protocol/BASELINE_IMPLEMENTATIONS.md','protocol/EXPERIMENT_CONFIG_LOCK.json',
                'implementations/shared/engine/postgres_full.cpp',
                'implementations/shared/repro/src/qmap/cpp/src/baselines/formal_baselines.cpp']:
        raw(kit/rel)
    for p in [ROOT/'Mthod/LISA/LISA_IMPLEMENTATION_SCOPE.md',
              ROOT/'Mthod/LISA/LISA_INDEX_SIZE_COMPARABILITY_REPORT.md',
              ROOT/'Mthod/LISA/LISA_FINAL_AUDIT.json',
              ROOT/'Mthod/LMSFC/LMSFC_METHOD_IDENTITY.json',
              ROOT/'Mthod/LMSFC/LMSFC_CR_PARTIAL_FINAL_RESULTS.csv',
              ROOT/'Mthod/Flood/FLOOD_COMPLETE_FINAL_REPORT.md',
              ROOT/'Mthod/Flood/FLOOD_RECOVERY_V2/evidence/FORMAL_RESULT_SKEWED.json',
              PAPER/'09_postgis_fairness_audit_20261019/FAIRNESS_AUDIT.md',
              PAPER/'09_postgis_fairness_audit_20261019/paper/revised_section52.tex',
              CORE/'README.md',CORE/'experiments/build_index.py',CORE/'experiments/audit_data.py',
              CORE/'src/adapters/native_benchmark.cpp',CORE/'manifests/SOURCE_COPIES.json']:
        raw(p)
    fk=ROOT/'Mthod/Flood/FLOOD_RECOVERY_V2'/KIT
    a=js(kit/'protocol/EXPERIMENT_CONFIG_LOCK.json'); b=js(fk/'protocol/EXPERIMENT_CONFIG_LOCK.json')
    changed=[k for k in set(a)|set(b) if a.get(k)!=b.get(k)]
    check('Flood protocol metadata changes only',set(changed)=={'source_version','EnvironmentID'},changed)
    check('Flood timing policy identical',raw(kit/'protocol/TIMING_PROTOCOL.md')==raw(fk/'protocol/TIMING_PROTOCOL.md'))
    frozen=[]
    for ds in DS.values():
        for phase in ['performance','correctness']:
            digests=[]
            for method in ['BMTree','LISA','Tsunami','LMSFC','PostGIS GiST','Flood/FLOOD_RECOVERY_V2']:
                p=ROOT/'Mthod'/method/KIT/'queries/frozen_queries'/ds/f'{phase}_normalized.csv'
                digest=hashlib.sha256(raw(p)).hexdigest();digests.append(digest)
                frozen.append({'dataset_id':ds,'phase':phase,'implementation_directory':method,'source_file':str(p),'sha256':digest})
            check(ds+':identical frozen '+phase+' files across methods',len(set(digests))==1)
    save(pd.DataFrame(frozen),'frozen_query_identity.csv')

def fullscale():
    kits={m:ROOT/'Mthod'/m/KIT for m in ['BMTree','LISA','Tsunami','LMSFC','PostGIS GiST']}
    kits['Flood']=ROOT/'Mthod/Flood/FLOOD_RECOVERY_V2'/KIT
    qp=kits['Tsunami']/'reference_results/QMF_RESULT_PROVENANCE.json'
    qr=js(qp); rows=[]
    for e in qr:
        r=e['result'].copy();r.update(method='Q-COST',summary_file=str(qp),base=str(Path(e['root'])),internal='qmap_uniform_qmf')
        # Original receipts remain authoritative; archived copies are the fallback.
        if not (Path(r['base'])/f'05_performance/{e["Dataset"]}/qmap_uniform_qmf/query_latency_raw.csv.zst').exists():
            r['base']=str(kits['Tsunami']/f'reference_results/evidence/{e["Dataset"]}/qmap_uniform_qmf')
        rows.append(r)
    for m,f in [('BMTree','BMTREE_FINAL_RESULTS.csv'),('LISA','LISA_FINAL_RESULTS.csv'),
                ('Tsunami','TSUNAMI_FINAL_RESULTS.csv'),('Flood','FLOOD_COMPLETE_FINAL_RESULTS.csv'),
                ('LMSFC','LMSFC_CR_PARTIAL_FINAL_RESULTS.csv')]:
        p=ROOT/'Mthod'/m/f
        for r in read(p).to_dict('records'):
            ds=DS[r['Dataset']]; internal={'BMTree':'bmtree'}.get(m,m.lower())
            if r['AttemptID']=='four_dataset_paper_protocol_20260911':
                base=kits[m]/f'reference_results/evidence/{ds}/{internal}'
            else:
                runmethod='lisa_v2_r3' if m=='LISA' else internal
                base=kits[m]/f'baseline_runs/{runmethod}/{ds}/{r["AttemptID"]}'
            r.update(method=m,summary_file=str(p),base=str(base),internal=internal);rows.append(r)
    pb=PAPER/'08_postgis_gist_completion/06_summary'
    for r in js(pb/'historical_gist_validation.json'):
        r.update(method='PostGIS GiST',summary_file=str(pb/'historical_gist_validation.json'),
                 base=r['EvidenceRoot'],internal='postgis_gist');rows.append(r)
    for code in ['nyc','skewed']:
        p=pb/f'{code}_completed_summary.json';r=js(p)
        r.update(method='PostGIS GiST',summary_file=str(p),base='',internal='postgis_gist',
                 MethodVersion='PostgreSQL 14 / PostGIS 3.2; '+r['CompletionExecutableSHA'],
                 AttemptID='gist_completion_20261019_'+code)
        rows.append(r)
    check('28 planned pairs',len(rows)==28)
    valid=[]; audit=[]; logs=[]; refs={}; correctness_refs={}
    for r in rows:
        dataset=r['Dataset'];ds=DS[dataset];m=r['method'];base=Path(r['base']);key=dataset+'/'+m
        check(key+':full cardinality',int(r['Points'])==POINTS[dataset])
        rr={'dataset':dataset,'method':m,'point_count':int(r['Points']),
            'source_file':'','summary_file':r['summary_file'],'original_method_name':r['Method'],
            'implementation_version':r.get('MethodVersion',''),'attempt_id':r.get('AttemptID',''),
            'dataset_sha256':r['DatasetSHA'],'query_sha256':r['QuerySHA'],
            'protocol_sha256':r['ProtocolSHA'],'environment_id':r.get('EnvironmentID','restored completion; see audit'),
            'status':r['Status'],'correctness_status':r['Correctness'],
            'correctness_scope':'NOT_RUN',
            'mean_ms':np.nan,'p95_ms':np.nan,'p99_ms':np.nan,'qps':np.nan,
            'timing_observations':0,'correctness_observations':0,'build_s':r.get('Build_s',np.nan),
            'failure_reason':r.get('FailureReason','')}
        if r['Status']!='PASS':
            rr['source_file']=r.get('EvidencePath',r['summary_file']);raw(rr['source_file'])
            valid.append(rr);continue
        if 'RawFiles' in r:
            lp=Path(r['RawFiles']['timing']['path']);cp=Path(r['RawFiles']['correctness']['path'])
        else:
            lp=base/f'05_performance/{ds}/{r["internal"]}/query_latency_raw.csv.zst'
            cp=base/f'04_correctness/{ds}/{r["internal"]}.csv'
        d=read(lp); c=read(cp)
        check(key+':15000 positive clocks',len(d)==15000 and np.isfinite(d.latency_ns).all() and (d.latency_ns>0).all())
        check(key+':5x3000 unique slots',not d.duplicated(['repetition','query_id']).any() and d.groupby('repetition').size().tolist()==[3000]*5)
        check(key+':3000 frozen query IDs',set(d.query_id)=={f'performance-{i:05d}' for i in range(3000)})
        check(key+':1000 unique correctness',len(c)==1000 and c.query_id.nunique()==1000)
        if 'reference_count' in c:
            ok=(c.result_count==c.reference_count).all() and c.status.eq('OK').all()
            check(key+':all timed counts match retained truth',(d.result_count==d.reference_count).all() and d.status.eq('OK').all())
        else:
            ok=c.exact.eq(1).all() and c['missing'].eq(0).all() and c.extra.eq(0).all() and c.count_exact.eq(1).all()
        check(key+':correctness pass',ok)
        v=d.latency_ns.to_numpy(dtype=np.float64)/1e6
        values=dict(mean_ms=v.mean(),p95_ms=np.quantile(v,.95,method='linear'),p99_ms=np.quantile(v,.99,method='linear'),qps=1000/v.mean())
        for f,old in [('mean_ms','Mean_ms'),('p95_ms','P95_ms'),('p99_ms','P99_ms'),('qps','QPS')]:
            check(key+':recomputed '+f,np.isclose(values[f],float(r[old]),rtol=1e-10,atol=1e-10),(values[f],r[old]))
        rr.update(values,source_file=str(lp),correctness_file=str(cp),timing_observations=len(d),correctness_observations=len(c),
                  correctness_scope='COUNT_VS_RETAINED_TRUTH' if 'reference_count' in c else 'COUNT_AND_ID_SET')
        valid.append(rr)
        d['dataset']=dataset;d['method_display']=m;d['source_file']=str(lp);d['source_row']=np.arange(len(d))+2
        logs.append(d[['dataset','method_display','repetition','ordinal','query_id','latency_ns','result_count','source_file','source_row']])
        refs[(dataset,m)]=d.sort_values(['repetition','query_id'])
        correctness_refs[(dataset,m)]=c.sort_values('query_id')
        audit.append({'dataset':dataset,'method':m,'raw_rows':len(d),'rounds':d.repetition.nunique(),
                      'queries':d.query_id.nunique(),'correctness_rows':len(c),'all_correct':True,
                      'source_file':str(lp),'correctness_file':str(cp),'summary_file':r['summary_file']})
        # Persistent state is not equated with archive bytes or index-only relations.
        state={'dataset':dataset,'method':m,'mean_ms':values['mean_ms'],'included':False,
               'bytes':np.nan,'state_gib':np.nan,'source_file':'','state_path':'','file_exists_now':False,
               'stat_matches_receipt':None,'scope':'','reason':''}
        if m=='Flood':
            state.update(scope='point archive; reconstruction on preload',reason='Excluded: archive is not complete persisted query state')
        elif m=='PostGIS GiST':
            if 'QueryReadyNativeState_MiB' in r:
                size=round(r['QueryReadyNativeState_MiB']*2**20)
                state.update(included=True,bytes=size,state_gib=size/2**30,source_file=r['summary_file'],
                             scope='PostgreSQL table + all indexes + TOAST/FSM/VM; excludes server catalogs, WAL, temp',
                             reason='Complete per-relation persistent footprint; archived pg_total_relation_size measurement')
            else: state.update(scope='GiST index relation only',reason='Excluded: heap / full table footprint missing')
        else:
            bp=base/f'03_build/{ds}/{r["internal"]}.json'; receipt=js(bp)
            check(key+':one build receipt',len(receipt)==1)
            z=receipt[0]; size=int(z['serialized_bytes']); statepath=Path(z['index_path'])
            check(key+':state bytes match summary',np.isclose(size/2**20,float(r['IndexSize_MiB']),rtol=1e-12))
            check(key+':build receipt matches',np.isclose(float(z['build_seconds']),float(r['Build_s']),rtol=1e-12))
            state.update(included=True,bytes=size,state_gib=size/2**30,source_file=str(bp),state_path=str(statepath),
                         file_exists_now=statepath.is_file(),scope='complete native point payload + serialized query structures',
                         reason='Saved query state, no algorithm rebuild on load')
            if statepath.is_file():
                state['stat_bytes']=statepath.stat().st_size;state['stat_mtime_ns']=statepath.stat().st_mtime_ns
                state['stat_matches_receipt']=state['stat_bytes']==size
                check(key+':current state file size',state['stat_matches_receipt'])
            else: state['reason']+='; original runtime file absent, retained build receipt used'
        STORAGE.append(state)
    frame=pd.DataFrame(valid)
    frame['dataset']=pd.Categorical(frame.dataset,list(DS),ordered=True)
    frame['method']=pd.Categorical(frame.method,METHODS,ordered=True)
    frame=frame.sort_values(['dataset','method'])
    check('unique fullscale pairs',not frame.duplicated(['dataset','method']).any())
    for dataset,g in frame.groupby('dataset',observed=True):
        for f in ['point_count','dataset_sha256','query_sha256']:
            check(dataset+':same '+f,g[f].nunique()==1)
        ref=refs[(dataset,'Q-COST')]
        for m in g[g.status=='PASS'].method:
            x=refs[(dataset,m)]
            check(dataset+'/'+m+':same timed query order and counts',
                  np.array_equal(x[['repetition','query_id','ordinal','result_count']].values,ref[['repetition','query_id','ordinal','result_count']].values))
    old=read(PAPER/'01_processed_data/fig07_08_system_metrics.csv')
    old['method']=old.Method.replace({'LISA-V2':'LISA','Flood-V2':'Flood','Tsunami-CR':'Tsunami'})
    for r in old.itertuples():
        n=frame[(frame.dataset==r.Dataset)&(frame.method==r.method)].iloc[0]
        for new,oldcol in [('mean_ms','Mean_ms'),('p95_ms','P95_ms'),('p99_ms','P99_ms'),('qps','QPS')]:
            check(f'original TABLE II unchanged:{r.Dataset}/{r.method}/{new}',np.isclose(n[new],getattr(r,oldcol),rtol=1e-10))
    save(frame,'fullscale_results.csv');save(pd.DataFrame(audit),'fullscale_validation.csv')
    save(pd.concat(logs,ignore_index=True),'fullscale_latency_observations.csv')
    save(pd.DataFrame(STORAGE),'storage_scope.csv')
    save(frame[(frame.status=='PASS')&~frame.set_index(['dataset','method']).index.isin(old.set_index(['Dataset','method']).index)],'newly_included_results.csv')
    save(frame[(frame.method=='Q-COST')][['dataset','point_count','build_s','summary_file']].assign(construction_hours=lambda x:x.build_s/3600),'qcost_build.csv')
    print('Full-scale:',int(frame.status.eq('PASS').sum()),'/ 28 valid; raw clocks:',sum(a['raw_rows'] for a in audit),flush=True)
    return frame

def controlled():
    cfg=js(CORE/'configs/protocol.json');build=read(CORE/'results/tables/BUILD_LEVEL_METRICS.csv')
    build=build[build.Points==20000].copy()
    check('controlled:80 independent builds',len(build)==80 and not build.duplicated(['Dataset','Method','Seed']).any())
    check('controlled:5 frozen seeds',sorted(build.Seed.unique())==sorted(cfg['seeds']))
    check('controlled:all count and ID correctness',build.Correctness.eq('COUNT_AND_ID_SET_PASS').all())
    dsn={'geolife':'GeoLife','gowalla':'Gowalla','nyc_taxi':'NYC Taxi','skewed_2d':'Skewed 2D'}
    records=[]; bcheck=[]; samples=[]
    for ds,label in dsn.items():
        manifest=js(CORE/f'data/{ds}_20000/manifest.json')
        samples.append({'dataset':label,'points':manifest['points'],'sampling':manifest['sampling'],
                        'source_path':manifest['source_path'],'manifest_file':str(CORE/f'data/{ds}_20000/manifest.json'),
                        'manifest_json':json.dumps(manifest)})
        check(ds+':20000 points',manifest['points']==20000)
        qp=CORE/f'data/{ds}_20000/queries_enriched.csv';q=read(qp);q=q[q.split=='performance']
        check(ds+':frozen 3x1000 queries',len(q)==3000 and q.groupby('group').size().tolist()==[1000]*3)
        reference_order=None
        for r in build[build.Dataset==ds].itertuples():
            p=CORE/r.Folder; meta=js(p/'metadata.json');c=read(p/'queries/query_correctness.csv');lp=p/'queries/query_latency.csv';lat=read(lp)
            key=f'{ds}/{r.Method}/{r.Seed}'
            check(key+':metadata identity',meta['status']=='PASS' and meta['method']==r.Method and meta['seed']==r.Seed and meta['points']==20000)
            check(key+':1000 correct ID and count checks',len(c)==1000 and c.query_id.nunique()==1000 and c.exact.eq(1).all() and c['missing'].eq(0).all() and c.extra.eq(0).all() and (c.truth_count==c.count_result).all())
            check(key+':5x3000 positive timings',len(lat)==15000 and (lat.latency_ns>0).all() and not lat.duplicated(['repetition','query_id']).any() and lat.groupby('repetition').size().tolist()==[3000]*5)
            order=lat.sort_values(['repetition','ordinal'])[['repetition','ordinal','query_id','result_count']].values
            if reference_order is None: reference_order=order
            check(key+':matched workload and query order',np.array_equal(order,reference_order))
            check(key+':reported mean preserved',np.isclose(lat.latency_ns.mean()/1e6,build.loc[build.Folder==r.Folder,'Mean (ms)'].iloc[0],rtol=1e-10))
            joined=lat.merge(q[['query_id','group','area','actual_selectivity','result_count']],on='query_id',suffixes=('_clock','_query'),validate='many_to_one')
            check(key+':group/count identity',(joined.group_clock==joined.group_query).all() and (joined.result_count_clock==joined.result_count_query).all())
            for group,g in joined.groupby('group_query'):
                records.append({'dataset':label,'method':CORE_METHODS[r.Method],'original_method_name':r.Method,
                                'build_seed':r.Seed,'area_class':group,'nominal_area_pct':{'S1':.01,'S2':.1,'S3':1}[group],
                                'mean_ms':g.latency_ns.mean()/1e6,'queries':g.query_id.nunique(),'observations':len(g),
                                'source_file':str(lp),'query_file':str(qp),'metadata_file':str(p/'metadata.json')})
            bcheck.append({'dataset':label,'method':CORE_METHODS[r.Method],'build_seed':r.Seed,'raw_rows':len(lat),
                           'correctness_rows':len(c),'correctness_status':'COUNT_AND_ID_SET_PASS','source_file':str(lp)})
    d=pd.DataFrame(records);ref=d[d.method=='R4 Greedy'][['dataset','build_seed','area_class','mean_ms']].rename(columns={'mean_ms':'r4_mean_ms'})
    d=d.merge(ref,on=['dataset','build_seed','area_class'],validate='many_to_one');d['relative_latency']=d.mean_ms/d.r4_mean_ms
    stats=[]
    for (ds,m,a),g in d.groupby(['dataset','method','area_class']):
        v=g.relative_latency.to_numpy();check(f'{ds}/{m}/{a}:5 independent builds',len(v)==5)
        mean=float(v.mean());sd=float(v.std(ddof=1));half=float(t.ppf(.975,4)*sd/np.sqrt(5))
        stats.append({'dataset':ds,'method':m,'area_class':a,'mean_relative_latency':mean,'sd':sd,'ci95_halfwidth':half,
                      'ci95_low':mean-half,'ci95_high':mean+half,'independent_builds':5,'df':4})
    old=read(PAPER/'01_processed_data/fig09_workload_build_groups.csv')
    joined=d.merge(old,left_on=['dataset','method','build_seed','area_class'],right_on=['Dataset','Method','Seed','Group'],validate='one_to_one')
    check('Figure9:all original 240 build-class means preserved',len(joined)==240 and np.allclose(joined.relative_latency,joined.RelativeLatency,rtol=1e-10))
    save(d,'workload_build_pairs.csv');save(pd.DataFrame(stats),'workload_statistics.csv');save(pd.DataFrame(bcheck),'workload_validation.csv')
    save(pd.DataFrame(samples),'controlled_sample_provenance.csv')
    print('Controlled: 80 builds, 240 paired build-class ratios, 1,200,000 raw clocks',flush=True)

def main():
    protect_existing();context();fullscale();controlled()
    pd.DataFrame(SOURCE.values()).to_csv(OUT/'reports/source_sha256.csv',index=False)
    pd.DataFrame(CHECKS).to_csv(OUT/'reports/data_checks.csv',index=False)
    (OUT/'reports/extraction_status.json').write_text(json.dumps({'sources':len(SOURCE),'checks':len(CHECKS),'all_pass':all(x['passed'] for x in CHECKS)},indent=2))
    print('All extraction checks PASS:',len(CHECKS),flush=True)

if __name__=='__main__': main()
