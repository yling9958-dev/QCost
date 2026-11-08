"""Read-only, timestamped evidence of current pipeline and PostgreSQL work."""
import json,os,subprocess,time
from pathlib import Path
from initial_audit import ROOT,write
from run_stage import RUNTIME,now
def observe():
    unit='flood-skewed-pipeline-controller-20261024.service'
    r=subprocess.run(['systemctl','show',unit,'-p','MainPID','-p','ActiveState','-p','Result'],capture_output=True,text=True)
    state=dict(l.split('=',1) for l in r.stdout.splitlines() if '=' in l)
    pid=int(state.get('MainPID',0));proc=Path('/proc',str(pid))
    result=dict(at=now(),unit=unit,systemd=state,live=False)
    if pid and proc.exists():
        try:
            result.update(live=True,cmdline=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(),start_ticks=int((proc/'stat').read_text().rsplit(')',1)[1].split()[19]))
        except FileNotFoundError:result['live']=False
    sql="""SELECT json_build_object(
      'activity',(select json_agg(a) from (select pid,state,wait_event_type,wait_event,extract(epoch from clock_timestamp()-query_start)::int elapsed_s,left(query,150) query from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid()) a),
      'copy',(select json_agg(c) from (select pid,bytes_processed,tuples_processed from pg_stat_progress_copy) c),
      'index',(select json_agg(i) from (select pid,phase,blocks_total,blocks_done,tuples_total,tuples_done from pg_stat_progress_create_index) i),
      'cluster',(select json_agg(k) from (select pid,phase,heap_tuples_scanned,heap_tuples_written,heap_blks_total,heap_blks_scanned,index_rebuild_count from pg_stat_progress_cluster) k),
      'vacuum',(select json_agg(v) from (select pid,phase,heap_blks_total,heap_blks_scanned from pg_stat_progress_vacuum) v))"""
    q=subprocess.run(['psql','-X','-At','-c',sql],env={**os.environ,'PGHOST':str(RUNTIME/'socket'),'PGPORT':'55513','PGDATABASE':'flood_skewed','PGCONNECT_TIMEOUT':'3'},capture_output=True,text=True,timeout=10)
    result['postgres']=json.loads(q.stdout) if q.returncode==0 else {'connection_error':q.stderr.strip()}
    result['backend_process_evidence']={}
    for backend in result['postgres'].get('activity') or []:
        backend_pid=backend['pid'];directory=Path('/proc',str(backend_pid))
        try:
            stat=(directory/'stat').read_text().rsplit(')',1)[1].split()
            result['backend_process_evidence'][str(backend_pid)]={
                'start_ticks':int(stat[19]),'cpu_ticks':int(stat[11])+int(stat[12]),
                'io':{k:int(v.strip()) for k,v in (line.split(':',1) for line in (directory/'io').read_text().splitlines())}}
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            result['backend_process_evidence'][str(backend_pid)]={'unavailable_at_sample':True}
    p=ROOT/'08_reports/pipeline_state.json'
    result['recorded_phase']=json.loads(p.read_text()) if p.exists() else None
    result['resources']={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines()) if k in ['MemAvailable','SwapFree','SwapTotal']}
    result['timing_rows']={p.name:sum(1 for _ in p.open())-1 for p in (ROOT/'05_queries').glob('latency.r*.csv*') if p.suffix in ['.csv','.part']}
    corr=ROOT/'06_correctness/raw_correctness.csv'
    result['correctness_rows']=sum(1 for _ in corr.open())-1 if corr.exists() else 0
    output=ROOT/'08_reports/observations';output.mkdir(exist_ok=True)
    write(output/f'{time.time_ns()}.json',result)
    write(ROOT/'08_reports/latest_observation.json',result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':observe()
