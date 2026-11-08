"""Two sequential PostgreSQL subset diagnostics inside a fixed shared budget."""
import os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
def available():return next(int(v.split()[1])*1024 for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:'))
def main():
    for n in (1000000,5000000):
        if (OUT/('postgres_'+str(n//1000000)+'M')/'complete.json').exists():continue
        while available()<18*1024**3:time.sleep(10)
        unit=f'qmf-flood-p2-pg-{n}-20260915'
        command=['systemd-run','--user','--wait','--pipe','--collect','--unit='+unit,
            '--property=MemoryHigh=23622320128','--property=MemoryMax=25769803776','--property=MemorySwapMax=0',
            '--property=TimeoutStopSec=30','--setenv=FLOOD_DIAGNOSTIC_ROOT='+str(OUT),
            '--setenv=FLOOD_DIAGNOSTIC_POINTS='+str(n),
            '--setenv=FLOOD_DIAGNOSTIC_INPUTS=/var/tmp/qmf-flood-correctness-memfix-20260915/inputs',
            '--setenv=QMF_FLOOD_OWNERSHIP_TRACE='+str(OUT/f'postgres_{n//1000000}M_ownership.csv'),
            '/usr/bin/python3','-B',str(ROOT/'scripts/diagnostics/flood_postgres_profile.py')]
        print('START PostgreSQL diagnostic',n,flush=True)
        with (OUT/f'postgres_{n}_launch.log').open('x') as log:
            p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            while p.poll() is None:
                if available()<7*1024**3//2:
                    subprocess.run(['systemctl','--user','stop',unit],check=True)
                    raise RuntimeError('HOST_SAFETY_STOP diagnostic')
                time.sleep(.5)
        if p.returncode:raise RuntimeError((OUT/f'postgres_{n}_launch.log').read_text()[-5000:])
        print('PASS PostgreSQL',n,flush=True)
if __name__=='__main__':main()
