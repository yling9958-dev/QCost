"""Incremental exact AND/OR evaluation; scheduling only, no bound pruning."""
class RecursiveAnytime:
    def __init__(self,engine,feedback=True):self.engine=engine;self.feedback=feedback
    def initialize(self,state=None):
        e=self.engine;s=e.root if state is None else state;e.meter.check()
        if s.best is not None or s.exact:return
        e.expand(s)
        for t in s.actions:
            self.evaluate(t)
            if s.best is not None:break
    def evaluate(self,t):
        e=self.engine;e.meter.check();t.started=True
        children=list(t.children)
        if self.feedback:
            children.sort(key=lambda c:(c.best is not None,-(c.best.cost if c.best else c.proxy),c.uid))
        for c in children:
            self.initialize(c)
            if c.exact and c.best is None:break
        e.update(t.state)
