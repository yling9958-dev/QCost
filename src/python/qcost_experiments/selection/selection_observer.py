"""Observer-only event logging; never reads an Exact reference or changes a cost."""
from .conditional_state import ConditionalEngine
from .recursive_anytime import RecursiveAnytime
from .shared_cache import SharedCache
class Observer:
    def __init__(self,meter):
        self.meter=meter;self.candidates=[];self.active=[];self.completed=0;self.selections=[];self.exact=[];self.lookups=[];self.incumbent_plans=[]
        self.initializing=True;self.current_selection=None;self.cache=None
    def counters(self):
        c=self.cache
        return dict(completed=self.completed,exact=c.exact_state_evaluations,cache_hits=c.cache_hits,
                    cache_misses=c.cache_misses,terminal_calls=c.terminal_cost_evaluations)
    def lookup(self,kind,hit):
        self.lookups.append([self.meter.elapsed(),kind,bool(hit),self.active[-1] if self.active else None])
    def incumbent(self,event,plan):
        event.update(candidate_completed=self.completed,active_candidate=self.active[-1] if self.active else None,
                     selected_candidate=self.current_selection,initialization=self.initializing,**self.counters())
        if self.active:self.candidates[self.active[-1]]['direct_improvements']+=1
        self.incumbent_plans.append((event,plan))
class ObservedCache(SharedCache):
    def __init__(self,enabled,observer,**kwargs):
        self.observer=observer;super().__init__(enabled,**kwargs);observer.cache=self
    def get_state(self,key):
        result=super().get_state(key);self.observer.lookup('state',result is not None);return result
    def record(self,state):
        before=self.exact_state_evaluations;super().record(state)
        if self.exact_state_evaluations>before:
            self.observer.exact.append([self.observer.meter.elapsed(),state.key,bool(state.best is not None)])
class ObservedEngine(ConditionalEngine):
    def __init__(self,*args,observer,**kwargs):self.observer=observer;super().__init__(*args,**kwargs)
    def leaf_work(self,state):
        before=self.cache.cache_hits;result=super().leaf_work(state)
        self.observer.lookup('terminal',self.cache.cache_hits>before);return result
    def combine(self,task):
        eligible=all(c.best is not None for c in task.children);before=self.cache.configuration_hits
        result=super().combine(task)
        if eligible:self.observer.lookup('configuration',self.cache.configuration_hits>before)
        return result
    def _update(self,state):
        before=len(self.incumbent_trace);super()._update(state)
        if state is self.root and len(self.incumbent_trace)>before:
            self.observer.incumbent(self.incumbent_trace[-1],self.incumbent)
class ObservedRecursion(RecursiveAnytime):
    def evaluate(self,task):
        o=self.engine.observer;i=len(o.candidates)
        row=dict(id=i,task=task.uid,parent=o.active[-1] if o.active else None,selection=o.current_selection,
                 initialization=o.initializing,start=o.meter.elapsed(),end=None,complete=False,direct_improvements=0,
                 before=o.counters())
        o.candidates.append(row);o.active.append(i)
        try:
            result=super().evaluate(task);row['complete']=True;o.completed+=1;return result
        finally:
            row['end']=o.meter.elapsed();row['after']=o.counters();assert o.active.pop()==i
