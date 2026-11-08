#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON='/media/lingyaqi/Lenovo F510/QMF-Motivation-Study/.venv/bin/python'
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export MPLCONFIGDIR="$TASK_DIR/reports/mplconfig"
"$PYTHON" -B "$TASK_DIR/scripts/archive_current.py"
for script in plot_fig7 plot_fig6 plot_fig8 plot_fig9 write_layout_revision check_compact_revision; do
    "$PYTHON" -B "$TASK_DIR/scripts/$script.py" > "$TASK_DIR/reports/${script}_current.log" 2>&1
done
