"""QMF index construction and range-query support."""

from __future__ import annotations

import numpy as np

def cached_work_metrics(configurations, queries):
    if not configurations:
        raise ValueError('empty configuration universe')
    q=len(queries)
    # Above this bound, the reference float64 accumulation need not be exact.
    if any(sum(leaf.point_count for leaf in plan.leaves)*q > 2**53 for plan in configurations):
        return None
    hits={}
    partitions={}

    def hit_array(bounds):
        if bounds not in hits:
            x0,y0,x1,y1=bounds
            hits[bounds]=(queries[:,2]>=x0)&(queries[:,0]<=x1)&(queries[:,3]>=y0)&(queries[:,1]<=y1)
        return hits[bounds]

    leaf_counts={}
    for plan in configurations:
        for leaf in plan.leaves:
            if leaf.bounds not in leaf_counts:
                leaf_counts[leaf.bounds]=int(np.count_nonzero(hit_array(leaf.bounds)))
        for partition in plan.partitions:
            key=(partition.left_bounds,partition.right_bounds)
            if key not in partitions:
                partitions[key]=int(np.count_nonzero(hit_array(key[0])&hit_array(key[1])))
    refined=np.asarray([sum(leaf_counts[leaf.bounds]*leaf.point_count for leaf in plan.leaves)
                        for plan in configurations],dtype=np.float64)/q
    visited=np.asarray([sum(leaf_counts[leaf.bounds] for leaf in plan.leaves)
                        for plan in configurations],dtype=np.float64)/q
    cross=np.asarray([sum(partitions[(p.left_bounds,p.right_bounds)] for p in plan.partitions)
                      for plan in configurations],dtype=np.float64)/q
    return refined,visited,cross
