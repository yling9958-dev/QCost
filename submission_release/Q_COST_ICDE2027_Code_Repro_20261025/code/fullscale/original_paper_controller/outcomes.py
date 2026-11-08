"""Terminal cause and failed phase are separate experimental evidence."""
from paper_protocol import STATUSES

def phase_failure(phase):
    return {'correctness':'CORRECTNESS_FAILED','warmup':'WARMUP_FAILED','timing':'TIMING_FAILED',
            'finalization':'FINALIZATION_FAILED','reporting':'REPORTING_FAILED'}.get(phase,'BUILD_FAILED')

def classify(phase,reason='',events=None,initial=None,oomd=False,swap=0):
    events=events or {}; initial=initial or {}
    if swap: return 'SWAP_INVALID'
    if 'HOST_SAFETY_STOP' in reason: return 'HOST_SAFETY_STOP'
    if oomd or events.get('oom_kill',0)>initial.get('oom_kill',0): return 'OOM_KILLED'
    if events.get('max',0)>initial.get('max',0) or events.get('oom',0)>initial.get('oom',0): return 'CGROUP_MEMORY_MAX'
    return phase_failure(phase)
