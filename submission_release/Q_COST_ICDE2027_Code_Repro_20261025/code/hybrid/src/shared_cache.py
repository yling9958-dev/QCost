"""Cold per-run caches. Progress and a proven optimum are distinct."""
from dataclasses import dataclass,field
import sys
@dataclass
class CacheEntry:
    state_id:str
    remaining_h:int
    value:float|None=None
    exact:bool=False
    plan:object=None
    dependencies:tuple=()
    status:str='UNSOLVED'
class SharedCache:
    def __init__(self,enabled=True,state_cache=True,terminal_cache=True,configuration_cache=True):
        self.enabled=enabled;self.states={};self.entries={};self.terminal={};self.configurations={}
        self.state_enabled=enabled and state_cache
        self.terminal_enabled=enabled and terminal_cache
        self.configuration_enabled=enabled and configuration_cache
        self.cache_hits=0;self.cache_misses=0;self.exact_state_evaluations=0;self.terminal_cost_evaluations=0
        self.reused_subproblems=0;self.state_reuses=0;self.configuration_hits=0
    def get_state(self,key):
        if self.state_enabled and key in self.states:
            self.cache_hits+=1;self.state_reuses+=1
            if self.states[key].exact:self.reused_subproblems+=1
            return self.states[key]
        self.cache_misses+=1;return None
    def put_state(self,state):
        if self.state_enabled:self.states[state.key]=state
        self.entries[state.uid]=CacheEntry(state.key,state.h)
    def record(self,state):
        e=self.entries[state.uid]
        if state.exact and not e.exact:self.exact_state_evaluations+=1
        e.exact=state.exact;e.plan=state.best;e.value=state.best.cost if state.best else None
        e.status='EXACT' if state.exact and state.best else 'INFEASIBLE' if state.exact else 'FEASIBLE' if state.best else 'UNSOLVED'
        e.dependencies=tuple(c.key for a in state.actions for c in a.children) if state.actions else ()
    def memory_bytes(self):
        # Accounted owned payload, not RSS; references are not counted as duplicate plans.
        return (sum(sys.getsizeof(k)+sys.getsizeof(v)+(v.ids.nbytes if v.ids is not None else 0) for k,v in self.states.items())+
                sum(sys.getsizeof(k)+sys.getsizeof(v) for k,v in self.entries.items())+
                sum(sys.getsizeof(k)+sys.getsizeof(v) for k,v in self.terminal.items())+
                sum(sys.getsizeof(k)+sys.getsizeof(v) for k,v in self.configurations.items()))
    def stats(self):
        return dict(cache_hits=self.cache_hits,cache_misses=self.cache_misses,exact_state_evaluations=self.exact_state_evaluations,
          terminal_cost_evaluations=self.terminal_cost_evaluations,reused_subproblems=self.reused_subproblems,state_reuses=self.state_reuses,
          configuration_cache_hits=self.configuration_hits,cache_memory_bytes=self.memory_bytes(),
          cache_hit_rate=self.cache_hits/max(1,self.cache_hits+self.cache_misses),cache_state_enabled=self.state_enabled,cache_terminal_enabled=self.terminal_enabled,cache_configuration_enabled=self.configuration_enabled,cache_memory_definition='accounted owned payload estimate; process RSS reported separately')
