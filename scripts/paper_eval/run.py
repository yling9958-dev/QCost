"""One durable sequential paper campaign; reporting never authorizes benchmark work."""
import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import support as s
import orchestrate as o
import worker
import report
from paper_protocol import (CAMPAIGN_UNIT, DATASET_SPECS, DATASETS,
                            GEOLIFE_NORMALIZED_SHA256, PERFORMANCE_QUERIES_PER_GROUP,
                            PERFORMANCE_REPETITIONS, POINT_COUNTS, PROTOCOL,
                            QUERY_COUNTS, RAW_SHA256, REPAIR_UNIT, TIMEOUTS_S)

UNIT=CAMPAIGN_UNIT
RAW_SHA=RAW_SHA256
POINTS=POINT_COUNTS
GEO_SHA=GEOLIFE_NORMALIZED_SHA256
OLD_UNITS=['qmf-four-dataset-final-20260911','qmf-four-dataset-campaign-guardian',
 'qmf-verification-recovery-1','qmf-worker-688779','qmf-geolife-postgres',
 'qmf-geolife-memfix-20260911','qmf-memory-clean-1','qmf-memory-equivalence-candidate1']
AUDIT_ROOT=s.ROOT/'results/qmf_build_audit_cleanup_20260914'

def passing_test_xml(path,minimum=1):
    import xml.etree.ElementTree as ET
    if not path.exists(): return False
    suites=list(ET.parse(path).iter('testsuite'))
    return sum(int(v.get('tests',0)) for v in suites)>=minimum and all(
        not int(v.get(k,0)) for v in suites for k in ('errors','failures'))

def active(unit): return o.props(unit).get('ActiveState') in ('active','activating','deactivating')

def old_stopped():
    running=[u for u in OLD_UNITS if active(u)]
    if running: raise RuntimeError('OLD_HEAVY_CAMPAIGN_ACTIVE: '+','.join(running))

def source_manifest():
    return {str(p.relative_to(s.BASE)):s.sha(p) for folder in ['src','config']
            for p in sorted((s.BASE/folder).rglob('*')) if p.is_file()}

