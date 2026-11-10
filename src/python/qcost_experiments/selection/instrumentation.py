from contextlib import contextmanager
from collections import defaultdict
import time,resource
class BudgetExpired(Exception):pass
class Instrumentation:
    def __init__(self,seconds=None,attempts=None):
        self.started=time.perf_counter();self.cpu0=time.process_time();self.seconds=seconds;self.limit=attempts
        self.attempts=0;self.phases=defaultdict(float);self.stack=[];self.events=[]
    def elapsed(self):return time.perf_counter()-self.started
    def check(self):
        if self.seconds is not None and self.elapsed()>=self.seconds:raise BudgetExpired('wall_clock')
    @contextmanager
    def phase(self,name):
        now=time.perf_counter()
        if self.stack:self.phases[self.stack[-1][0]]+=now-self.stack[-1][1]
        self.stack.append([name,now])
        try:yield
        finally:
            now=time.perf_counter();key,t=self.stack.pop();self.phases[key]+=now-t
            if self.stack:self.stack[-1][1]=now
    def summary(self):
        elapsed=self.elapsed();phases=dict(self.phases);phases['other']=max(0.,elapsed-sum(phases.values()))
        return dict(total_optimizer_time=elapsed,cpu_seconds=time.process_time()-self.cpu0,peak_memory_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                    phase_seconds=phases,attempts=self.attempts,deadline_seconds=self.seconds,
                    deadline_overrun_seconds=max(0.,elapsed-self.seconds) if self.seconds is not None else 0.)
