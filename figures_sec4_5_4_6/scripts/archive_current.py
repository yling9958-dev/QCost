"""Keep every previous output when the read-only extraction/plot pipeline is repeated."""
from pathlib import Path
from datetime import datetime,timezone
import zipfile
ROOT=Path(__file__).resolve().parents[1]
files=[p for folder in ['data','figures','latex','reports','scripts'] for p in (ROOT/folder).rglob('*')
       if p.is_file() and '__pycache__' not in p.parts and 'mplconfig' not in p.parts]
if files:
    name=datetime.now(timezone.utc).strftime('derived_before_reproduce_%Y%m%dT%H%M%S_%fZ.zip')
    with zipfile.ZipFile(ROOT/'archive'/name,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,str(p.relative_to(ROOT)))
    print('Archived',len(files),'derived files to archive/'+name)
