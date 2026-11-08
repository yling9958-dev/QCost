"""Descriptive memory extrapolation; never publishes formal benchmark metrics."""
import csv
import json
from pathlib import Path
import numpy as np

OUT=Path('/var/tmp/qmf-flood-correctness-memfix-20260915')
def trace(path):
    rows=list(csv.DictReader(path.open()))
    return {'peak_rss_mib':max(int(r['peak_rss_bytes']) for r in rows)/2**20,
        'peak_cgroup_mib':max(int(r['cgroup_memory_peak']) for r in rows)/2**20,
        'peak_live_rss_phase':max(rows,key=lambda r:int(r['rss_bytes']))['phase'],
        'peak_live_rss_query':max(rows,key=lambda r:int(r['rss_bytes']))['query_count'],
        'swap_peak':max(int(r['cgroup_swap_current']) for r in rows)}
def main():
    allrows=[]
    for n in (1000000,5000000,10000000,25000000,50000000):
        for v in ('before','after'):
            folder=OUT/'profiles'/str(n)/v
            info=json.loads((folder/'completed.json').read_text())
            rows=list(csv.DictReader((folder/'correctness.csv').open()))
            assert info['status']=='PASS' and len(rows)==1000
            assert all(r['exact']=='1' and r['count_exact']=='1' and r['missing']=='0' and r['extra']=='0' for r in rows)
            assert (folder/'correctness.csv').read_bytes()==(folder.parent/'before/correctness.csv').read_bytes()
            allrows.append({**info,**trace(folder/'memory_trace.csv')})
    with (OUT/'FLOOD_CORRECTNESS_MEMORY_SCALING.csv').open('x') as stream:
        w=csv.DictWriter(stream,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    after=[r for r in allrows if r['version']=='after']
    slope,intercept=np.polyfit([r['N']/1e6 for r in after],[r['peak_rss_mib'] for r in after],1)
    pg=trace(OUT/'postgres_1M/FLOOD_CORRECTNESS_MEMORY_TRACE.csv')
    pg_summary=json.loads((OUT/'postgres_1M/summary.json').read_text())
    pg_peak=(pg_summary['backend_peak_rss_kib']+pg_summary['client_peak_rss_kib'])/1024
    pg_overhead=max(0,pg_peak-after[0]['peak_rss_mib'])
    # State a conservative fixed 1 GiB engineering margin, not a statistical CI.
    # Same model regardless of whether it meets the user's 18 GiB admission gate.
    predicted=float(slope*181+intercept+pg_overhead+1024)
    result={'linear_slope_mib_per_million':float(slope),'intercept_mib':float(intercept),
        'native_181m_prediction_mib':float(slope*181+intercept),'postgres_1m_peak_mib':pg_peak,
        'postgres_overhead_mib':pg_overhead,'engineering_margin_mib':1024,
        'predicted_181m_peak_mib':predicted,'threshold_mib':18*1024,
        'memory_gate_pass':predicted<=18*1024,'equivalence_pass':True,
        'full_scale_measured':False,'diagnostic_only':True,
        'caveat':'Prefix composition and duplicate multiplicity vary; five-point extrapolation is descriptive, not a guarantee or confidence interval.',
        'postgres_trace':pg,'profiles':allrows}
    (OUT/'profile_analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='profiles'},indent=2))
if __name__=='__main__':main()
