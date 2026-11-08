from pathlib import Path
import csv, hashlib, json, subprocess, shutil, sys, time, os
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
FLOOD=Path('/media/lingyaqi/Lenovo F510/Mthod/Flood')
KIT=FLOOD/'FLOOD_RECOVERY_V2/QMF_Baseline_7Method_Parallel_Kit_20260930'
ORIGINAL_COMMON=Path('/var/tmp/qmf-three-baselines/7da901c84be5/flood/common')
COMMON=Path(os.environ.get('FLOOD_COMPLETION_COMMON',str(ORIGINAL_COMMON)))
VALIDATOR=Path(os.environ.get('FLOOD_COMPLETION_VALIDATOR','/var/tmp/qmf-three-baselines/7da901c84be5/flood/validation/validate_v2'))
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def initial():
    for name in ['FLOOD_SKEWED_MEMORY_ROOT_CAUSE.md','FLOOD_COMPLETE_FINAL_REPORT.md','FLOOD_RECOVERY_VERSION_REPORT.md']:
        shutil.copyfile(FLOOD/name,ROOT/'02_diagnosis'/name)
    cfg=json.loads((KIT/'protocol/EXPERIMENT_CONFIG_LOCK.json').read_text())
    write(ROOT/'01_environment/frozen_protocol.json',cfg)
    write(ROOT/'01_environment/protected_results.json',{str(p):sha(p) for p in [*FLOOD.glob('FLOOD_*'),*KIT.glob('baseline_runs/flood/*/attempt-*/RESULT.csv')] if p.is_file()})
    v=json.loads((FLOOD/'FLOOD_RECOVERY_V2/evidence/VERSION.json').read_text())
    source_root=KIT/'implementations/shared/repro'
    source_files={p.relative_to(source_root).as_posix():sha(p) for p in sorted(source_root.rglob('*')) if p.is_file()}
    assert source_files==v['source_files'],'Flood-V2 source differs from historical validated version'
    write(ROOT/'01_environment/source_manifest.json',dict(source_root=str(source_root),files=source_files,NewSourceSHA=v['NewSourceSHA'],MethodVersion=v['MethodVersion']))
    binaries={str(COMMON/Path(p).relative_to(ORIGINAL_COMMON)):{'expected':h,'actual':sha(COMMON/Path(p).relative_to(ORIGINAL_COMMON))} for p,h in v['NewBinarySHA'].items()}
    assert all(r['expected']==r['actual'] for r in binaries.values())
    write(ROOT/'01_environment/binaries.json',binaries)
    validator=VALIDATOR
    assert sha(validator)=='648b5f78cfd58bb67e39fab17ee8e308d1f1181904f322e1d4bd50f13f15f644'
    write(ROOT/'01_environment/validator_binary.json',dict(path=str(validator),sha256=sha(validator)))
    for name,cmd in {'free':['free','-h'],'df':['df','-h'],'lsblk':['lsblk','-f'],'ulimit':['bash','-c','ulimit -a'],'cpu':['lscpu'],'kernel':['journalctl','-k','--no-pager'],'dmesg':['dmesg','--ctime'],'compiler':['g++','--version'],'python':[sys.executable,'-c','import sys,numpy,pandas; print(sys.version); print(numpy.__version__,pandas.__version__)'],'git':['git','-C',str(FLOOD/'FLOOD_RECOVERY_V2'),'rev-parse','HEAD']}.items():
        r=subprocess.run(cmd,capture_output=True,text=True)
        (ROOT/'01_environment'/f'{name}.txt').write_text(r.stdout+r.stderr+f'\nreturncode={r.returncode}\n')
    q=KIT/'queries/frozen_queries/skewed_2d'
    shutil.copytree(q,ROOT/'03_validation/frozen_queries',dirs_exist_ok=True)
    query_files={p.name:sha(p) for p in q.iterdir() if p.is_file()}
    train=list(csv.DictReader((q/'train_normalized.csv').open()))
    x=sum(float(r['xmax'])-float(r['xmin']) for r in train);y=sum(float(r['ymax'])-float(r['ymin']) for r in train)
    write(ROOT/'03_validation/query_verification.json',dict(files=query_files,training_queries=len(train),sum_x_width=x,sum_y_width=y,expected_swap=x<y))
    source=Path(cfg['datasets'][-1]['normalized_path'])
    for n in (16384,1000000):
        sample=ROOT/'03_validation'/f'diagnostic_{n}.csv'
        with source.open() as f,sample.open('w') as out:
            out.write(f.readline())
            for _ in range(n):out.write(next(f))
    print('INITIAL_AUDIT_PASS',flush=True)
def full():
    import pandas as pd,numpy as np
    cfg=json.loads((ROOT/'01_environment/frozen_protocol.json').read_text());d=cfg['datasets'][-1]
    records=[]
    for field,expected in [('source_path','RawSHA256'),('normalized_path','NormalizedSHA256')]:
        p=Path(d[field]);start=time.monotonic();actual=sha(p)
        assert actual==d[expected],(str(p),actual)
        n=0;low=None;high=None
        for frame in pd.read_csv(p,chunksize=250000,float_precision='round_trip'):
            a=frame.iloc[:,-2:].to_numpy(dtype=np.float64)
            assert np.isfinite(a).all()
            if field=='normalized_path':assert np.array_equal(frame.iloc[:,0].to_numpy(),np.arange(n,n+len(frame)))
            lo=a.min(axis=0);hi=a.max(axis=0)
            low=lo if low is None else np.minimum(low,lo);high=hi if high is None else np.maximum(high,hi)
            n+=len(frame)
        assert n==204986702
        records.append(dict(path=str(p),sha256=actual,bytes=p.stat().st_size,points=n,min=low.tolist(),max=high.tolist(),validation_seconds=time.monotonic()-start))
        write(ROOT/'03_validation/full_input_validation.json',records)
        print('FULL_INPUT_PASS',str(p),n,flush=True)
if __name__=='__main__':
    (initial if sys.argv[1]=='initial' else full)()
