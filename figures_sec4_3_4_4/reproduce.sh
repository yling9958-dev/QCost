#!/usr/bin/env bash
set -euo pipefail
revision_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$revision_root"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
revision_python='/media/lingyaqi/Lenovo F510/QMF-Motivation-Study/.venv/bin/python'
"$revision_python" -B scripts/archive_current.py
"$revision_python" -B scripts/extract_results.py
"$revision_python" -B scripts/plot_fig10.py
"$revision_python" -B scripts/plot_fig11.py
"$revision_python" -B scripts/plot_fig12.py
"$revision_python" -B scripts/plot_fig13.py
"$revision_python" -B scripts/write_delivery.py
"$revision_python" -B scripts/check_delivery.py
