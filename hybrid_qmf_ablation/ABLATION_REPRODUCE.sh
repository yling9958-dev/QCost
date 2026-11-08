#!/usr/bin/env bash
set -euo pipefail
ABLATION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ABLATION_PYTHON='/media/lingyaqi/Lenovo F510/QMF-Motivation-Study/.venv/bin/python'
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
cd "$ABLATION_ROOT/.."
# Resume only missing combinations. Existing raw checkpoints are never overwritten.
"$ABLATION_PYTHON" -B "$ABLATION_ROOT/02_code/run_ablation.py" --pilot 2>&1 | tee -a "$ABLATION_ROOT/03_runs/reproduce_pilot.log"
"$ABLATION_PYTHON" -B "$ABLATION_ROOT/02_code/run_ablation.py" 2>&1 | tee -a "$ABLATION_ROOT/03_runs/reproduce_formal.log"
taskset -c 1 python "$ABLATION_ROOT/02_code/analyze.py"
"$ABLATION_PYTHON" -B "$ABLATION_ROOT/06_reports/validate_enumeration.py" 2>&1 | tee -a "$ABLATION_ROOT/03_runs/reproduce_enumeration_validation.log"
taskset -c 1 python "$ABLATION_ROOT/02_code/make_reports.py"
taskset -c 1 python "$ABLATION_ROOT/02_code/paper_delivery.py" --integrate
bash "$ABLATION_ROOT/ABLATION_COMPILE.sh"
taskset -c 1 python "$ABLATION_ROOT/06_reports/validate_paper.py"
taskset -c 1 python "$ABLATION_ROOT/06_reports/finalize_delivery.py"
