"""Read subset evidence, fit every frozen scale, and preserve all formal files."""
import csv,json,sys
from pathlib import Path
import numpy as np
OUT=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
OLD=Path('/var/tmp/qmf-flood-correctness-memfix-20260915')
SIZES=(1000000,5000000,10000000,25000000,50000000)
def fit(version):
    rows=[json.loads((OUT/version/str(n)/'completed.json').read_text()) for n in SIZES]
    x=np.array(SIZES)/1e6;y=np.array([r['peak_rss_mib'] for r in rows])
    a,b=np.polyfit(x,y,1);r2=1-float(np.sum((y-(a*x+b))**2)/np.sum((y-y.mean())**2))
    return dict(version=version,slope=float(a),intercept=float(b),R2=r2,native_181m_mib=float(a*181+b),profiles=rows)
def main():
    version=sys.argv[1];result=fit(version)
    result.update(old_slope=120.140557887,old_intercept=386.955908950)
    if sys.argv[2:]!=['--native-only']:
        overheads=[146.31640625] # Never hide the previously observed positive overhead.
        pg=[]
        for n in (1000000,5000000):
            folder=OUT/('postgres_'+str(n//1000000)+'M')
            value=json.loads((folder/'complete.json').read_text());assert value['status']=='PASS'
            summary=json.loads((folder/'summary.json').read_text())
            peak=(summary['backend_peak_rss_kib']+summary['client_peak_rss_kib'])/1024
            native=next(r['peak_rss_mib'] for r in result['profiles'] if r['N']==n)
            overheads.append(max(0,peak-native));pg.append({**value,'peak_mib':peak,'positive_overhead_mib':max(0,peak-native)})
        result.update(postgres=pg,postgres_overhead_mib=max(overheads),engineering_margin_mib=1024)
        predicted=result['native_181m_mib']+max(overheads)+1024
        result.update(predicted_181m_peak_mib=predicted,threshold_mib=18432,
            headroom_mib=18432-predicted,minimum_meaningful_headroom_mib=512,
            safe_for_full_retry=predicted<=18432-512,equivalence_pass=True)
        for n in SIZES:
            current=OUT/version/str(n);reference=OUT/'phase1'/str(n)
            assert (current/'correctness.csv').read_bytes()==(reference/'correctness.csv').read_bytes()==(OLD/'profiles'/str(n)/'after/correctness.csv').read_bytes()
            assert (current/'matches.csv').read_bytes()==(reference/'matches.csv').read_bytes()
            samples=list(csv.DictReader((current/'trace.csv').open()))
            assert all(int(row['cgroup_swap_current'])==0 for row in samples)
        for n in (1,5):
            samples=list(csv.DictReader((OUT/f'postgres_{n}M/FLOOD_CORRECTNESS_MEMORY_TRACE.csv').open()))
            assert all(int(row['cgroup_swap_current'])==0 for row in samples)
    path=OUT/(version+'_scaling.json')
    if path.exists():raise RuntimeError('Refuse overwrite '+str(path))
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('profiles','postgres')},indent=2))
if __name__=='__main__':main()
