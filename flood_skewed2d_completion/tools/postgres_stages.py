import os,sys,json,time,shutil,subprocess,csv
from pathlib import Path
from run_stage import ROOT,KIT,COMMON,RUNTIME,SLICE,kitlib,configure,monitor,run,write,now,sha,native_env
PG=Path('/usr/lib/postgresql/14/bin')
PGDATA=RUNTIME/'pgdata';SOCKET=RUNTIME/'socket';PORT=55513
UNIT='qmf-skewed-completion-postgres.service'
ENV={'PGHOST':str(SOCKET),'PGPORT':str(PORT),'PGDATABASE':'flood_skewed','PGUSER':'lingyaqi'}
TABLESPACE=ROOT/'06_correctness/reference_tablespace'
def sql(text,db='flood_skewed'):
    return subprocess.check_output([str(PG/'psql'),'-X','-v','ON_ERROR_STOP=1','-At','-c',text],env={**os.environ,**ENV,'PGDATABASE':db},text=True).strip()
def start():
    SOCKET.mkdir(exist_ok=True)
    if not (PGDATA/'PG_VERSION').exists():
        monitor([PG/'initdb','-D',PGDATA,'--auth-local=trust','--auth-host=scram-sha-256','--encoding=UTF8','--locale=C.UTF-8'],ROOT/'06_correctness','initdb',600)
        shutil.copyfile(KIT/'implementations/flood/postgres.conf',PGDATA/'repro.conf')
        with (PGDATA/'postgresql.conf').open('a') as f:
            f.write("\ninclude='repro.conf'\nlisten_addresses=''\nport=55513\nunix_socket_directories='"+str(SOCKET)+"'\n")
    native_args=['--setenv='+k+'='+v for k,v in native_env().items()]
    run(['sudo','-n','systemd-run','--quiet','--unit='+UNIT,'--slice='+SLICE,'--uid='+str(os.getuid()),'--gid='+str(os.getgid()),'-p','KillSignal=SIGINT','-p','TimeoutStopSec=120','-p','StandardOutput=append:'+str(ROOT/'06_correctness/postgres.log'),'-p','StandardError=append:'+str(ROOT/'06_correctness/postgres.log'),*native_args,PG/'postgres','-D',PGDATA])
    for _ in range(60):
        if subprocess.run([str(PG/'pg_isready'),'-h',str(SOCKET),'-p',str(PORT)],capture_output=True).returncode==0:return
        time.sleep(1)
    raise RuntimeError('PostgreSQL startup failed')
def stop():
    subprocess.run(['sudo','-n','systemctl','stop',UNIT],check=True)
def setup():
    TABLESPACE.mkdir(exist_ok=True)
    if sql("SELECT count(*) FROM pg_tablespace WHERE spcname='flood_reference'",'postgres')=='0':
        sql("CREATE TABLESPACE flood_reference LOCATION '"+str(TABLESPACE).replace("'","''")+"'",'postgres')
    if sql("SELECT count(*) FROM pg_database WHERE datname='flood_skewed'",'postgres')=='0':
        sql('CREATE DATABASE flood_skewed TABLESPACE flood_reference','postgres')
    sql("ALTER DATABASE flood_skewed SET temp_tablespaces='flood_reference'")
    sql('CREATE EXTENSION IF NOT EXISTS postgis')
    assert sql('SHOW server_version_num')=='140024' and sql('SELECT PostGIS_Lib_Version()')=='3.2.0'
    if sql("SELECT count(*) FROM pg_proc WHERE proname='qmap_range_count'")=='0':
        text=(KIT/'implementations/shared/repro/src/postgres/qmap_benchmark--1.0.sql').read_text().replace('MODULE_PATHNAME',str(COMMON/'extension/qmap_benchmark'))
        sql(text)
    write(ROOT/'01_environment/postgres_storage.json',dict(pgdata=str(PGDATA),tablespace=str(TABLESPACE),version=sql('SELECT version()'),settings=sql('SHOW ALL'),note='Dedicated reference storage on external exFAT tablespace; PGDATA and measured Flood point archive on NVMe ext4. Historical reference storage was NVMe. Timed Flood count uses preloaded model, no reference table access.'))
