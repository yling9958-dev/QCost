"""Bounded-memory dataset preparation and wrappers around the immutable baseline."""
import argparse
import csv
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from support import BASE, ROOT, RUN, OUT, SEED, atomic_json, atomic_csv, read_json, sha
from paper_protocol import PERFORMANCE_QUERIES_PER_GROUP, QUERY_COUNTS

def audit():
    import numpy as np
    import pandas as pd
    files=sorted((ROOT/'dataest').rglob('*'))
    files=[p for p in files if p.is_file()]
    if len(files)!=4 or any(p.suffix.lower()!='.csv' for p in files):
        raise ValueError('Expected exactly four actual CSV datasets; inspect inventory before proceeding')
    rows=[]
    for p in files:
        key=p.stem
        saved=OUT/'01_dataset_inventory'/f'{key}.json'
        st=p.stat()
        if saved.exists():
            row=read_json(saved)
            if row['raw_bytes']==st.st_size and row['mtime_ns']==st.st_mtime_ns and row['sha256']==sha(p):
                rows.append(row); continue
            raise ValueError('Frozen source changed: '+str(p))
        started=time.time(); count=0; lo=np.full(2,np.inf); hi=-lo
        digest=sha(p)
        for frame in pd.read_csv(p,chunksize=1000000,dtype=np.float64,float_precision='round_trip'):
            if list(frame.columns)!=['x','y']: raise ValueError(f'Unsupported coordinates: {p}')
            values=frame.to_numpy()
            if not np.isfinite(values).all(): raise ValueError(f'Nonfinite coordinate in {p}')
            count+=len(frame); lo=np.minimum(lo,values.min(axis=0)); hi=np.maximum(hi,values.max(axis=0))
        if p.stat().st_size!=st.st_size or p.stat().st_mtime_ns!=st.st_mtime_ns:
            raise ValueError('Input changed during audit')
        if count>=2**32: raise ValueError('Frozen native adapters have uint32 IDs; implementation limit')
        names={'geolife_2d_4p2G':'GeoLife','gowalla_2d_4p2G':'Gowalla',
               'nyc_taxi_2d_4p2G':'NYC taxi','skewed_2d':'Skewed 2D'}
        semantics='generic x/y; provenance unverified' if key=='skewed_2d' else 'longitude/latitude inferred from name and coordinate range; provenance unverified'
        row={'dataset_id':key,'dataset_name':names.get(key,key),'source_path':str(p),
             'raw_bytes':st.st_size,'raw_GiB':st.st_size/1024**3,'format':'CSV with x,y header',
             'coordinate_x':'x','coordinate_y':'y','record_count':count,'sha256':digest,
             'status':'FROZEN','mtime_ns':st.st_mtime_ns,'bounds':[*lo.tolist(),*hi.tolist()],
             'semantics':semantics,'audit_seconds':time.time()-started}
        atomic_json(saved,row); rows.append(row)
        print(f'AUDIT {key}: {count} rows, {digest}',flush=True)
    fields=['dataset_id','dataset_name','source_path','raw_bytes','raw_GiB','format',
            'coordinate_x','coordinate_y','record_count','sha256','status']
    table=[{k:r[k] for k in fields} for r in rows]
    for parent in [RUN,OUT/'01_dataset_inventory']:
        atomic_csv(parent/'dataset_inventory.csv',table,fields)
        atomic_csv(parent/'frozen_dataset_manifest.csv',table,fields)
    atomic_json(RUN/'inventory.json',rows)

def normalize(dataset):
    import numpy as np
    import pandas as pd
    row=read_json(OUT/'01_dataset_inventory'/f'{dataset}.json')
    work=RUN/'active'/dataset; work.mkdir(parents=True,exist_ok=True)
    target=work/'points_normalized.csv'; temp=target.with_suffix('.csv.part')
    low=np.array(row['bounds'][:2]); high=np.array(row['bounds'][2:]); count=0
    with temp.open('w') as f:
        f.write('id,x,y\n')
        for frame in pd.read_csv(row['source_path'],dtype=np.float64,chunksize=250000,float_precision='round_trip'):
            values=(frame.to_numpy()-low)/(high-low)
            out=pd.DataFrame({'id':np.arange(count,count+len(frame),dtype=np.int64),
                              'x':values[:,0],'y':values[:,1]})
            out.to_csv(f,header=False,index=False,float_format='%.17g',lineterminator='\n')
            count+=len(frame)
            if count%10000000==0: print(f'NORMALIZE {dataset}: {count} rows',flush=True)
        f.flush(); os.fsync(f.fileno())
    if count!=row['record_count']: raise ValueError('Full dataset row count changed')
    os.replace(temp,target)
    atomic_json(work/'normalized.json',{'dataset':dataset,'points':count,'path':str(target),
                'bytes':target.stat().st_size,'sha256':sha(target),'bounds':row['bounds'],
                'id_mapping':'zero-based source row ordinal; no filtering, deduplication or replication',
                'normalization':'float64 affine min-max; identical CSV for every native adapter'})

