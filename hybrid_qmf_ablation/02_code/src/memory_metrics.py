"""Linux process-local memory measurements; no background sampler thread."""
from pathlib import Path

def memory():
    fields={}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:','VmHWM:','VmSize:')):
            key,value,*_=line.split();fields[key[:-1]]=int(value)/1024.
    return dict(rss_mib=fields['VmRSS'],peak_rss_mib=fields['VmHWM'],virtual_mib=fields['VmSize'])

def reset_peak():
    before=memory()
    Path('/proc/self/clear_refs').write_text('5\n')
    return before
