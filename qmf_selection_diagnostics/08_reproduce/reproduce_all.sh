#!/usr/bin/env bash
set -euo pipefail
DIAG_SCRIPTS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DIAG_ROOT="$(dirname -- "$DIAG_SCRIPTS")"
DIAG_PYTHON='/media/lingyaqi/Lenovo F510/QMF-Motivation-Study/.venv/bin/python'
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$DIAG_PYTHON" -B "$DIAG_SCRIPTS/prepare_nodes.py" 2>&1 | tee -a "$DIAG_ROOT/02_raw_logs/reproduce_nodes.log"
taskset -c 1 python "$DIAG_SCRIPTS/extract_historical.py"
if [ ! -f "$DIAG_ROOT/01_code_audit/PILOT_PASS.json" ]; then
 "$DIAG_PYTHON" -B "$DIAG_SCRIPTS/run_diagnostics.py" --pilot 2>&1 | tee -a "$DIAG_ROOT/02_raw_logs/reproduce_pilot.log"
fi
"$DIAG_PYTHON" -B "$DIAG_SCRIPTS/validate_new_references.py" 2>&1 | tee -a "$DIAG_ROOT/02_raw_logs/reproduce_references.log"
"$DIAG_PYTHON" -B "$DIAG_SCRIPTS/run_diagnostics.py" 2>&1 | tee -a "$DIAG_ROOT/02_raw_logs/reproduce_formal.log"
taskset -c 1 python "$DIAG_SCRIPTS/analyze.py" 2>&1 | tee "$DIAG_ROOT/06_reports/analysis.log"
taskset -c 1 python "$DIAG_SCRIPTS/validate_metrics.py"
taskset -c 1 python "$DIAG_SCRIPTS/plot_results.py"
taskset -c 1 python "$DIAG_SCRIPTS/update_paper.py"
bash "$DIAG_SCRIPTS/build_paper.sh"
taskset -c 1 python "$DIAG_SCRIPTS/validate_paper.py"
taskset -c 1 python "$DIAG_SCRIPTS/verify_preservation.py"
taskset -c 1 python "$DIAG_SCRIPTS/write_reports.py"
taskset -c 1 python "$DIAG_SCRIPTS/finalize_manifest.py"
