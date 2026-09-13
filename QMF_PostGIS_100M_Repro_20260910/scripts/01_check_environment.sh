#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
for cmd in python cmake g++ make git pg_config psql taskset; do command -v "$cmd" >/dev/null; done
python -m qmapli.repro environment
