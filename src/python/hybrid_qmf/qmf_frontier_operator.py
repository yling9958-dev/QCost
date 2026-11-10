"""Classical QMF-inspired amplification of a VISIBLE PROXY threshold set.
No unseen complete configuration costs, amplitude state vector or QPU.
"""
import math
import numpy as np
def visible_distribution(estimates,threshold):
    s=np.asarray(estimates,dtype=float);n=len(s)
    if n==0:raise ValueError('empty frontier')
    # Same visible marking rule is supplied to classical Threshold.
    cutoff=min(float(threshold),float(np.quantile(s,.25)))
    marked=s<cutoff;p=float(marked.mean());prob=np.full(n,1/n);j=0
    if 0<p<1:
        theta=math.asin(math.sqrt(p));j=max(0,min(8,int(round(math.pi/(4*theta)-.5))))
        amplified=math.sin((2*j+1)*theta)**2
        prob[marked]=amplified/marked.sum();prob[~marked]=(1-amplified)/(~marked).sum()
    else:amplified=p
    prob=np.maximum(prob,0);prob/=prob.sum()
    return prob,dict(threshold=float(threshold),proxy_cutoff=cutoff,marked=marked.tolist(),marked_mass=p,j=j,amplified_mass=amplified)
def select(estimates,threshold,rng):
    p,info=visible_distribution(estimates,threshold);i=int(rng.choice(len(p),p=p));info['probabilities']=p.tolist();return i,info
