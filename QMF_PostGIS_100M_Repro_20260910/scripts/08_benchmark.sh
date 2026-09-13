#!/usr/bin/env bash
set -euo pipefail
# The frozen harness checks complete IDs before count timing.
bash "$(dirname "$0")/07_correctness.sh"
