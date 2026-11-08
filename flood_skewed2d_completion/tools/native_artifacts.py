"""Archive and restore the exact validated binaries without a temporary-cache dependency."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from initial_audit import ROOT, FLOOD, KIT, sha, write

ORIGINAL = Path('/var/tmp/qmf-three-baselines/7da901c84be5/flood')
FILES = {
    'qmf_postgres_full': ('common/qmf_postgres_full', '3ebcc8130bca4e140c824c6e3c31e10ae6e42a7257251cfca43b8b04389df938'),
    'qmap_build_index': ('common/build/bin/qmap_build_index', '01008977adf8b6b394d828ddc79e69306704e1a7aeefba033b5f91a50f2afd4a'),
    'libqmap_runtime.so': ('common/build/lib/libqmap_runtime.so', '52283a9c9f9b35a6506dfe859a12d931f6bc4455076c84229c2f0bf98109f973'),
    'qmap_benchmark.so': ('common/extension/qmap_benchmark.so', '5e1e2261038b3534c5ffb5a7966e77ba6f72a8aa5467a81f47400a3798414256'),
    'validate_v2': ('validation/validate_v2', '648b5f78cfd58bb67e39fab17ee8e308d1f1181904f322e1d4bd50f13f15f644'),
}
SNAPSHOT = ROOT/'01_environment/validated_binary_snapshot'


def verify():
    checked = {}
    for name, (relative, expected) in FILES.items():
        path = SNAPSHOT/name
        assert path.is_file() and sha(path) == expected, f'Missing or changed native snapshot: {path}'
        checked[name] = dict(relative_path=relative, sha256=expected, bytes=path.stat().st_size)
    return checked


def archive():
    SNAPSHOT.mkdir(exist_ok=True)
    for name, (relative, expected) in FILES.items():
        source = ORIGINAL/relative
        assert sha(source) == expected, str(source)
        target = SNAPSHOT/name
        if not target.exists():
            shutil.copy2(source, target)
        assert sha(target) == expected, str(target)
    env = ROOT/'01_environment'
    harness = env/'experiment_harness_snapshot.tar.gz'
    if not harness.exists():
        subprocess.run(['tar', '-czf', str(harness), '-C', str(KIT),
                        'implementations/shared/engine', 'implementations/flood/postgres.conf',
                        'scripts', 'protocol/EXPERIMENT_CONFIG_LOCK.json'], check=True)
    version = env/'flood_v2_version.json'
    if not version.exists():
        shutil.copy2(FLOOD/'FLOOD_RECOVERY_V2/evidence/VERSION.json', version)
    dependencies = {}
    for name in FILES:
        dependencies[name] = subprocess.check_output(['readelf', '-d', str(SNAPSHOT/name)], text=True)
    result = dict(files=verify(), harness_archive_sha256=sha(harness),
                  version_sha256=sha(version), elf_dynamic_sections=dependencies,
                  helper_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                                 [*sorted((ROOT/'tools').glob('*.py')), *sorted((ROOT/'tools').glob('*.cpp')), ROOT/'FLOOD_SKEWED2D_REPRODUCE.sh']},
                  scope='Exact original binaries; project/data and installed PostgreSQL/PostGIS/system libraries remain prerequisites.')
    write(env/'native_bundle_manifest.json', result)
    return result


def bootstrap(runtime):
    checked = verify()
    runtime = Path(runtime).resolve()
    assert runtime.is_dir(), 'Create the isolated runtime first.'
    assert not (runtime/'common').exists() and not (runtime/'validation').exists(), 'Refuse to overwrite native runtime.'
    for name, (relative, expected) in FILES.items():
        target = runtime/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SNAPSHOT/name, target)
        assert sha(target) == expected
    result = dict(common=str(runtime/'common'), validator=str(runtime/'validation/validate_v2'), files=checked)
    write(runtime/'native_bootstrap.json', result)
    return result


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'archive':
        result = archive()
    elif action == 'verify':
        result = dict(files=verify())
    elif action == 'bootstrap':
        result = bootstrap(sys.argv[2])
    else:
        raise ValueError(action)
    print(json.dumps(result, indent=2))
