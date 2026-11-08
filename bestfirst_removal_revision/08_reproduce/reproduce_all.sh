#!/usr/bin/env bash
set -euo pipefail
REVISION_SCRIPTS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
python "$REVISION_SCRIPTS/prepare_data.py"
python "$REVISION_SCRIPTS/regenerate_ablation_table.py"
python "$REVISION_SCRIPTS/regenerate_fig12.py"
python "$REVISION_SCRIPTS/regenerate_fig13.py"
python "$REVISION_SCRIPTS/regenerate_fig16.py"
python "$REVISION_SCRIPTS/revise_manuscript.py"
bash "$REVISION_SCRIPTS/build_paper.sh"
python "$REVISION_SCRIPTS/validate_delivery.py"
python "$REVISION_SCRIPTS/verify_preservation.py"
python "$REVISION_SCRIPTS/write_reports.py"
