"""Flood-only immutable-build resume and exact duplicate-coordinate expansion."""
import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import flood_resume as f
import support as s
import orchestrate as o
import report
import repair_geolife as repair
from test_retry import retry_env, bytes_under, write_valid_method


@pytest.fixture
def flood_env(retry_env,monkeypatch):
    monkeypatch.setattr(f,'FORMAL',s.OUT)
    monkeypatch.setattr(f,'RUNTIME',s.RUN)
    monkeypatch.setattr(f,'ATTEMPTS',retry_env/'attempts')
    monkeypatch.setattr(f,'runtime_path',lambda target:retry_env/('runtime-'+target.name))
    index=s.RUN/'original/flood.idx';index.parent.mkdir(parents=True)
    index.write_bytes(b'protected build fixture')
    (index.parent/'build.csv').write_text('total_ns\n112318935022\n')
    s.done(f.DATASET,'flood_build_r0',{'build_seconds':112.318935022,
        'serialized_bytes':index.stat().st_size,'index_path':str(index),
        'index_sha256':s.sha(index),'peak_rss_kib':1234,'repetition':0},[index])
    q=s.OUT/'02_queries'/f.DATASET/(f.DATASET+'_queries.csv')
    q.parent.mkdir(parents=True);q.write_text('query_id,split\n')
    s.atomic_json(q.parent/'query_manifest.json',{'query_sha256':s.sha(q)})
    source=retry_env/'source.csv';source.write_text('x,y\n')
    s.atomic_json(s.OUT/'01_dataset_inventory'/(f.DATASET+'.json'),{
        'dataset_id':f.DATASET,'source_path':str(source),'raw_bytes':source.stat().st_size,
        'mtime_ns':source.stat().st_mtime_ns,'bounds':[0,0,1,1]})
    return index


def test_flood_build_checkpoint_reused(flood_env):
    before=bytes_under(f.FORMAL);artifact=flood_env.read_bytes()
    record=f.validate_build();target=f.new_attempt()
    assert (target/'checkpoints'/f.DATASET/'flood_build_r0.done').read_bytes()==s.marker(f.DATASET,'flood_build_r0').read_bytes()
    assert record['payload']['build_seconds']==112.318935022
    assert bytes_under(f.FORMAL)==before and flood_env.read_bytes()==artifact


def test_flood_build_not_reexecuted(flood_env,monkeypatch):
    before=bytes_under(f.FORMAL);target=f.new_attempt();calls=[]
    monkeypatch.setattr(o,'ensure_pg',lambda:None)
    monkeypatch.setattr(o,'cleanup_method',lambda *a:None)
    def reached(command,label,*args,**kwargs):
        calls.append(command)
        assert command[command.index('--phase')+1]=='correctness'
        raise o.Blocked('HOST_SAFETY_STOP','diagnostic fixture')
    monkeypatch.setattr(o,'monitor',reached)
    result=f.perform(target)
    assert len(calls)==1 and result['Status']=='HOST_SAFETY_STOP'
    assert result['Build_s']==112.318935022
    assert bytes_under(f.FORMAL)==before


def test_flood_correctness_resume(flood_env,monkeypatch):
    first=f.new_attempt()
    with monkeypatch.context() as m:
        m.setattr(s,'OUT',first)
        corr=first/'04_correctness'/f.DATASET/'flood.csv'
        corr.parent.mkdir(parents=True);corr.write_text('exact\n1\n')
        s.done(f.DATASET,'flood_correctness',{'exact':1000,'missing':0,'extra':0},[corr])
        s.done(f.DATASET,'flood_method',{'Status':'HOST_SAFETY_STOP'})
    before=bytes_under(first);second=f.new_attempt()
    assert (second/'checkpoints'/f.DATASET/'flood_correctness.done').is_file()
    assert not (second/'checkpoints'/f.DATASET/'flood_method.done').exists()
    assert bytes_under(first)==before


def test_flood_invalid_build_never_falls_back_to_build(flood_env):
    flood_env.write_bytes(b'invalid diagnostic fixture')
    with pytest.raises(RuntimeError,match='rebuilding is forbidden'):f.new_attempt()


def test_flood_timing_resume_restores_only_new_working_copies(flood_env,monkeypatch):
    first=f.new_attempt();raw=first/'05_performance'/f.DATASET/'flood/latency.r0.csv.zst'
    raw.parent.mkdir(parents=True)
    contents=b'query_id,repetition,latency_ns\np0,0,100\n'
    subprocess.run(['zstd','-q','-o',str(raw)],input=contents,check=True)
    with monkeypatch.context() as m:
        m.setattr(s,'OUT',first)
        s.done(f.DATASET,'flood_timing_r1',{'repetition':0},[raw])
    before=bytes_under(first);second=f.new_attempt()
    assert (second/'05_performance'/f.DATASET/'flood/latency.r0.csv').read_bytes()==contents
    assert bytes_under(first)==before


def test_flood_only_route_does_not_schedule_pass_or_boost(monkeypatch):
    calls=[];monkeypatch.setattr(f,'start',lambda:calls.append('flood correctness'))
    repair.start(methods=['flood'])
    assert calls==['flood correctness']


def test_flood_query_results_identical():
    # The original operation unions the full ID group once per matched point.
    # The new operation unions it once per distinct matched coordinate.
    import itertools
    groups={(0.,0.):[1,3,7],(1.,1.):[2,5],(0.,1.):[4]}
    for length in range(7):
        for matches in itertools.product(groups,repeat=length):
            before=sorted(set(i for p in matches for i in groups[p]))
            after=sorted(set(i for p in sorted(set(matches)) for i in groups[p]))
            assert before==after


