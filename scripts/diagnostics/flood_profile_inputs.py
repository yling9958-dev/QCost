"""Create deterministic diagnostic prefixes from a read-only Flood artifact."""
import hashlib
import json
from pathlib import Path
import struct

SOURCE=Path('/var/tmp/qmf-paper-protocol-20260911/active/geolife_2d_4p2G/methods/flood/rep0/flood.idx')
OUT=Path('/var/tmp/qmf-flood-correctness-memfix-20260915')
def main():
    with SOURCE.open('rb') as source:
        header=source.read(9)
        assert struct.unpack('<Q',header[:8])[0]==181000000
        for n in (1000000,5000000,10000000,25000000,50000000):
            target=OUT/'inputs'/f'{n}.idx';target.parent.mkdir(parents=True,exist_ok=True)
            source.seek(9)
            h=hashlib.sha256()
            with target.open('xb') as output:
                prefix=struct.pack('<Q',n)+header[8:9];output.write(prefix);h.update(prefix)
                remaining=12*n
                while remaining:
                    block=source.read(min(8*1024*1024,remaining))
                    if not block:raise RuntimeError('source truncated')
                    output.write(block);h.update(block);remaining-=len(block)
            target.with_suffix('.json').write_text(json.dumps({'points':n,'sha256':h.hexdigest(),
                'source':str(SOURCE),'source_offset':9,'preserved_orientation_byte':header[8],
                'scope':'engineering prefix only; no formal dataset/build modified'},indent=2)+'\n')
if __name__=='__main__':main()
