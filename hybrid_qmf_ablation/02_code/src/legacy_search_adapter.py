"""Original full-table methods; explicitly charge complete preparation."""
from . import bootstrap
import math,time,numpy as np
from qmapli.wg_qmf.configuration import enumerate_joint_configurations
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs
from qmapli.wg_qmf.search import uniform_qmf,_classical_result,beam_search
from .conditional_state import BL,BP

def run(points,queries,scorer,method,seed=11,budget=None):
    started=time.perf_counter()
    u=enumerate_joint_configurations(points,queries,scorer,depth=3,top_k=4,minimum_child_count=256,maximum_configurations=16384)
    expanded=time.perf_counter()
    table=evaluate_subtree_costs(u.configurations,queries,beta_leaf=BL,beta_point=BP)
    evaluated=time.perf_counter();b=min(u.size,math.ceil(2*math.sqrt(u.size))) if budget is None else min(u.size,int(budget))
    if method=='Legacy-QMF':result=uniform_qmf(table.costs,budget=b,seed=seed)
    elif method=='Legacy-Random':result=_classical_result('Original Random',table.costs,np.random.default_rng(seed).choice(u.size,size=b,replace=False),b)
    elif method=='Legacy-Beam':result=beam_search(table.costs,u,width=b,budget=b)
    else:raise ValueError(method)
    return result,u.configurations[result.selected_index],dict(configuration_generation=expanded-started,cost_table=evaluated-expanded,selection=time.perf_counter()-evaluated,total=time.perf_counter()-started,N=u.size,all_costs_precomputed=True)