def reference():
    setup();folder=ROOT/'06_correctness'
    if not (folder/'load_pass.json').exists():
        if sql("SELECT to_regclass('points') IS NOT NULL")=='t':raise RuntimeError('Incomplete reference load exists; inspect before retry')
        sql('CREATE TABLE points (id BIGINT GENERATED ALWAYS AS IDENTITY (MINVALUE 0 START 0) PRIMARY KEY, x DOUBLE PRECISION NOT NULL,y DOUBLE PRECISION NOT NULL,geom geometry(Point,4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(x,y),4326)) STORED)')
        source=json.loads((ROOT/'01_environment/frozen_protocol.json').read_text())['datasets'][-1]['source_path']
        load=folder/'load.sql';load.write_text("\\copy points(x,y) FROM '"+source.replace("'","''")+"' WITH (FORMAT csv, HEADER true)\nCREATE VIEW evaluation AS SELECT id,x,y,x AS lon,y AS lat,geom FROM points;\nANALYZE points;\n")
        monitor([PG/'psql','-X','-v','ON_ERROR_STOP=1','-f',load],folder,'reference_load',14400,ENV)
        count=int(sql('SELECT count(*) FROM points'));assert count==204986702
        write(folder/'load_pass.json',dict(points=count,at=now()))
    if not (folder/'reference_pass.json').exists():
        monitor([PG/'psql','-X','-v','ON_ERROR_STOP=1','-c','CREATE INDEX points_gist ON points USING GIST(geom); ANALYZE points;'],folder,'reference_gist',43200,ENV)
        write(folder/'reference_pass.json',dict(index_bytes=int(sql("SELECT pg_relation_size('points_gist')")),at=now()))
def reference_cluster():
    folder=ROOT/'06_correctness'
    assert (folder/'reference_pass.json').exists()
    if (folder/'reference_cluster_pass.json').exists():return
    before=sql("SELECT json_build_object('relfilenode',relfilenode,'bytes',pg_relation_size(oid)) FROM pg_class WHERE oid='points'::regclass")
    write(folder/'reference_cluster_before.json',dict(at=now(),table=json.loads(before),purpose='Physical reference heap locality only; original IDs, double coordinates, SQL semantics, Flood binary and frozen queries unchanged. Not part of Flood Build Time or measured query latency.'))
    monitor([PG/'psql','-X','-v','ON_ERROR_STOP=1','-c','CLUSTER VERBOSE points USING points_gist; ANALYZE points;'],folder,'reference_cluster',43200,ENV)
    audit=json.loads(sql("SELECT json_build_object('points',count(*),'min_id',min(id),'max_id',max(id),'sum_id',sum(id)) FROM points"))
    n=204986702
    assert audit==dict(points=n,min_id=0,max_id=n-1,sum_id=n*(n-1)//2)
    indexes=json.loads(sql("SELECT json_agg(json_build_object('name',indexrelid::regclass::text,'valid',indisvalid,'ready',indisready,'clustered',indisclustered)) FROM pg_index WHERE indrelid='points'::regclass"))
    assert all(i['valid'] and i['ready'] for i in indexes)
    assert any(i['name']=='points_gist' and i['clustered'] for i in indexes)
    write(folder/'reference_cluster_pass.json',dict(at=now(),audit=audit,indexes=indexes,physical_layout_only=True))
def query(phase):
    assert (ROOT/'06_correctness/reference_pass.json').exists()
    assert (ROOT/'06_correctness/reference_cluster_pass.json').exists()
    a=json.loads((ROOT/'04_build/artifact.json').read_text());assert sha(a['path'])==a['sha256']
    q=ROOT/'03_validation/frozen_queries/skewed_2d_queries.csv';assert sha(q)=='66fc69a347738af95f89f800f5894c9356b79ff8b036a840c7e280966b8d58dd'
    if phase=='timing':
        rows=list(csv.DictReader((ROOT/'06_correctness/raw_correctness.csv').open()))
        assert len(rows)==1000 and all(r['exact']=='1' and r['count_exact']=='1' and r['missing']=='0' and r['extra']=='0' for r in rows)
    folder=ROOT/('06_correctness' if phase=='correctness' else '05_queries')
    args=['taskset','-c',str(min(os.sched_getaffinity(0))),COMMON/'qmf_postgres_full','--conninfo','dbname=flood_skewed application_name=qmf_full_flood','--method','flood','--table','evaluation','--queries',q,'--repetitions','5','--phase',phase,'--start-repetition','0','--index-root',RUNTIME,'--source-xmin','0.0','--source-ymin','0.0','--source-xmax','0.99999999','--source-ymax','0.99999991','--correctness-output',ROOT/'06_correctness/raw_correctness.csv','--latency-output',ROOT/'05_queries/latency','--summary-output',ROOT/'06_correctness/summary.json']
    monitor(args,folder,phase,43200,ENV)
def main(phase):
    with kitlib.GlobalLease('flood_skewed2d_completion') as lease:
        configure();write(ROOT/'01_environment'/f'{phase}_lease.json',dict(ticket=str(lease.ticket),at=now()))
        try:
            start()
            if phase=='setup':setup()
            elif phase=='reference':reference()
            elif phase=='reference_cluster':reference_cluster()
            elif phase in ('correctness','timing'):query(phase)
            else:raise ValueError(phase)
        finally:stop()
if __name__=='__main__':main(sys.argv[1])
