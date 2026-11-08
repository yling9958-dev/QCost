"""Durable sequential continuation; no automatic retries or overwritten phases."""
import json,subprocess,sys,time,traceback
from initial_audit import ROOT,write
from run_stage import now
def main():
    state=ROOT/'08_reports/pipeline_state.json'
    for phase in ['reference','reference_cluster','correctness','timing']:
        write(state,dict(at=now(),phase=phase,status='RUNNING',controller_pid=__import__('os').getpid()))
        log=ROOT/'08_reports'/f'pipeline_{phase}.log'
        with log.open('a') as f:
            result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/postgres_stages.py'),phase],stdout=f,stderr=subprocess.STDOUT)
        if result.returncode:
            write(state,dict(at=now(),phase=phase,status='FAILED_REQUIRES_DIAGNOSIS',returncode=result.returncode))
            raise RuntimeError('Phase failed; no automatic retry: '+phase)
        subprocess.run([sys.executable,'-B',str(ROOT/'tools/finalize.py')],check=True)
    write(state,dict(at=now(),phase='acceptance',status='PHASES_FINISHED_REQUIRES_FINAL_AUDIT'))
if __name__=='__main__':main()