def test_flood_memory_optimization_equivalence():
    # This source gate also prevents the fix from changing build/load/model code.
    root=Path(__file__).resolve().parents[2]
    path=root/'QMF_PostGIS_100M_Repro_20260910/src/qmap/cpp/src/baselines/learnedbench_adapters.cpp'
    source=path.read_text()
    assert 'matches.erase(std::unique(matches.begin(), matches.end()), matches.end());' in source
    old=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915/phase1_adapters.cpp')
    if old.exists():
        # Phase 2 extends ownership only; the accepted Phase 1 output union and
        # untouched LISA suffix remain protected alongside native equivalence.
        assert source.split('class LisaAdapter')[1]==old.read_text().split('class LisaAdapter')[1]
        for line in ['auto matches = index_->range_query(box);',
                     'std::sort(result.ids.begin(), result.ids.end());',
                     'result.candidates = result.ids.size();']:
            assert line in source and line in old.read_text()


def test_resource_accounting_no_double_count(retry_env,monkeypatch):
    (s.OUT/'00_environment').mkdir(parents=True);s.RUN.mkdir(parents=True)
    monkeypatch.setattr(o,'CURRENT',{'phase':'correctness'})
    monkeypatch.setattr(o,'ctl',lambda *a,**kw:None)
    monkeypatch.setattr(o,'props',lambda unit:{'ActiveState':'active','ControlGroup':'pg' if unit==o.PGUNIT else 'worker'})
    def stats(group):
        n=200 if group=='pg' else 10
        return dict(rss=n,vm_peak=n,swap=0,major_faults=0,max_process_rss=n)
    monkeypatch.setattr(o,'cgroup_stats',stats)
    samples=iter([25*s.GIB,25*s.GIB,s.GIB])
    monkeypatch.setattr(o,'memory',lambda:dict(available=next(samples),swap_in=0,swap_out=0))
    snapshot={'path':'/fixture','kernel':{'memory.current':220,'memory.peak':220,'memory.swap.current':0,'memory.events':{}}}
    monkeypatch.setattr(o.cgroup_policy,'snapshot',lambda *a:snapshot)
    monkeypatch.setattr(o.cgroup_policy,'validate',lambda *a:True)
    monkeypatch.setattr(repair.diagnose,'ownership',lambda *a:{})
    monkeypatch.setattr(o.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess([],0,stdout='',stderr=''))
    with pytest.raises(o.Blocked):o.monitor([],'geolife_flood_correctness',adopt_unit='fixture')
    receipt=s.read_json(s.OUT/'00_environment/geolife_flood_correctness_stop_receipt.json')
    assert receipt['worker']['rss']==10
    assert receipt['postgres']['rss']==200
    assert receipt['aggregate']['rss']==210


def test_pass_results_unchanged_during_flood_attempt(flood_env,monkeypatch):
    for runtime in ['qmap_uniform_qmf','postgis_gist','lisa','tsunami','lmsfc','bmtree']:
        # Protected files are opaque immutable assets to the Flood runner.
        s.atomic_json(s.OUT/'pass'/runtime/'result.json',{'Status':'PASS','metric':1.23456789})
    before=bytes_under(f.FORMAL)
    f.new_attempt()
    assert bytes_under(f.FORMAL)==before


def test_no_publication_before_scientific_pass(flood_env):
    before=bytes_under(f.FORMAL);target=f.new_attempt()
    with pytest.raises(RuntimeError):report.publish_flood_attempt(f.FORMAL,target,f.DATASET)
    assert bytes_under(f.FORMAL)==before


def test_publication_preserves_other_rows_and_historical_receipts(flood_env,monkeypatch):
    target=f.new_attempt()
    with monkeypatch.context() as m:
        m.setattr(s,'OUT',target)
        write_valid_method('flood')
    primary=f.FORMAL/'geolife/GEOLIFE_8_METHODS_7_METRICS.csv'
    primary.parent.mkdir()
    labels=['QMF-Index','PostGIS GiST','LISA','Flood','Tsunami','LMSFC','BMTree','Boost R*-tree']
    data=[dict(Method=label,**{k:123.456789 for k in s.METRICS},Correctness='1000/1000 exact',Status='PASS') for label in labels]
    data[3].update(Status='HOST_SAFETY_STOP',Correctness='NOT_RUN')
    s.atomic_csv(primary,data,report.FIELDS)
    primary.with_suffix('.md').write_text(report.table(data))
    old=bytes_under(f.FORMAL)
    report.publish_flood_attempt(f.FORMAL,target,f.DATASET)
    rows=primary.read_bytes().splitlines(keepends=True)
    for i,line in enumerate(old[str(primary.relative_to(f.FORMAL))].splitlines(keepends=True)):
        if i!=4:assert rows[i]==line
    for name,value in old.items():
        if name not in ['geolife/GEOLIFE_8_METHODS_7_METRICS.csv','geolife/GEOLIFE_8_METHODS_7_METRICS.md']:
            assert (f.FORMAL/name).read_bytes()==value
    assert report.valid_method(f.DATASET,'flood')


def test_flood_pg_bindings_are_explicit_and_other_methods_unaffected():
    source=(Path(__file__).parent/'postgres_full.cpp').read_text()
    assert 'if (!flood_session_bindings) return sql;' in source
    assert 'sql.insert(pos, "pg_temp.")' in source
    assert 'method != "flood"' in source
