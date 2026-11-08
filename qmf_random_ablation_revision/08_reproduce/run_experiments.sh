#!/usr/bin/env bash
set -euo pipefail
RANDOM_REVISION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RANDOM_PYTHON='/media/lingyaqi/Lenovo F510/QMF-Motivation-Study/.venv/bin/python'
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$RANDOM_PYTHON" -B "$RANDOM_REVISION_ROOT/02_code/run_random.py" --pilot 2>&1 | tee -a "$RANDOM_REVISION_ROOT/03_runs/reproduce_pilot.log"
taskset -c 1 python "$RANDOM_REVISION_ROOT/02_code/validate_pilot.py"
"$RANDOM_PYTHON" -B "$RANDOM_REVISION_ROOT/02_code/run_random.py" 2>&1 | tee -a "$RANDOM_REVISION_ROOT/03_runs/reproduce_formal.log"
taskset -c 1 python "$RANDOM_REVISION_ROOT/02_code/analyze_random.py" 2>&1 | tee "$RANDOM_REVISION_ROOT/07_reports/analysis.log"
