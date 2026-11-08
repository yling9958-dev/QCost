#!/usr/bin/env bash
set -Eeuo pipefail
base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
stamp=$(date +%Y%m%dT%H%M%S)-$$
destination=${1:-"$base/reproduce_$stamp"}
if [[ -e "$destination" ]]; then
  printf 'Refusing to overwrite existing output: %s\n' "$destination" >&2
  exit 2
fi
mkdir -p -- "$destination"/{01_environment,02_diagnosis,03_validation,04_build,05_queries,06_correctness,07_metrics,08_reports,tools}
cp -- "$base"/tools/*.py "$base/tools/validate_flood.cpp" "$destination/tools/"
cp -- "$base/08_reports/FLOOD_SKEWED2D_DIAGNOSIS.md" "$destination/08_reports/"
cp -- "$base/FLOOD_SKEWED2D_REPRODUCE.sh" "$destination/"
python3 -B "$base/tools/native_artifacts.py" verify >/dev/null
cp -a -- "$base/01_environment/validated_binary_snapshot" "$destination/01_environment/"
for provenance in native_bundle_manifest.json flood_v2_version.json flood_v2_source_snapshot.tar.gz learnedbench_patched_snapshot.tar.gz experiment_harness_snapshot.tar.gz REPRODUCTION_DEPENDENCIES.md; do
  cp -- "$base/01_environment/$provenance" "$destination/01_environment/"
done
export FLOOD_COMPLETION_RUNTIME="/var/tmp/flood-skewed2d-reproduce-$stamp"
export FLOOD_COMPLETION_COMMON="$FLOOD_COMPLETION_RUNTIME/common"
export FLOOD_COMPLETION_VALIDATOR="$FLOOD_COMPLETION_RUNTIME/validation/validate_v2"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
command -v python3 g++ sudo systemd-run >/dev/null
sudo -n true
python3 -c 'import numpy,pandas; assert numpy.__version__ == "1.26.4"'
mkdir -p -- "$FLOOD_COMPLETION_RUNTIME"
printf 'Output: %s\nRuntime: %s\n' "$destination" "$FLOOD_COMPLETION_RUNTIME"
printf '%s\n' "$FLOOD_COMPLETION_RUNTIME" > "$destination/01_environment/runtime_path.txt"
on_exit() {
  result=$?
  trap - EXIT
  python3 -B "$destination/tools/finalize.py" > "$destination/08_reports/terminal_summary.txt" 2>&1 || true
  printf 'Execution exit status: %s\nOutput: %s\n' "$result" "$destination"
  exit "$result"
}
trap on_exit EXIT
python3 -B "$destination/tools/native_artifacts.py" bootstrap "$FLOOD_COMPLETION_RUNTIME" > "$destination/01_environment/native_bootstrap.json"
python3 -B "$destination/tools/initial_audit.py" initial
python3 -B "$destination/tools/run_stage.py" validation
python3 -B "$destination/tools/verify_count_edges.py"
python3 -B "$destination/tools/run_stage.py" full_read
python3 -B "$destination/tools/run_stage.py" build
python3 -B "$destination/tools/run_stage.py" grid
python3 -B "$destination/tools/postgres_stages.py" reference
python3 -B "$destination/tools/postgres_stages.py" reference_cluster
python3 -B "$destination/tools/postgres_stages.py" correctness
python3 -B "$destination/tools/postgres_stages.py" timing
python3 -B "$destination/tools/finalize.py"
python3 -B "$destination/tools/independent_audit.py"
python3 - "$destination" <<'PY'
import json,sys
from pathlib import Path
assert json.loads((Path(sys.argv[1])/'07_metrics/acceptance.json').read_text())['status']=='EXPERIMENT_COMPLETED'
PY
