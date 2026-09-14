"""One post-exit handoff after a scientifically successful GeoLife repair."""
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET
import support as s
import orchestrate as o
import run
import report
import repair_geolife as repair


def eligible(state,completion):
    return state.get('status')=='COMPLETE' and completion.get('scientifically_complete') is True


def finish():
    hold=repair.DEBUG/'GEOLIFE_REPAIR_HOLD.json'
    if not hold.exists() or not s.read_json(hold).get('active'): return
    state=s.read_json(repair.WORK/'status.json')
    complete=report.completion(repair.D)
    if not eligible(state,complete):
        s.atomic_json(repair.DEBUG/'forward_handoff.json',{'at':time.time(),'status':'HELD',**complete,
            'reason':'Repair must finish successfully with eight scientifically valid methods'})
        return
    if os.environ.get('SERVICE_RESULT','success')!='success':
        raise RuntimeError('Repair service did not exit successfully; forward campaign remains held')
    run.verify_source(); repair.verify_protected()
    if not s.valid(repair.D,'results_persisted'): raise RuntimeError('Final GeoLife result files are not valid')
    audited=s.read_json(repair.DEBUG/'repair_source_verification.json')['current_source_manifest']
    current={p.name:s.sha(p) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.cpp')}
    if not run.control_source_verified(audited): raise RuntimeError('Repair control source differs from tested audit')
    suites=list(ET.parse(repair.DEBUG/'repair_tests.xml').iter('testsuite'))
    if not suites or any(int(v.get(k,0)) for v in suites for k in ('errors','failures')):
        raise RuntimeError('Repair regression tests must pass')
    parent=o.cgroup_policy.snapshot(o.SLICE)
    root=Path('/sys/fs/cgroup')/parent['path'].lstrip('/')
    if not parent['path'] or any(p.read_text().strip() for p in root.rglob('cgroup.procs')):
        raise RuntimeError('GeoLife experiment processes remain active')
    if parent['kernel'].get('memory.swap.current')!=0: raise RuntimeError('Experiment swap is nonzero')
    if run.active(o.PGUNIT): raise RuntimeError('GeoLife PostgreSQL remains active')
    # Keep the restored SQL cluster on disk; it no longer occupies active memory.
    o.ctl('stop',o.SLICE,check=True)
    s.done(repair.D,'cleanup',{'active_memory_released':True,'postgres_processes':0,
        'worker_processes':0,'swap':0,'persistent_normalized_preserved':True,
        'restored_sql_cluster_preserved':str(repair.WORK/'common/pg_data')})
    s.done(repair.D,'dataset_complete',complete)
    freeze=s.OUT/'00_environment/paper_source_freeze.json'
    repair.archive(freeze,repair.DEBUG/'paper_source_freeze_before_control_repair.json')
    s.atomic_json(freeze,current)
    s.atomic_json(hold,{**s.read_json(hold),'active':False,'released_at':time.time(),'release_reason':'GeoLife eight valid methods and active cleanup verified'})
    try:
        run.start()
    except Exception:
        s.atomic_json(hold,{**s.read_json(hold),'active':True,'reason':'Forward handoff failed; completed work preserved'})
        raise
    s.atomic_json(repair.DEBUG/'forward_handoff.json',{'at':time.time(),'status':'GOWALLA_RESUMED',**complete,
        'preserved_timing_repetitions':'Gowalla PostGIS repetitions 1–3; resume unfinished work only'})


if __name__=='__main__':
    try: finish()
    except Exception as e:
        s.atomic_json(repair.DEBUG/'forward_handoff.json',{'at':time.time(),'status':'HANDOFF_FAILED','error':repr(e)})
        raise
