"""1M diagnostic PostgreSQL correctness; no formal database or result writes."""
import csv
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ.get('FLOOD_DIAGNOSTIC_ROOT','/var/tmp/qmf-flood-correctness-memfix-20260915'))
N=int(os.environ.get('FLOOD_DIAGNOSTIC_POINTS','1000000'))
WORK=OUT/('postgres_'+str(N//1000000)+'M')
PGBIN=Path('/usr/lib/postgresql/14/bin')
FORMAL=ROOT/'results/four_dataset_paper_protocol_20260911'

def main():
    WORK.mkdir(exist_ok=True)
    if (WORK/'complete.json').exists():raise RuntimeError('Diagnostic already complete')
    data=WORK/'pg_data';socket=WORK/'socket';socket.mkdir(exist_ok=True)
    index=WORK/'indexes';index.mkdir(exist_ok=True)
    inputs=Path(os.environ.get('FLOOD_DIAGNOSTIC_INPUTS',str(OUT/'inputs')))
    if not (index/'flood.idx').exists():(index/'flood.idx').symlink_to(inputs/(str(N)+'.idx'))
    if not data.exists():
        subprocess.run([str(PGBIN/'initdb'),'-D',str(data),'-A','trust','--no-locale'],check=True)
    env={**os.environ,'PGHOST':str(socket),'PGPORT':'55446','PGDATABASE':'postgres'}
    pg=subprocess.Popen([str(PGBIN/'postgres'),'-D',str(data),'-k',str(socket),'-p','55446',
        '-c','listen_addresses=','-c','shared_buffers=128MB','-c','max_parallel_workers_per_gather=0'],
        stdout=(WORK/'postgres.log').open('a'),stderr=subprocess.STDOUT)
    def sql(text):
        return subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-At','-c',text],env=env,check=True,capture_output=True,text=True).stdout
    try:
        for _ in range(100):
            if subprocess.run(['pg_isready'],env=env,capture_output=True).returncode==0:break
            time.sleep(.1)
        sql('CREATE EXTENSION IF NOT EXISTS postgis; CREATE TABLE evaluation (id bigint GENERATED ALWAYS AS IDENTITY (START WITH 0 MINVALUE 0),lon double precision,lat double precision,geom geometry(Point,4326));')
        # Exact frozen raw prefix; the builder is never invoked.
        copy=subprocess.Popen(['psql','-X','-v','ON_ERROR_STOP=1','-c',
            'COPY evaluation(lon,lat) FROM STDIN WITH (FORMAT csv, HEADER true)'],env=env,stdin=subprocess.PIPE)
        with (ROOT/'dataest/geolife_2d_4p2G.csv').open('rb') as source:
            for _ in range(N+1):copy.stdin.write(next(source))
        copy.stdin.close()
        if copy.wait()!=0:raise RuntimeError('Diagnostic prefix COPY failed')
        sql('UPDATE evaluation SET geom=ST_SetSRID(ST_MakePoint(lon,lat),4326); CREATE INDEX diag_gist ON evaluation USING GIST(geom); ANALYZE evaluation;')
        info=sql('SELECT version(); SELECT postgis_lib_version(); SELECT count(*) FROM evaluation;')
        bounds=json.loads((FORMAL/'01_dataset_inventory/geolife_2d_4p2G.json').read_text())['bounds']
        command=[str(OUT/'qmf_postgres_full'),'--conninfo','dbname=postgres application_name=flood_diagnostic',
            '--method','flood','--table','evaluation','--queries',str(FORMAL/'02_queries/geolife_2d_4p2G/geolife_2d_4p2G_queries.csv'),
            '--phase','correctness','--repetitions','5','--start-repetition','0',
            '--index-root',str(index),'--correctness-output',str(WORK/'correctness.csv'),
            '--latency-output',str(WORK/'unused_latency'),'--summary-output',str(WORK/'summary.json'),
            '--memory-trace',str(WORK/'FLOOD_CORRECTNESS_MEMORY_TRACE.csv'),
            '--flood-session-setup',str(OUT/'session_setup.sql')]
        for name,value in zip(('xmin','ymin','xmax','ymax'),bounds):command+=['--source-'+name,str(value)]
        started=time.time()
        with (WORK/'client.log').open('w') as log:subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        rows=list(csv.DictReader((WORK/'correctness.csv').open()))
        assert len(rows)==1000 and all(r['exact']=='1' and r['missing']=='0' and r['extra']=='0' for r in rows)
        (WORK/'complete.json').write_text(json.dumps({'points':N,'queries':len(rows),'status':'PASS',
            'elapsed_s':time.time()-started,'environment':info,'original_results_written':False},indent=2)+'\n')
    finally:
        if pg.poll() is None:pg.send_signal(2);pg.wait(timeout=30)
if __name__=='__main__':main()
