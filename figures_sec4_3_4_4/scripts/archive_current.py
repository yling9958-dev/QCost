"""Before repeat rendering, preserve this output directory's previous artifacts."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import zipfile
R=Path(__file__).resolve().parents[1]
stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S%f')
p=R/'archive'/f'previous_render_{stamp}.zip'
with zipfile.ZipFile(p,'x',zipfile.ZIP_DEFLATED) as z:
    for folder in ['data','figures','scripts','latex','reports']:
        for f in sorted((R/folder).rglob('*')):
            if f.is_file() and not any(x in f.parts for x in ['mplconfig','__pycache__']):z.write(f,f.relative_to(R))
print(p)
