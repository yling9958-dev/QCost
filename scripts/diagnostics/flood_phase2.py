"""Sequential subset-only Flood ownership diagnostics; formal assets are read-only."""
import csv,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'QMF_PostGIS_100M_Repro_20260910'
OUT=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
OLD=Path('/var/tmp/qmf-flood-correctness-memfix-20260915')
ADAPTER=BASE/'src/qmap/cpp/src/baselines/learnedbench_adapters.cpp'
QUERY=ROOT/'results/four_dataset_paper_protocol_20260911/02_queries/geolife_2d_4p2G/correctness_normalized.csv'
def compile_profiles(version):
    source=ADAPTER
    if version=='phase1':
        original=(OUT/'phase1_adapters.cpp').read_text()
        # Diagnostic observation only, after the accepted result has been formed.
        updated=original.replace('#include "indexes/learned/lisa2.hpp"','#include "indexes/learned/lisa2.hpp"\n#include "flood_ownership.hpp"')
        updated=updated.replace('result.candidates = result.ids.size();','result.candidates = result.ids.size();\n        flood_memory::match_digest(matches,Swap,result.candidates);',1)
        source=OUT/'phase1_observed.cpp';source.write_text(updated)
    subprocess.run(['g++','-O3','-DNDEBUG','-march=native','-std=c++17',
        '-I'+str(BASE/'src/qmap/cpp/include'),'-I'+str(ADAPTER.parent),
        '-I/var/tmp/qmf-paper-protocol-20260911/common/learnedbench-patched',
        str(ROOT/'scripts/diagnostics/flood_correctness_profile.cpp'),str(source),
        '-o',str(OUT/('profile_'+version))],check=True)
def available():return next(int(v.split()[1])*1024 for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:'))
def profiles(version):
    for n in (1000000,5000000,10000000,25000000,50000000):
        folder=OUT/version/str(n)
        if (folder/'completed.json').exists():continue
        folder.mkdir(parents=True,exist_ok=True)
        unit=f'qmf-flood-p2-{version}-{n}-20260915'
        command=['systemd-run','--user','--wait','--pipe','--collect','--unit='+unit,
            '--property=MemoryHigh=23622320128','--property=MemoryMax=25769803776','--property=MemorySwapMax=0',
            '--property=TimeoutStopSec=10','--setenv=QMF_FLOOD_MATCH_TRACE='+str(folder/'matches.csv'),
            '--setenv=QMF_FLOOD_OWNERSHIP_TRACE='+str(folder/'ownership.csv'),
            '/usr/bin/time','-v','-o',str(folder/'time.txt'),'taskset','-c',str(min(os.sched_getaffinity(0))),
            str(OUT/('profile_'+version)),str(OLD/'inputs'/f'{n}.idx'),str(QUERY),str(folder/'correctness.csv'),str(folder/'trace.csv')]
        while available()<18*1024**3:print('waiting for diagnostic headroom',flush=True);time.sleep(10)
        print('START',version,n,flush=True);start=time.time();minimum=available()
        with (folder/'output.log').open('x') as log:
            p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            while p.poll() is None:
                minimum=min(minimum,available())
                if minimum<7*1024**3//2:subprocess.run(['systemctl','--user','stop',unit],check=True);raise RuntimeError('HOST_SAFETY_STOP')
                time.sleep(.5)
        if p.returncode:raise RuntimeError((folder/'output.log').read_text()[-3000:])
        assert (folder/'correctness.csv').read_bytes()==(OLD/'profiles'/str(n)/'after/correctness.csv').read_bytes()
        matches=list(csv.reader((folder/'matches.csv').open()))
        assert len(matches)==2000
        corr=list(csv.DictReader((folder/'correctness.csv').open()))
        assert all(int(matches[2*i][2])==int(r['result_count'])==int(matches[2*i+1][2]) for i,r in enumerate(corr))
        trace=list(csv.DictReader((folder/'trace.csv').open()))
        info={'version':version,'N':n,'status':'PASS','correctness':1000,'elapsed_s':time.time()-start,
            'peak_rss_mib':max(int(r['peak_rss_bytes']) for r in trace)/2**20,
            'peak_cgroup_mib':max(int(r['cgroup_memory_peak']) for r in trace)/2**20,'host_min_available':minimum}
        (folder/'completed.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info),flush=True)
        if version!='phase1' and (OUT/'phase1'/str(n)/'matches.csv').exists():
            assert (folder/'matches.csv').read_bytes()==(OUT/'phase1'/str(n)/'matches.csv').read_bytes()
if __name__=='__main__':
    if sys.argv[1]=='compile':compile_profiles(sys.argv[2])
    elif sys.argv[1]=='profile':profiles(sys.argv[2])
