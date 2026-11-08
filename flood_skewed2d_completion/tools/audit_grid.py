from pathlib import Path
import json
import numpy as np
from initial_audit import ROOT,write
artifact=json.loads((ROOT/'04_build/artifact.json').read_text());path=Path(artifact['path'])
with path.open('rb') as f:
    n=int.from_bytes(f.read(8),'little');swapped=bool(int.from_bytes(f.read(1),'little'))
assert n==204986702 and path.stat().st_size==9+12*n
assert swapped==json.loads((ROOT/'03_validation/query_verification.json').read_text())['expected_swap']
points=np.memmap(path,mode='r',offset=9,dtype=[('x','<f4'),('y','<f4'),('id','<u4')],shape=(n,))
axis='y' if swapped else 'x';values=np.array(points[axis],copy=True)
positions=np.minimum(n-1,np.arange(33,dtype=np.int64)*n//32)
values.partition(positions)
boundaries=values[positions].astype(np.float64);del values
assert np.all(np.diff(boundaries)>=0)
counts=np.zeros(32,dtype=np.int64)
for first in range(0,n,250000):
    chunk=points[first:first+250000]
    assert np.array_equal(chunk['id'],np.arange(first,first+len(chunk),dtype=np.uint32))
    assert np.isfinite(chunk['x']).all() and np.isfinite(chunk['y']).all()
    v=chunk[axis];bucket=np.searchsorted(boundaries[1:-1],v,side='right')
    bucket[v<=boundaries[0]]=0;bucket[v>=boundaries[-1]]=31
    counts+=np.bincount(bucket,minlength=32)
assert int(counts.sum())==n
write(ROOT/'04_build/grid_integrity.json',dict(points=n,swap=swapped,grid_axis=axis,grid_boundaries=boundaries.tolist(),bucket_counts=counts.tolist(),sum_bucket_counts=int(counts.sum()),point_ids_exact_source_ordinals=True,finite_float32_coordinates=True,method='Independent reconstruction from original point archive using the unchanged Flood get_dim_idx rule; outside all formal timers'))
print('FULL_GRID_AND_ARCHIVE_INTEGRITY_PASS',n)
