#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: $0 POINT_COUNT INPUT_CSV OUTPUT_DIR [QUERY_CSV]" >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPRO_ROOT="$PROJECT_ROOT/QMF_PostGIS_100M_Repro_20260910"
POINT_COUNT="$1"
INPUT_CSV="$2"
OUTPUT_DIR="$3"
QUERY_CSV="${4:-$PROJECT_ROOT/results/four_dataset_paper_protocol_20260911/02_queries/geolife_2d_4p2G/train_normalized.csv}"

if [ ! -f "$INPUT_CSV" ]; then
  echo "input CSV not found: $INPUT_CSV" >&2
  exit 2
fi
if [ ! -f "$QUERY_CSV" ]; then
  echo "query CSV not found: $QUERY_CSV" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"
export REPRO_ROOT
export PYTHONPATH="$REPRO_ROOT/src/common/python"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export QMF_BUILD_JOBS=2

exec /usr/bin/time -v -o "$OUTPUT_DIR/time.txt" \
  python3 -B "$PROJECT_ROOT/scripts/diagnostics/qmf_build_with_trace.py" \
  "$OUTPUT_DIR" "$INPUT_CSV" "$POINT_COUNT" "$QUERY_CSV"
