"""Record bounded, read-only I/O evidence for explicitly selected live PIDs."""
import json
import os
import stat
import sys
import time
from pathlib import Path
from initial_audit import ROOT, write
from run_stage import now


def inspect(pid):
    proc = Path('/proc', str(pid))
    try:
        fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
        result = dict(pid=pid, start_ticks=int(fields[19]),
                      comm=(proc/'comm').read_text().strip(),
                      cgroup=(proc/'cgroup').read_text().strip(),
                      io={k: int(v) for k, v in
                          (line.split(':', 1) for line in (proc/'io').read_text().splitlines())})
        devices = {}
        for fd in (proc/'fd').iterdir():
            try:
                info = fd.stat()
                if stat.S_ISREG(info.st_mode):
                    key = str(info.st_dev)
                    devices[key] = devices.get(key, 0) + 1
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass
        result['open_regular_files_by_device'] = devices
        final = (proc/'stat').read_text().rsplit(')', 1)[1].split()
        result['same_process_at_end'] = int(final[19]) == result['start_ticks']
        return result
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return dict(pid=pid, unavailable_at_sample=True)


if __name__ == '__main__':
    assert len(sys.argv) > 1, 'Pass explicit numeric PIDs to inspect.'
    result = dict(at=now(), reference_device=os.stat(ROOT/'06_correctness/reference_tablespace').st_dev,
                  processes=[inspect(int(pid)) for pid in sys.argv[1:]],
                  host_pressure={kind: Path('/proc/pressure', kind).read_text()
                                 for kind in ['io', 'memory']},
                  note='Observation only; no process signaling, scheduling or memory settings changed. File paths and command arguments are not collected.')
    output = ROOT/'02_diagnosis'/f'io_contention_{time.time_ns()}.json'
    write(output, result)
    print(json.dumps(dict(path=str(output), **result), indent=2))
