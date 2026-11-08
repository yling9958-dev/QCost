#!/usr/bin/env bash
set -euo pipefail
RANDOM_REVISION_SCRIPTS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bash "$RANDOM_REVISION_SCRIPTS/run_experiments.sh"
taskset -c 1 python "$RANDOM_REVISION_SCRIPTS/../02_code/update_paper.py"
bash "$RANDOM_REVISION_SCRIPTS/build_paper.sh"
taskset -c 1 python "$RANDOM_REVISION_SCRIPTS/validate_delivery.py"
taskset -c 1 python "$RANDOM_REVISION_SCRIPTS/verify_preservation.py"
taskset -c 1 python "$RANDOM_REVISION_SCRIPTS/../02_code/write_reports.py"
