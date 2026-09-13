#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
python -m qmapli.repro benchmark
