"""Sequential engineering profiles only; never touches formal output/runtime."""
import csv
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=Path('/var/tmp/qmf-flood-correctness-memfix-20260915')
QUERY=ROOT/'results/four_dataset_paper_protocol_20260911/02_queries/geolife_2d_4p2G/correctness_normalized.csv'
def available():
    return next(int(v.split()[1])*1024 for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:'))
def main():
    for n in (1000000,5000000,10000000,25000000,50000000):
        for version in ('before','after'):
            folder=OUT/'profiles'/str(n)/version
            if (folder/'completed.json').exists():continue
            folder.mkdir(parents=True,exist_ok=True)
            unit=f'qmf-flood-diag-{n}-{version}-20260915'
            args=['systemd-run','--user','--wait','--pipe','--collect','--unit='+unit,
                '--property=MemoryHigh=23622320128','--property=MemoryMax=25769803776',
                '--property=MemorySwapMax=0','--property=TimeoutStopSec=10',
                '/usr/bin/time','-v','-o',str(folder/'time.txt'),'taskset','-c',str(min(os.sched_getaffinity(0))),
                str(OUT/('profile_'+version)),str(OUT/'inputs'/f'{n}.idx'),str(QUERY),
                str(folder/'correctness.csv'),str(folder/'memory_trace.csv')]
            while available()<24*1024**3:
                # A clean diagnostic admission gate; does not change formal policy.
                if available()>18*1024**3:break
                print('waiting for diagnostic headroom',flush=True);time.sleep(10)
            print(f'START {n} {version}',flush=True)
            started=time.time(); minimum=available();status=None
            with (folder/'output.log').open('w') as log:
                p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
                while p.poll() is None:
                    minimum=min(minimum,available())
                    if minimum<7*1024**3//2:
                        subprocess.run(['systemctl','--user','stop',unit],check=True)
                        status='HOST_SAFETY_STOP';break
                    time.sleep(.5)
                code=p.wait()
            rows=list(csv.DictReader((folder/'correctness.csv').open())) if (folder/'correctness.csv').exists() else []
            if status is None:status='PASS' if code==0 and len(rows)==1000 else 'FAILED'
            result={'N':n,'version':version,'status':status,'exit_code':code,'elapsed_s':time.time()-started,
                    'host_min_available':minimum,'correctness_queries':len(rows)}
            (folder/'completed.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps(result),flush=True)
            if status!='PASS':raise RuntimeError('Diagnostic did not complete; inspect '+str(folder))
            if version=='after':
                assert (folder/'correctness.csv').read_bytes()==(folder.parent/'before/correctness.csv').read_bytes()
if __name__=='__main__':main()
