#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPRO_ROOT="$PROJECT_ROOT/QMF_PostGIS_100M_Repro_20260910"
FIXTURE_ROOT="/var/tmp/qmf-memory-opt-100m"
OUTPUT_ROOT="$PROJECT_ROOT/results/qmf_8core_engineering_diagnostic_20260913/env8_100m"

mkdir -p "$OUTPUT_ROOT"
test "$(sha256sum "$FIXTURE_ROOT/points_normalized.csv" | cut -d' ' -f1)" = \
  "6d7978b6703e74e2896dbefe0080540f50325a1e7db047faaf43a50cde2cf22a"
test "$(sha256sum "$FIXTURE_ROOT/queries/train_normalized.csv" | cut -d' ' -f1)" = \
  "1dabdc74c02fab9ee4d6de582880c0e782cc35b847564a1868fb020ee59a93b5"

export REPRO_ROOT
export PYTHONPATH="$REPRO_ROOT/src/common/python"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export MKL_NUM_THREADS=8
export QMF_BUILD_JOBS=8

exec /usr/bin/time -v -o "$OUTPUT_ROOT/time.txt" \
  taskset -c 0-7 python3 -B "$PROJECT_ROOT/scripts/diagnostics/qmf_build_with_trace.py" \
  "$OUTPUT_ROOT" "$FIXTURE_ROOT/points_normalized.csv" 4197223 \
  "$FIXTURE_ROOT/queries/train_normalized.csv"
