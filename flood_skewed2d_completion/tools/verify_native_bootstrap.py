"""Exercise restored native artifacts on diagnostic data, outside formal metrics."""
import csv
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from initial_audit import ROOT, sha, write
from native_artifacts import ORIGINAL, FILES, bootstrap


def main():
    folder = ROOT/'03_validation'/f'native_bootstrap_smoke_{time.time_ns()}'
    folder.mkdir()
    runtime = Path(tempfile.mkdtemp(prefix='flood-native-bootstrap-20261024-', dir='/var/tmp'))
    restored = bootstrap(runtime)
    common = Path(restored['common'])
    env = {**os.environ, 'LD_LIBRARY_PATH': str(common/'build/lib'),
           'FLOOD_COMPLETION_COMMON': str(common),
           'FLOOD_COMPLETION_VALIDATOR': restored['validator'],
           'PYTHONDONTWRITEBYTECODE': '1', 'LC_ALL': 'C',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    commands = []

    def execute(label, command):
        log = folder/(label+'.log')
        started = time.monotonic()
        with log.open('x') as output:
            result = subprocess.run(list(map(str, command)), env=env, cwd=ROOT/'tools',
                                    stdout=output, stderr=subprocess.STDOUT, timeout=120)
        commands.append(dict(label=label, command=list(map(str, command)), returncode=result.returncode,
                             elapsed_s=time.monotonic()-started, log=str(log)))
        write(folder/'commands.json', commands)
        assert result.returncode == 0, str(log)
        return log.read_text()

    library = str(common/'build/lib/libqmap_runtime.so')
    for name, (relative, _) in FILES.items():
        output = execute('ldd_'+name, ['ldd', runtime/relative])
        assert 'not found' not in output, name
        if name in ('qmap_build_index', 'qmap_benchmark.so', 'validate_v2'):
            assert 'libqmap_runtime.so => '+library in output, output

    selected = execute('selected_configuration', ['python3', '-B', '-c',
        "import json; from run_stage import COMMON,VALIDATOR,native_env; "
        "print(json.dumps(dict(common=str(COMMON),validator=str(VALIDATOR),environment=native_env())))"])
    configuration = json.loads(selected)
    assert configuration['common'] == str(common)
    assert configuration['validator'] == restored['validator']
    assert configuration['environment']['LD_LIBRARY_PATH'] == str(common/'build/lib')

    sample = ROOT/'03_validation/diagnostic_16384.csv'
    correctness = folder/'correctness.csv'
    execute('validator', [restored['validator'], sample, correctness, runtime/'validation_smoke'])
    with correctness.open() as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 4808 and all(row['exact'] == '1' and row['missing'] == '0' and row['extra'] == '0' for row in rows)

    queries = ROOT/'03_validation/frozen_queries'
    archive = runtime/'flood.idx'
    execute('builder', [common/'build/bin/qmap_build_index', '--method', 'flood', '--points', sample,
                       '--train-queries', queries/'train_normalized.csv',
                       '--validation-queries', queries/'validation_normalized.csv',
                       '--index', archive, '--output', folder/'diagnostic_build.csv'])
    with archive.open('rb') as source:
        points = int.from_bytes(source.read(8), 'little')
    assert points == 16384 and archive.stat().st_size == 9+12*points
    original_cache = {}
    for relative, expected in FILES.values():
        source = ORIGINAL/relative
        if source.exists():
            assert sha(source) == expected
            original_cache[relative] = 'present and unchanged'
        else:
            original_cache[relative] = 'absent; restored snapshot used'
    result = dict(diagnostic_only=True, status='PASS', source_points=points, validator_checks=len(rows),
                  all_id_checks_exact=True, runtime=str(runtime), configuration=configuration,
                  sample_sha256=sha(sample), archive_sha256=sha(archive),
                  verification_script_sha256=sha(Path(__file__)), original_cache=original_cache,
                  restored_files=restored['files'], commands=commands,
                  scope='Restored binary hashes, relocated dynamic library resolution, native validator and native index build. No full experiment rerun or PostgreSQL service restart.')
    write(folder/'PASS.json', result)
    print(json.dumps(dict(path=str(folder/'PASS.json'), **result), indent=2))


if __name__ == '__main__':
    main()
