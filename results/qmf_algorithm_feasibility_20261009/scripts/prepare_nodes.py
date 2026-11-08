"""Read an existing normalized reproduction file and replay saved ancestor splits.
No index is rebuilt. Row order and float64 values are retained exactly.
"""
from pathlib import Path
import csv, hashlib, json, os, sys, time
RUN=Path(__file__).resolve().parents[1]
ROOT=RUN.parents[1]
PKG=ROOT/'QMF_PostGIS_100M_Repro_20260910'
sys.path.insert(0,str(PKG/'src/common/python'))
import numpy as np
from qmapli.wg_qmf.point_io import read_points
from qmapli.wg_qmf.configuration import _bounds

def sha(path):
    d=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):d.update(b)
    return d.hexdigest()

def save_json(path,obj):
    with path.open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2)

def main():
    t=time.perf_counter()
    source=Path('/var/tmp/qmf-memory-opt-100m/points_normalized.csv')
    query_source=PKG/'queries/train_normalized.csv'
    tree_source=ROOT/'results/qmf_build_audit_cleanup_20260914/equivalence/100mib/tree_decision_manifest.csv'
    metadata=json.loads((PKG/'data/normalized_hashes.json').read_text())
    observed_sha=sha(source)
    assert observed_sha==metadata['normalized_points_sha256'],(observed_sha,metadata)
    points,ids=read_points(source,expected_count=metadata['point_count'])
    with query_source.open() as f:query_rows=list(csv.DictReader(f))
    queries=np.asarray([[float(r[k]) for k in ('xmin','ymin','xmax','ymax')] for r in query_rows])
    query_ids=np.asarray([r['query_id'] for r in query_rows])
    with tree_source.open() as f:rows=list(csv.DictReader(f))
    tree={int(r['node_id']):r for r in rows}
    count=lambda r:int(r['point_end'])-int(r['point_start'])
    internal=min((r for r in rows if r['is_leaf']=='0'),key=lambda r:(count(r),int(r['node_id'])))
    leaf=min((r for r in rows if r['is_leaf']=='1'),key=lambda r:(count(r),int(r['node_id'])))
    selected=[0,int(internal['node_id']),int(leaf['node_id'])]
    manifest=[]
    for ident in selected:
        chain=[];cursor=ident
        while int(tree[cursor]['parent_id'])>=0:
            parent=int(tree[cursor]['parent_id']);row=tree[parent]
            side=0 if int(row['left_child'])==cursor else 1
            chain.append((parent,int(row['axis']),float.fromhex(row['threshold']),side))
            cursor=parent
        local=points;local_ids=ids
        for parent,axis,threshold,side in reversed(chain):
            mask=local[:,axis]<=threshold
            if side:mask=~mask
            local=local[mask];local_ids=local_ids[mask]
        bounds=_bounds(local)
        expected=tuple(float.fromhex(x) for x in tree[ident]['bbox'].split('|'))
        assert len(local)==count(tree[ident]),(ident,len(local),count(tree[ident]))
        assert bounds==expected,(ident,bounds,expected)
        qmask=(queries[:,2]>=bounds[0])&(queries[:,0]<=bounds[2])&(queries[:,3]>=bounds[1])&(queries[:,1]<=bounds[3])
        name=f'geolife100m_node{ident}'
        out=RUN/'inputs'/(name+'.npz')
        with out.open('xb') as f:np.savez(f,points=local,ids=local_ids,queries=queries[qmask],query_ids=query_ids[qmask])
        record={'name':name,'dataset':'GeoLife100MiB reproduction','saved_node_id':ident,
            'points':len(local),'queries':int(qmask.sum()),'depth_in_saved_tree':len(chain),
            'was_saved_leaf':tree[ident]['is_leaf']=='1','node_role':'root' if ident==0 else ('smallest_saved_internal' if ident==int(internal['node_id']) else 'smallest_saved_leaf'),
            'bounds_hex':[v.hex() for v in bounds],'exact_count_and_bounds_match':True,
            'input_path':str(out),'input_sha256':sha(out),
            'source_path':str(source),'source_sha256':observed_sha,
            'source_point_count':len(points),'query_path':str(query_source),'query_sha256':sha(query_source),
            'tree_path':str(tree_source),'tree_sha256':sha(tree_source),
            'ancestor_splits':[{'parent':p,'axis':a,'threshold_hex':v.hex(),'side':s} for p,a,v,s in reversed(chain)],
            'K':4,'H':3,'global_builder_would_stop_for_depth':len(chain)>=8,
            'provenance':'exact existing normalized file plus saved ancestor decisions; no index reconstruction',
            'random_seed':'not used; deterministic metadata-based node selection'}
        manifest.append(record)
        save_json(RUN/'inputs'/(name+'.json'),record)
        print(name,len(local),int(qmask.sum()),flush=True)
    # A separate, explicitly labelled infeasibility unit probe; not a recovered production node.
    local=points[:1024];bounds=_bounds(local)
    qmask=(queries[:,2]>=bounds[0])&(queries[:,0]<=bounds[2])&(queries[:,3]>=bounds[1])&(queries[:,1]<=bounds[3])
    name='geolife100m_prefix1024_boundary_probe';out=RUN/'inputs'/(name+'.npz')
    with out.open('xb') as f:np.savez(f,points=local,ids=ids[:1024],queries=queries[qmask],query_ids=query_ids[qmask])
    rec={'name':name,'dataset':'GeoLife100MiB reproduction','saved_node_id':None,'points':1024,'queries':int(qmask.sum()),
        'node_role':'derived_infeasibility_probe_NOT_SAVED_NODE','input_path':str(out),'input_sha256':sha(out),
        'source_path':str(source),'source_sha256':observed_sha,'query_path':str(query_source),'query_sha256':sha(query_source),
        'K':4,'H':3,'provenance':'first 1024 unchanged source points; tests 8*256 minimum-leaf infeasibility and small-node fallback; not evidence of production fallback causes',
        'random_seed':'not used'}
    manifest.append(rec);save_json(RUN/'inputs'/(name+'.json'),rec)
    save_json(RUN/'inputs/node_manifest.json',manifest)
    save_json(RUN/'inputs/node_availability.json',{
        'recovered_saved_nodes':selected,'full_dataset_nodes':{
        'GeoLife181M':'NOT AVAILABLE as reusable exact node snapshots/cost tables; small reproduction used',
        'Gowalla183M':'NOT AVAILABLE as reusable exact node snapshots/cost tables',
        'NYCTaxi181M':'NOT AVAILABLE as reusable exact node snapshots/cost tables; historical fallback metadata only',
        'Skewed204986702':'NOT AVAILABLE as reusable exact node snapshots/cost tables'},
        'reason':'raw full datasets and static files exist, but full scans or float32 static recovery are avoided; no large reconstruction was performed',
        'input_preparation_seconds':time.perf_counter()-t})
    print('INPUTS_READY',flush=True)

if __name__=='__main__':main()