def queries(dataset):
    import numpy as np
    row=read_json(OUT/'01_dataset_inventory'/f'{dataset}.json')
    low=np.array(row['bounds'][:2]); high=np.array(row['bounds'][2:]); scale=high-low
    rng=np.random.default_rng(SEED)
    folder=OUT/'02_queries'/dataset; folder.mkdir(parents=True,exist_ok=True)
    all_rows=[]; norm_rows=[]
    targets=[.0001,.001,.01]
    # Use the same generator sequence and settings for each dataset, before timing.
    for split in ('train', 'validation', 'correctness', 'warmup', 'performance'):
        n=QUERY_COUNTS[split]
        local=[]
        for i in range(n):
            group=i//PERFORMANCE_QUERIES_PER_GROUP if split=='performance' else i%3
            aspect=float(rng.choice([.5,1.,2.])); area=targets[group]
            size=np.array([math.sqrt(area*aspect),math.sqrt(area/aspect)])
            center=rng.random(2)
            bounds=np.r_[np.maximum(center-size/2,0),np.minimum(center+size/2,1)]
            # Midpoints between adjacent float32 levels align exact raw and native float queries.
            f32=bounds.astype(np.float32)
            upper=np.nextafter(f32,np.float32(np.inf)).astype(np.float64)
            snapped=(f32.astype(np.float64)+upper)/2
            snapped[bounds==0]=0.; snapped[bounds==1]=1.
            raw=snapped*np.tile(scale,2)+np.tile(low,2)
            normalized=(raw-np.tile(low,2))/np.tile(scale,2)
            base={'query_id':f'{split}-{i:05d}','selectivity_group':f'S{group+1}','split':split}
            keys=['xmin','ymin','xmax','ymax']
            all_rows.append({**base,**dict(zip(keys,map(float,raw))),'expected_count':''})
            v={**base,**dict(zip(keys,map(float,normalized))),'expected_count':''}
            local.append(v); norm_rows.append(v)
        atomic_csv(folder/f'{split}_normalized.csv',local)
    target=folder/f'{dataset}_queries.csv'; atomic_csv(target,all_rows)
    atomic_json(folder/'query_manifest.json',{'dataset':dataset,'query_count':len(all_rows),
        'S1_count':PERFORMANCE_QUERIES_PER_GROUP,
        'S2_count':PERFORMANCE_QUERIES_PER_GROUP,
        'S3_count':PERFORMANCE_QUERIES_PER_GROUP,
        'correctness_count':QUERY_COUNTS['correctness'],
        'warmup_count':QUERY_COUNTS['warmup'],'train_count':QUERY_COUNTS['train'],
        'validation_count':QUERY_COUNTS['validation'],'seed':SEED,
        'query_sha256':sha(target),'target_selectivities':{'S1':.0001,'S2':.001,'S3':.01},
        'expected_count_policy':'exact ID/reference evidence only for correctness; performance result counts are observations, not independent truth',
        'selectivity_policy':'target rectangle area fraction; actual point selectivity may differ, including zero',
        'generator':'PCG64 uniform bounds centers; aspects .5/1/2; clipped edges; float32 midpoint boundaries'})

def qmf(dataset, repetition):
    sys.path.insert(0,str(BASE/'src/common/python'))
    from qmapli.wg_qmf.build_static_qw_index import main
    from qmapli.indexes.qmap_nai.index import PrefixHybridIndex
    original=PrefixHybridIndex.build
    work=RUN/'active'/dataset; build=work/'methods'/'qmap_uniform_qmf'/f'rep{repetition}'
    build.mkdir(parents=True,exist_ok=True)
    def audited(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        parents={child.node_id:node.node_id for node in self.nodes for child in node.children}
        rows=[]
        for node in sorted(self.nodes,key=lambda n:n.node_id):
            rows.append({'node_id':node.node_id,'parent_id':parents.get(node.node_id,-1),
                'axis':node.split_action.axis if node.children else -1,
                'threshold':float(node.threshold).hex() if node.children else '',
                'left_child':node.children[0].node_id if node.children else -1,
                'right_child':node.children[1].node_id if node.children else -1,
                'is_leaf':int(not node.children),'point_start':node.storage_start,'point_end':node.storage_end,
                'bbox':'|'.join(float(v).hex() for v in node.mbr)})
        atomic_csv(build/'tree_decision_manifest.csv',rows)
        return result
    PrefixHybridIndex.build=audited
    import yaml
    cfg=yaml.safe_load((BASE/'config/qmf_frozen_config.yaml').read_text())
    point_count=read_json(OUT/'01_dataset_inventory'/(dataset+'.json'))['record_count']
    args=['--mode','uniform_qmf','--r4-checkpoint',str(BASE/'config/r4.pt'),
        '--points',str(work/'points_normalized.csv'),'--point-count',str(point_count),
        '--train-queries',str(OUT/'02_queries'/dataset/'train_normalized.csv'),
        '--index',str(build/'qmap_uniform_qmf.idx'),'--metadata',str(build/'metadata.json'),
        '--context-seed',str(SEED),'--beta-leaf',str(cfg['beta_leaf']),'--beta-point',str(cfg['beta_point']),
        '--max-depth',str(cfg['max_depth']),'--min-leaf-size',str(cfg['min_leaf_size']),
        '--max-leaves',str(cfg['max_leaves']),'--budget-factor',str(cfg['budget_sqrt_factor']),
        '--memory-stage-trace',str(build/'QMF_MEMORY_STAGE_TRACE.csv')]
    main(args)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=['audit','normalize','queries','qmf'])
    parser.add_argument('dataset',nargs='?'); parser.add_argument('repetition',nargs='?',type=int,default=0)
    a=parser.parse_args()
    if a.phase=='audit': audit()
    elif a.phase=='qmf': qmf(a.dataset,a.repetition)
    else: globals()[a.phase](a.dataset)
