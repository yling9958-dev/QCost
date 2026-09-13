"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import numpy as np

from scipy.stats import skew

from ..workload_action_interaction.actions import enumerate_actions, QUANTILES

from ..workload_action_interaction.spatial_maps import CHANNEL_NAMES

def node_action_features(points, queries, actions):
    points=np.asarray(points,dtype=np.float64)
    lower=np.asarray((points[:,0].min(),points[:,1].min()))
    upper=np.asarray((points[:,0].max(),points[:,1].max()))
    if (lower==0).any() or (upper==0).any():
        lower,upper=points.min(axis=0),points.max(axis=0)
    spans=np.maximum(upper-lower,1e-12)
    correlation=np.corrcoef(points[:,0],points[:,1])[0,1]
    node=[np.log1p(len(points)),spans[0]/spans[1],*points.mean(axis=0),*points.var(axis=0),
          float(correlation) if np.isfinite(correlation) else 0.,
          float(np.nan_to_num(skew(points[:,0],bias=False))),float(np.nan_to_num(skew(points[:,1],bias=False)))]
    for axis in (0,1):
        node.extend(np.quantile(points[:,axis],(.25,.5,.75)).tolist())
    expected=[(axis,q) for axis in (0,1) for q in QUANTILES]
    all_actions=actions if [(a.axis,a.quantile) for a in actions]==expected else enumerate_actions(points)
    node.extend(abs(a.left_count-a.right_count)/len(points) for a in all_actions)
    for axis in (0,1):
        histogram,_=np.histogram(points[:,axis],bins=8,range=(lower[axis],upper[axis]))
        node.extend((histogram/max(histogram.sum(),1)).tolist())
    node=np.asarray(node,dtype=np.float32)
    normalized=np.clip((points-lower)/spans,0.,1.)
    histogram,_,_=np.histogram2d(normalized[:,0],normalized[:,1],bins=4,range=((0.,1.),(0.,1.)))
    density=(histogram.T/max(float(histogram.sum()),1.)).astype(np.float32)
    local=np.asarray(queries,dtype=np.float64).copy()
    local[:,(0,2)]=(local[:,(0,2)]-lower[0])/spans[0]
    local[:,(1,3)]=(local[:,(1,3)]-lower[1])/spans[1]
    local=np.clip(local,0.,1.)
    edges=np.linspace(0.,1.,5)
    heat=np.zeros((4,4),dtype=np.float64)
    areas=np.maximum((local[:,2]-local[:,0])*(local[:,3]-local[:,1]),1e-15)
    for row in range(4):
        for column in range(4):
            width=np.maximum(0.,np.minimum(local[:,2],edges[column+1])-np.maximum(local[:,0],edges[column]))
            height=np.maximum(0.,np.minimum(local[:,3],edges[row+1])-np.maximum(local[:,1],edges[row]))
            heat[row,column]=np.mean(width*height/areas)
    heat/=max(float(heat.sum()),1e-15)
    workload=heat.astype(np.float32)
    scalar,spatial=[],[]
    centers=(np.arange(4,dtype=np.float64)+.5)/4
    for action in actions:
        threshold=float(np.clip((action.threshold-lower[action.axis])/spans[action.axis],0.,1.))
        action_scalar=np.asarray([float(action.axis==0),float(action.axis==1),action.quantile,threshold,
                                  abs(action.left_count-action.right_count)/len(points)],dtype=np.float32)
        scalar.append(np.concatenate((node,action_scalar)))
        mask=np.empty((4,4),dtype=np.float64)
        for row in range(4):
            for column in range(4):
                index=column if action.axis==0 else row
                left=np.clip((threshold-edges[index])/(edges[index+1]-edges[index]),0.,1.)
                mask[row,column]=1.-2.*left
        mask=mask.astype(np.float32)
        one=np.exp(-.5*(np.abs(centers-threshold)/.25)**2)
        boundary=(np.repeat(one[None,:],4,axis=0) if action.axis==0 else np.repeat(one[:,None],4,axis=1)).astype(np.float32)
        maps={'P':density,'W':workload,'M':mask,'B':boundary,'I_DQ':density*workload,
              'I_QB':workload*boundary,'I_DQB':density*workload*boundary}
        spatial.append(np.stack([maps[name] for name in CHANNEL_NAMES]))
    return np.asarray(scalar,dtype=np.float32),np.asarray(spatial,dtype=np.float32)
