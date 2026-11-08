"""Independent stdlib recomputation; run only after all experiment phases finish."""
import csv,json,math,hashlib,subprocess
from pathlib import Path
from initial_audit import ROOT,sha,write
def rows(p):
    with p.open() as f:return list(csv.DictReader(f))
def close(a,b):return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-10)
def quantile(sorted_values,p):
    pos=(len(sorted_values)-1)*p;lo=math.floor(pos);hi=math.ceil(pos)
    return sorted_values[lo]+(sorted_values[hi]-sorted_values[lo])*(pos-lo)
def main():
    accepted=json.loads((ROOT/'07_metrics/acceptance.json').read_text())
    assert accepted['status']=='EXPERIMENT_COMPLETED' and all(accepted['checks'].values())
    metrics=rows(ROOT/'FLOOD_SKEWED2D_METRICS.csv');assert len(metrics)==1;m=metrics[0]
    q=rows(ROOT/'03_validation/frozen_queries/skewed_2d_queries.csv')
    perf=[x for x in q if x['split']=='performance'];corr=[x for x in q if x['split']=='correctness']
    ns=[];raw=[];memory=[]
    for rep in range(5):
        rr=rows(ROOT/'05_queries'/f'latency.r{rep}.csv');assert len(rr)==3000
        for ordinal,(a,b) in enumerate(zip(rr,perf)):
            assert a['method']=='flood' and int(a['repetition'])==rep and int(a['ordinal'])==ordinal
            assert a['query_id']==b['query_id'] and a['selectivity_group']==b['selectivity_group']
            assert int(a['latency_ns'])>=0 and 0<=int(a['result_count'])<=204986702
            ns.append(int(a['latency_ns']));raw.append(a)
        ready=json.loads((ROOT/'05_queries'/f'latency.r{rep}.csv.ready').read_text());assert ready['repetition']==rep
        assert ready['fairness']['query_count']==300+3000*(rep+1) and ready['fairness']['load_count']==1
        memory.append((ready['backend_peak_rss_kib']+ready['client_peak_rss_kib'])*1024)
    exported=rows(ROOT/'FLOOD_SKEWED2D_LATENCIES.csv');assert len(exported)==len(raw)==15000
    for a,b in zip(exported,raw):
        assert int(a['Round'])==int(b['repetition'])+1 and a['Query_ID']==b['query_id']
        assert close(a['Latency_ms'],int(b['latency_ns'])/1e6) and a['Result_Count']==b['result_count'] and a['Query_Class']==b['selectivity_group']
    cr=rows(ROOT/'06_correctness/raw_correctness.csv');ce=rows(ROOT/'FLOOD_SKEWED2D_CORRECTNESS.csv');assert len(cr)==len(ce)==len(corr)==1000
    for a,b,c in zip(cr,ce,corr):
        assert a['query_id']==b['Query_ID']==c['query_id']
        assert a['truth_count']==a['result_count']==a['count_result']==b['Flood_Count']==b['Reference_Count']
        assert a['missing']==a['extra']=='0' and a['exact']==a['count_exact']==b['Match']=='1'
        assert [float(v) for v in json.loads(b['Query_Bounds'])]==[float(c[k]) for k in ['xmin','ymin','xmax','ymax']]
    b=rows(ROOT/'04_build/build.csv');assert len(b)==1;b=b[0]
    assert int(b['build_ns'])+int(b['serialize_ns'])==int(b['total_ns'])
    memory.append(int(b['peak_rss_kib'])*1024)
    for p in [ROOT/'04_build/full_build_receipt.json',ROOT/'06_correctness/correctness_receipt.json',ROOT/'05_queries/timing_receipt.json']:
        receipt=json.loads(p.read_text());assert receipt['returncode']==0 and receipt['stop_reason'] is None
        memory.append(receipt['historical_peak_rss_bytes'])
    s=json.loads((ROOT/'06_correctness/summary.json').read_text());memory.append((s['backend_peak_rss_kib']+s['client_peak_rss_kib'])*1024)
    assert s['fairness']['query_count']==2000 and s['fairness']['load_count']==1
    mean=math.fsum(ns)/len(ns);ordered=sorted(ns)
    derived=dict(Build_Time_s=int(b['total_ns'])/1e9,Mean_Latency_ms=mean/1e6,P95_Latency_ms=quantile(ordered,.95)/1e6,P99_Latency_ms=quantile(ordered,.99)/1e6,QPS=1e9/mean,Peak_RSS_MiB=max(memory)/2**20)
    for k,v in derived.items():assert close(m[k],v),(k,m[k],v)
    assert m['Index_Size_MiB']=='N/A' and m['Status']=='EXPERIMENT_COMPLETED' and int(m['Points'])==204986702
    edge_runs=[]
    for p in (ROOT/'03_validation').glob('count_kernel_edges_*/PASS.json'):
        edge=json.loads(p.read_text())
        if edge.get('status')!='PASS' or edge.get('verification_script_sha256')!=sha(ROOT/'tools/verify_count_edges.py'):continue
        records=rows(p.parent/'correctness.csv');assert len(records)==edge['exact_COUNT_and_ID_checks']==4928
        assert all(r['exact']=='1' and r['reference_count']==r['native_count']==r['id_count'] for r in records)
        groups={}
        for r in records:groups.setdefault((r['orientation'],r['lifecycle']),[]).append(r['query_id'])
        assert set(groups)=={(o,l) for o in ['normal','swapped'] for l in ['first_load','destroy_then_reload']}
        assert all(len(ids)==len(set(ids))==1232 for ids in groups.values())
        first=next(iter(groups.values()));assert all(ids==first for ids in groups.values())
        edge_runs.append(str(p.relative_to(ROOT)))
    assert edge_runs, 'Dedicated native COUNT edge diagnostics are required separately from ID-only fixtures.'
    for p,h in json.loads((ROOT/'01_environment/protected_results.json').read_text()).items():assert sha(p)==h
    required=['METRICS.csv','LATENCIES.csv','BUILD_LOG.txt','CORRECTNESS.csv','DIAGNOSIS.md','REPORT.md','REPRODUCE.sh']
    files={}
    for suffix in required:
        p=ROOT/('FLOOD_SKEWED2D_'+suffix);assert p.is_file() and p.stat().st_size>0;files[str(p)]=sha(p)
    subprocess.run(['bash','-n',str(ROOT/'FLOOD_SKEWED2D_REPRODUCE.sh')],check=True)
    write(ROOT/'07_metrics/independent_audit.json',dict(status='PASS',computation='Python stdlib math.fsum and explicit linear percentile interpolation, independent of NumPy aggregation',metrics=derived,formal_latency_records=len(ns),exact_correctness_records=len(cr),count_kernel_edge_runs=edge_runs,deliverable_sha256=files,build_monitoring_gap_disclosed=True))
    print(json.dumps(derived,indent=2))
if __name__=='__main__':main()
