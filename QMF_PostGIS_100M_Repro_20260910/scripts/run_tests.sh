#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
python -m pytest "$REPRO_ROOT/tests" -q -p no:cacheprovider --junitxml="$QMF_RUNTIME/tests.xml"