def control_source_verified(expected):
    current={p.name:s.sha(p) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.cpp')}
    if expected==current: return True
    # An audited orchestration-only cleanup may extend the existing source receipt.
    # Original experiment/source manifests remain unchanged as evidence.
    candidates=[
        (AUDIT_ROOT/'PAPER_CONTROLLER_SOURCE_20260914.json',
         AUDIT_ROOT/'PAPER_EVAL_TESTS_20260914.xml'),
        *[(s.OUT/'00_environment'/receipt_name,s.OUT/'00_environment'/test_name) for receipt_name,test_name in [
          ('qmf_memory_implementation_source_20260913.json','qmf_memory_tests_20260913.xml'),
          ('build_timeout_control_source_20260913.json','build_timeout_tests_20260913.xml'),
          ('retry_logic_control_source_20260912.json','retry_logic_tests_20260912.xml'),
          ('cleanup_control_source_20260912.json','cleanup_tests_20260912.xml')]],
    ]
    for receipt,tests in candidates:
        if not receipt.exists(): continue
        audit=s.read_json(receipt)
        if not passing_test_xml(tests) or s.sha(tests)!=audit.get('tests_sha256'): continue
        if (expected in audit.get('prior_control_manifests',[]) and
                current==audit.get('current_source_manifest')):
            return True
    return False

def production_source_receipt(expected,current):
    """Return the exact tested receipt authorizing current production source."""
    if current==expected: return {'status':'FROZEN_SOURCE'}
    receipt=s.OUT/'00_environment/qmf_memory_implementation_source_20260913.json'
    tests=s.OUT/'00_environment/qmf_memory_tests_20260913.xml'
    changed={path:{'before':expected.get(path),'after':current.get(path)}
             for path in sorted(set(expected)|set(current)) if expected.get(path)!=current.get(path)}
    if receipt.exists() and tests.exists():
        audit=s.read_json(receipt)
        evidence=s.OUT/'00_environment/qmf_memory_equivalence_20260913'
        if passing_test_xml(tests) and s.sha(tests)==audit.get('tests_sha256') and \
           s.sha(s.OUT/'00_environment/production_source_before.json')==audit.get('original_manifest_sha256') and \
           changed==audit.get('changed_production_files') and current==audit.get('current_production_source_manifest') and \
           audit.get('qmf_core_algorithm_changed') is False and \
           audit.get('dataset_changed') is False and audit.get('query_protocol_changed') is False and \
           audit.get('memory_policy_changed') is False and \
           s.sha(evidence/'tree_decision_manifest.csv')=='a7c540d4d5f8e1b34e7508d2be921741203cc13667403fa8b7df587e03696230' and \
           audit.get('standalone_100m_tree_sha256')=='a7c540d4d5f8e1b34e7508d2be921741203cc13667403fa8b7df587e03696230' and \
           audit.get('standalone_100m_index_sha256')=='12bbd47ef650888b67e042002d794e75de64ec5d91c0c2476eded5d85e577282':
            return audit
    receipt=AUDIT_ROOT/'QMF_MEMORY_IMPLEMENTATION_SOURCE_20260914.json'
    tests=AUDIT_ROOT/'QMF_MEMORY_TESTS_20260914.xml'
    if not receipt.exists() or not tests.exists(): return None
    audit=s.read_json(receipt); evidence=AUDIT_ROOT/'equivalence/100mib'
    required={
        'tree_decision_manifest.csv':'a7c540d4d5f8e1b34e7508d2be921741203cc13667403fa8b7df587e03696230',
        'qmap_uniform_qmf.idx':'12bbd47ef650888b67e042002d794e75de64ec5d91c0c2476eded5d85e577282',
    }
    if (passing_test_xml(tests) and s.sha(tests)==audit.get('tests_sha256') and
            s.sha(s.OUT/'00_environment/production_source_before.json')==audit.get('original_manifest_sha256') and
            changed==audit.get('changed_production_files') and
            current==audit.get('current_production_source_manifest') and
            all(audit.get(name) is False for name in (
                'qmf_core_algorithm_changed','dataset_changed',
                'query_protocol_changed','memory_policy_changed')) and
            all((evidence/name).is_file() and s.sha(evidence/name)==digest
                for name,digest in required.items()) and
            audit.get('standalone_100m_tree_sha256')==required['tree_decision_manifest.csv'] and
            audit.get('standalone_100m_index_sha256')==required['qmap_uniform_qmf.idx'] and
            audit.get('standalone_100m_leaf_assignment_sha256')==
                'f114efb06770bc520743c3770fcb2ac95c710f58b6cea02748454b6eff7348fb'):
        return audit
    return None

def production_source_verified(expected, current):
    """Accept only frozen source or an exact, tested equivalence amendment."""
    return production_source_receipt(expected,current) is not None

def dataset_inventory():
    # The current run owns the frozen input metadata; historical result roots are not inputs.
    return [s.read_json(s.OUT/'01_dataset_inventory'/(d+'.json')) for d in DATASETS]

def verify_protocol():
    """Accept only documented infrastructure/implementation amendments."""
    import copy
    path=s.OUT/'00_environment/protocol.json'
    frozen=s.read_json(path)
    if frozen==PROTOCOL: return
    amendment=s.OUT/'00_environment/BUILD_TIMEOUT_PROTOCOL_AMENDMENT_20260913.json'
    old=copy.deepcopy(PROTOCOL)
    old['timeouts_s']['build']=14400
    old['qmf_memory_engineering_production_change']=False
    if frozen!=old or not amendment.exists(): raise RuntimeError('Frozen paper protocol changed')
    audit=s.read_json(amendment)
    if audit.get('original_protocol_sha256')!=s.sha(path) or audit.get('effective_protocol')!=PROTOCOL or \
       (audit.get('old_build_timeout_s'),audit.get('new_build_timeout_s'))!=(14400,43200):
        # The 20260913 receipt predates the implementation provenance flag. Its
        # scientific values must equal the current protocol after that one field
        # is restored to false.
        effective=copy.deepcopy(PROTOCOL)
        effective['qmf_memory_engineering_production_change']=False
        if audit.get('original_protocol_sha256')!=s.sha(path) or \
           audit.get('effective_protocol')!=effective or \
           (audit.get('old_build_timeout_s'),audit.get('new_build_timeout_s'))!=(14400,43200):
            raise RuntimeError('Build timeout protocol amendment invalid')
    implementation=AUDIT_ROOT/'QMF_MEMORY_IMPLEMENTATION_SOURCE_20260914.json'
    if not implementation.exists(): raise RuntimeError('QMF memory implementation receipt missing')
    source_audit=s.read_json(implementation)
    if source_audit.get('qmf_core_algorithm_changed') is not False or \
       any(source_audit.get(name) is not False for name in (
           'dataset_changed','query_protocol_changed','memory_policy_changed','cpu_protocol_changed')):
        raise RuntimeError('QMF implementation provenance invalid')

def verify_source():
    expected=s.read_json(s.OUT/'00_environment/production_source_before.json')
    current=source_manifest()
    if not production_source_verified(expected,current):
        raise RuntimeError('UNVERIFIED_PRODUCTION_QMF_SOURCE_CHANGED')
    stage=s.read_json(s.BASE/'expected/stage_a_verification.json')
    if stage['verified']!=37 or stage['failed']!=0: raise RuntimeError('Stage-A attestation invalid')
    if s.sha(s.BASE/'config/r4.pt')!='0d10709b1440549e2aec605b1b68754aff0e8fbb9d793e0f31a64df9da213b5d':
        raise RuntimeError('Stage-A packaged R4 SHA mismatch')
    import yaml
    cfg=yaml.safe_load((s.BASE/'config/qmf_frozen_config.yaml').read_text())
    if cfg['top_k']!=4 or cfg['lookahead_depth']!=3 or cfg['maximum_configurations']!=16384:
        raise RuntimeError('Frozen QMF config mismatch')
    s.atomic_json(s.OUT/'00_environment/production_source_after.json',current)

def query_gate(row):
    d=row['dataset_id']; folder=s.OUT/'02_queries'/d; path=folder/(d+'_queries.csv')
    manifest=s.read_json(folder/'query_manifest.json')
    if s.sha(path)!=manifest['query_sha256']: raise RuntimeError('Frozen query SHA mismatch')
    with path.open() as f: records=list(csv.DictReader(f))
    if len(records)!=QUERY_COUNTS['total'] or \
       len({r['query_id'] for r in records})!=QUERY_COUNTS['total']:
        raise RuntimeError('Paper query cardinality mismatch')
    for split in ['train','validation','correctness','warmup','performance']:
        subset=[r for r in records if r['split']==split]
        if len(subset)!=PROTOCOL[split]: raise RuntimeError('Paper split cardinality mismatch')
        with (folder/(split+'_normalized.csv')).open() as f: normalized=list(csv.DictReader(f))
        if [r['query_id'] for r in normalized]!=[r['query_id'] for r in subset]: raise RuntimeError('Normalized query order mismatch')
    for group in ['S1','S2','S3']:
        if sum(r['split']=='performance' and r['selectivity_group']==group for r in records) \
           !=PERFORMANCE_QUERIES_PER_GROUP:
            raise RuntimeError('Paper selectivity cardinality mismatch')
    return records

def initialize():
    s.output_dirs(); o.COMMON.mkdir(exist_ok=True); o.ACTIVE.mkdir(exist_ok=True)
    old_stopped(); verify_source()
    frozen_code=s.OUT/'00_environment/paper_source_freeze.json'
    if not frozen_code.exists() or not control_source_verified(s.read_json(frozen_code)):
        raise RuntimeError('Paper source differs from tested preregistration')
    verify_protocol()  # Original protocol.json remains historical evidence, not overwritten.
    source=s.OUT/'00_environment/production_source_before.json'
    if not source.exists(): s.atomic_json(source,source_manifest())
    inventory=dataset_inventory()
    if [r['dataset_id'] for r in inventory]!=DATASETS: raise RuntimeError('Four full datasets required')
    for i,row in enumerate(inventory):
        if row['record_count']!=POINTS[i] or row['sha256']!=RAW_SHA[i]: raise RuntimeError('Dataset manifest mismatch')
        path=Path(row['source_path'])
        o.update(dataset=row['dataset_id'],method='shared',phase='raw_sha_verification')
        if path.stat().st_size!=row['raw_bytes'] or s.sha(path)!=RAW_SHA[i]: raise RuntimeError('RAW_SOURCE_MISMATCH')
        row['mtime_ns']=path.stat().st_mtime_ns
        s.atomic_json(s.OUT/'01_dataset_inventory'/(row['dataset_id']+'.json'),row)
    s.atomic_json(s.RUN/'inventory.json',inventory)
    s.atomic_csv(s.OUT/'01_dataset_inventory/frozen_dataset_manifest.csv',inventory)
    # Freeze all four small query workloads before any new method result exists.
    for row in inventory:
        d=row['dataset_id']; folder=s.OUT/'02_queries'/d
        if not (folder/'query_manifest.json').exists():
            if list((s.OUT/'checkpoints'/d).glob('*_build*.done')): raise RuntimeError('Refuse query regeneration after build')
            worker.queries(d)
        query_gate(row)
        s.done(d,'queries',s.read_json(folder/'query_manifest.json'),list(folder.glob('*.csv')))
    s.atomic_json(s.OUT/'00_environment/preparation_gate.json',{'old_heavy_campaign_active':False,'goal_guardian_active':False,
        'query_counts':[QUERY_COUNTS['total']]*len(DATASETS),
        'reference_denominator':QUERY_COUNTS['correctness'],
        'stage_a':'PASS attestation + R4 hash','QMF_ALGORITHM_CHANGED':False})
    return inventory

def normalized(row):
    d=row['dataset_id']; cache=s.ROOT/'data_cache/full'/d
    point=cache/'points_normalized.csv'; manifest=cache/'normalized_manifest.json'
    work=o.ACTIVE/d; work.mkdir(parents=True,exist_ok=True)
    o.update(dataset=d,method='shared',phase='normalized_sha_verification')
    if not point.exists():
        if d==DATASETS[0]: raise RuntimeError('GeoLife persistent normalized artifact missing; reconversion forbidden')
        o.update(phase='normalize')
        o.monitor(o.worker('normalize',d),d+'_normalize',14400)
        meta=s.read_json(work/'normalized.json'); cache.mkdir(parents=True,exist_ok=True)
        shutil.move(str(work/'points_normalized.csv'),point)
        meta.update(path=str(point),automatic_cleanup_allowed=False)
        s.atomic_json(manifest,meta)
    meta=s.read_json(manifest)
    if meta['points']!=row['record_count'] or point.stat().st_size!=meta['bytes'] or s.sha(point)!=meta['sha256']:
        raise RuntimeError('Normalized SHA/point/size mismatch')
    if d==DATASETS[0] and (meta['sha256']!=GEO_SHA or meta['bytes']!=8899322212): raise RuntimeError('GeoLife normalized SHA mismatch')
    link=work/'points_normalized.csv'
    if not link.exists(): link.symlink_to(point)
    s.atomic_json(work/'normalized.json',meta)
    s.atomic_json(s.OUT/'01_dataset_inventory'/(d+'_normalized.json'),meta)
    s.done(d,'normalize',meta,[manifest,point])

def infrastructure():
    o.cgroup_policy.configure(o.SLICE)
    # Existing current links pin immutable compiled dependencies. Cleanup preserves
    # their targets; missing binaries require explicit recovery, never old result reuse.
    for name in ['build','baselines','extension','learnedbench-patched','repro-source']:
        target=o.COMMON/name
        if not target.exists(): raise RuntimeError('Current compiled dependency missing: '+str(target))
    binary=s.RUN/'qmf_postgres_full'
    if not s.valid('_global','compiled'):
        o.update(phase='compile_harness')
        o.monitor(['g++','-O3','-DNDEBUG','-march=native','-std=c++17','-I/usr/include/postgresql',
            Path(__file__).with_name('postgres_full.cpp'),'-lpq','-pthread','-o',binary],'compile_harness',600)
        s.done('_global','compiled',files=[binary,o.COMMON/'build/bin/qmap_build_index'])
    o.setup()
    parent=o.cgroup_policy.snapshot(o.SLICE)
    o.cgroup_policy.validate(parent,[o.cgroup_policy.snapshot(o.PGUNIT)])
    s.atomic_json(s.OUT/'00_environment/pre_run_validation.json',{
        **PROTOCOL,'old_heavy_campaign_active':False,'goal_guardian_active':False,
        'normalized_geolife_sha':'PASS','normalized_sha256':GEO_SHA,
        'effective_parent':parent,'postgres_child':o.cgroup_policy.snapshot(o.PGUNIT),
        'worker_child_evidence':'00_environment/compile_harness_cgroup.json and every method phase cgroup record',
        'postgres_version':o.scalar('SHOW server_version'),'postgis_version':o.scalar('SELECT PostGIS_Lib_Version()')})

def persist(row,index):
    o.update(phase='reporting')
    while True:
        try:
            files=report.dataset_report(row,index)
            s.done(row['dataset_id'],'results_persisted',{'printed':True,'method_count':8},files)
            return
        except Exception as e:
            s.atomic_json(s.OUT/'09_reports/reporting_error.json',{'status':'REPORTING_FAILED','error':repr(e),'at':time.time()})
            # Reports are retried without rebuilding or altering benchmark checkpoints.
            time.sleep(10)

def aggregate_safely(inventory):
    try: report.aggregate(inventory)
    except Exception as e:
        s.atomic_json(s.OUT/'09_reports/aggregate_error.json',{'status':'REPORTING_FAILED','error':repr(e),'at':time.time()})

def cleanup(row):
    d=row['dataset_id']
    if not s.valid(d,'results_persisted'): raise RuntimeError('Results must be persisted before cleanup')
    if not report.completion(d)['scientifically_complete']:
        raise RuntimeError('Dataset scientifically incomplete; preserve database and failed method runtime for repair')
    o.update(phase='cleanup')
    if active(o.PGUNIT):
        o.sql('DROP VIEW IF EXISTS evaluation; DROP TABLE IF EXISTS points CASCADE;',d+'_drop',1800)
    o.ctl('stop',o.PGUNIT)
    for _,runtime in s.METHODS: o.cleanup_method(d,runtime)
    group=o.cgroup_policy.snapshot(o.SLICE)
    if active(o.PGUNIT): raise RuntimeError('PostgreSQL remains active')
    root=Path('/sys/fs/cgroup')/group['path'].lstrip('/')
    if root.exists() and any(p.read_text().strip() for p in root.rglob('cgroup.procs')):
        raise RuntimeError('Dataset worker/cgroup remains active')
    if group['kernel'].get('memory.swap.current',0)!=0: raise RuntimeError('Experiment swap nonzero')
    work=o.ACTIVE/d
    if work.exists(): shutil.rmtree(work)  # Persistent cache lies outside this exact dataset runtime.
    o.ctl('stop',o.SLICE)
    s.done(d,'cleanup',{'active_memory_released':True,'postgres_processes':0,'worker_processes':0,'swap':0,'persistent_normalized_preserved':True})
    s.done(d,'dataset_complete',{'method_count':8,'scientifically_complete':True})

def foreground():
    s.RUN.mkdir(parents=True,exist_ok=True)
    lock=(s.RUN/'campaign.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def interrupted(signum,frame): raise KeyboardInterrupt('Signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    try:
        o.update(status='RUNNING',phase='preflight')
        inventory=initialize()
        if not report.completion(DATASETS[0])['scientifically_complete']: normalized(inventory[0])
        infrastructure()
        for index,row in enumerate(inventory):
            d=row['dataset_id']
            if s.valid(d,'dataset_complete',False) and report.completion(d)['scientifically_complete']: continue
            if index and not report.completion(DATASETS[index-1])['scientifically_complete']:
                raise RuntimeError('Previous dataset scientifically incomplete; forward advancement forbidden')
            if index and not s.valid(DATASETS[index-1],'cleanup',False): raise RuntimeError('Previous dataset cleanup incomplete')
            o.cgroup_policy.configure(o.SLICE)
            o.update(dataset=d,method='shared',phase='preparation')
            if not s.valid(d,'results_persisted'):
                verify_source(); query_gate(row)
                if index: normalized(row)
                try:
                    o.prepare_dataset(row)
                    for display,runtime in s.METHODS:
                        verify_source(); query_gate(row)
                        o.run_method(row,display,runtime)
                except o.Blocked as e:
                    for display,runtime in s.METHODS:
                        if not s.marker(d,runtime+'_method').exists():
                            s.done(d,runtime+'_method',{'Method':display,**{m:None for m in s.METRICS},
                                'Correctness':'NOT_RUN','Status':e.status,'reason':'Shared preparation: '+str(e),'BUILD_REPETITIONS':1})
                persist(row,index)
            cleanup(row)
            aggregate_safely(inventory)
        verify_source(); report.aggregate(inventory)
        o.update(status='COMPLETE',phase='COMPLETE')
        s.atomic_json(s.RUN/'exit_status.json',{'exit_code':0,'at':time.time()})
    except BaseException as e:
        o.update(status='INTERRUPTED',error=repr(e))
        s.atomic_json(s.RUN/'exit_status.json',{'exit_code':1,'at':time.time(),'error':repr(e)})
        raise

def status():
    state=s.read_json(o.STATE) if o.STATE.exists() else {}
    repair_state=s.RUN/'geolife_repair/status.json'
    hold=s.OUT/'debug/GEOLIFE_REPAIR_HOLD.json'
    if repair_state.exists() and hold.exists() and s.read_json(hold).get('active'):
        state=s.read_json(repair_state)
        print('GeoLife repair service = '+o.props(REPAIR_UNIT).get('ActiveState','inactive'))
    print('Campaign service = '+o.props(UNIT).get('ActiveState','not started'))
    for k in ['dataset','method','phase','elapsed_seconds','error']: print(k+' = '+str(state.get(k,'N/A')))
    d=state.get('dataset'); runtime=dict(s.METHODS).get(state.get('method'))
    count=0; repetition=0; query=0
    if d and runtime:
        corr=s.OUT/'04_correctness'/d/(runtime+'.csv')
        if corr.exists():
            with corr.open() as f: count=max(0,sum(line.endswith('\n') for line in f)-1)
        folder=s.OUT/'05_performance'/d/runtime
        for rep in range(PERFORMANCE_REPETITIONS):
            for suffix in ['.csv','.csv.part']:
                path=folder/f'latency.r{rep}{suffix}'
                if path.exists():
                    repetition=rep+1
                    with path.open() as f: query=max(0,sum(line.endswith('\n') for line in f)-1)
        if s.marker(d,runtime+'_method').exists() and \
           s.read_json(s.marker(d,runtime+'_method'))['payload']['Status']=='PASS':
            repetition=PERFORMANCE_REPETITIONS; query=QUERY_COUNTS['performance']
    print(f"Correctness = {count} / {QUERY_COUNTS['correctness']}\n"
          f"Timing = repetition {repetition} / {PERFORMANCE_REPETITIONS}; "
          f"query {query} / {QUERY_COUNTS['performance']}")
    group=o.cgroup_policy.snapshot(o.SLICE)['kernel']
    print('Memory current = '+str(group.get('memory.current','N/A'))+' bytes')
    print('Memory peak = '+str(group.get('memory.peak','N/A'))+' bytes')
    print('Swap = '+str(group.get('memory.swap.current',0))+' bytes')
    states=[report.completion(d) for d in DATASETS]
    print('Attempted datasets = '+str(sum(v['attempted'] for v in states))+' / 4')
    print('Scientifically complete datasets = '+str(sum(v['scientifically_complete'] for v in states))+' / 4')
    for name,v in zip(report.NAMES,states):
        print(f'{name}: methods attempted = {v["methods_attempted"]}/8; methods valid = {v["methods_valid"]}/8; scientifically complete = {"YES" if v["scientifically_complete"] else "NO"}')
    for i,d in enumerate(DATASETS):
        p=s.OUT/report.SHORT[i]/(report.SHORT[i].upper()+'_8_METHODS_7_METRICS.md')
        if s.marker(d,'results_persisted').exists() and p.exists(): print(p.read_text())

def start():
    if active(UNIT): status(); return
    hold=s.OUT/'debug/GEOLIFE_REPAIR_HOLD.json'
    if hold.exists() and s.read_json(hold).get('active'):
        status(); print('Forward campaign paused for GeoLife repair; use the dedicated repair service.'); return
    old_stopped(); s.output_dirs()
    import xml.etree.ElementTree as ET
    tests=s.OUT/'paper_protocol_tests.xml'
    tree=ET.parse(tests)
    suites=list(tree.iter('testsuite'))
    if not suites or sum(int(v.get('tests',0)) for v in suites)<24 or any(int(v.get(k,0)) for v in suites for k in ['failures','errors']):
        raise RuntimeError('Paper regression tests must pass before launch')
    frozen=s.OUT/'00_environment/paper_source_freeze.json'
    current={p.name:s.sha(p) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.cpp')}
    if frozen.exists() and not control_source_verified(s.read_json(frozen)): raise RuntimeError('Paper source freeze changed; validate affected scope before resume')
    if not frozen.exists(): s.atomic_json(frozen,current)
    # A surviving phase worker is never killed or duplicated by --resume.
    workers=subprocess.check_output(['systemctl','--user','list-units','qmf-paper-worker-*','--state=active','--no-legend'],text=True)
    if workers.strip(): raise RuntimeError('Paper phase worker still active; allow it to finish before resume')
    o.ctl('reset-failed',UNIT)
    subprocess.run(['systemd-run','--user','--unit',UNIT,'--property=TimeoutStopSec=60',
        '--property=StandardOutput=append:'+str(s.OUT/'campaign.log'),
        '--property=StandardError=append:'+str(s.OUT/'campaign.log'),
        '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=OPENBLAS_NUM_THREADS=1','--setenv=OMP_NUM_THREADS=1',
        sys.executable,'-B',str(Path(__file__).resolve()),'--foreground'],check=True)

def repair(dataset, method=None, dry_run=False):
    """Dispatch the current checkpoint-safe repair engine through the main CLI."""
    aliases={value.lower():key for key,value,_,_ in DATASET_SPECS}
    aliases.update({key.lower():key for key in DATASETS})
    selected=aliases.get(str(dataset).lower())
    if selected is None:
        raise ValueError('Unknown paper dataset: '+str(dataset))
    if selected!=DATASETS[0]:
        raise RuntimeError('Targeted repair is currently required only for GeoLife; use --resume for the sequential campaign')
    import repair_geolife
    runtime=None
    if method:
        method_map={name.lower():value for name,value in s.METHODS}
        method_map.update({value.lower():value for _,value in s.METHODS})
        runtime=method_map.get(method.lower())
        if runtime is None: raise ValueError('Unknown paper method: '+method)
        if runtime not in repair_geolife.ORDER:
            raise ValueError('Method is already scientifically valid or outside the GeoLife repair queue: '+method)
    methods=[runtime] if runtime else list(repair_geolife.retry_queue())
    plan={'action':'repair','dataset':selected,'methods':methods,'dry_run':bool(dry_run),
          'formal_entrypoint':'scripts/run_paper_benchmark.sh','will_start_service':not dry_run}
    print(json.dumps(plan,indent=2))
    if not dry_run: repair_geolife.start(methods)

def dry_run_plan():
    print(json.dumps({'action':'campaign','datasets':list(DATASETS),
        'methods':[name for name,_ in s.METHODS],'protocol':PROTOCOL,
        'will_start_service':False},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); group=parser.add_mutually_exclusive_group(required=False)
    for flag in ['start','resume','status','foreground']: group.add_argument('--'+flag,action='store_true')
    group.add_argument('--repair',metavar='DATASET')
    parser.add_argument('--method',metavar='METHOD')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if args.method and not args.repair: parser.error('--method requires --repair DATASET')
    if args.status: status()
    elif args.foreground: foreground()
    elif args.repair: repair(args.repair,args.method,args.dry_run)
    elif args.dry_run: dry_run_plan()
    elif args.start or args.resume: start()
    else: parser.error('choose --start, --resume, --status, --repair DATASET, or --dry-run')
