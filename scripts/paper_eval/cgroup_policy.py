"""Fixed aggregate memory budget, verified against kernel cgroup files."""
from pathlib import Path
import subprocess

GIB=1024**3
MEMORY_HIGH=22*GIB
MEMORY_MAX=24*GIB
SWAP_MAX=0
CGROUP_ROOT=Path('/sys/fs/cgroup')
SYSTEM_MANAGER=True

def manager(write=False):
    # Read-only polling needs no privilege or per-sample sudo session journal.
    return (['sudo','-n','systemctl'] if write else ['systemctl']) if SYSTEM_MANAGER else ['systemctl','--user']

def configure(slice_name):
    subprocess.run([*manager(True),'set-property','--runtime',slice_name,
        'MemoryAccounting=yes','MemoryHigh='+str(MEMORY_HIGH),
        'MemoryMax='+str(MEMORY_MAX),'MemorySwapMax=0'],check=True)
    subprocess.run([*manager(True),'start',slice_name],check=True)

def snapshot(unit):
    result=subprocess.run([*manager(),'show',unit,'-p','ControlGroup','-p','MemoryCurrent',
        '-p','MemoryPeak','-p','MemoryHigh','-p','MemoryMax','-p','MemorySwapCurrent','-p','MemorySwapMax'],
        check=True,capture_output=True,text=True)
    values=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    group=values.get('ControlGroup',''); kernel={}
    if group:
        root=CGROUP_ROOT/group.lstrip('/')
        for name in ['memory.current','memory.peak','memory.high','memory.max','memory.swap.current','memory.swap.max']:
            try:
                value=(root/name).read_text().strip()
                kernel[name]=int(value) if value!='max' else 'max'
            except FileNotFoundError: kernel[name]=None
        for name in ['memory.events','memory.events.local']:
            try: kernel[name]={k:int(v) for k,v in (line.split() for line in (root/name).read_text().splitlines())}
            except FileNotFoundError: kernel[name]={}
        try:
            kernel['memory.pressure']=(root/'memory.pressure').read_text().strip()
        except FileNotFoundError: pass
    return {'unit':unit,'path':group,'systemd':values,'kernel':kernel}

def validate(parent,children=()):
    kernel=parent['kernel']
    if not parent['path'] or any(kernel.get(k)!=v for k,v in {
        'memory.high':MEMORY_HIGH,'memory.max':MEMORY_MAX,'memory.swap.max':SWAP_MAX}.items()):
        raise RuntimeError('CGROUP_FIX_NOT_EFFECTIVE: wrong fixed parent limits')
    for child in children:
        if not child['path'].startswith(parent['path'].rstrip('/')+'/'):
            raise RuntimeError('CGROUP_FIX_NOT_EFFECTIVE: child outside shared parent')
        if child['kernel'].get('memory.max')!='max' or child['kernel'].get('memory.high')!='max':
            raise RuntimeError('CGROUP_FIX_NOT_EFFECTIVE: independent child memory limit')
    if kernel.get('memory.swap.current')!=0:
        raise RuntimeError('CGROUP_FIX_NOT_EFFECTIVE: experiment swap is nonzero')
    return True
