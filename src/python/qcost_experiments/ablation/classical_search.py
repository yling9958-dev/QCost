import numpy as np
from .qmf_frontier_operator import visible_distribution
def choose(method,estimates,threshold,rng):
    values=np.asarray(estimates,float)
    if method=='random':return int(rng.integers(len(values))),{'strategy':'uniform'}
    if method=='bestfirst':return int(np.argmin(values)),{'strategy':'minimum_visible_proxy'}
    if method=='threshold':
        _,info=visible_distribution(values,threshold);ix=np.flatnonzero(info['marked'])
        if not len(ix):ix=np.arange(len(values))
        return int(rng.choice(ix)),dict(info,strategy='uniform_visible_threshold')
    raise ValueError(method)
