#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
MODE="${1:---full}"
case "$MODE" in --quick|--full) ;; *) echo 'Use --quick or --full' >&2; exit 2;; esac
bash "$REPRO_ROOT/scripts/00_verify_archive.sh"
bash "$REPRO_ROOT/data/verify_geolife_100m.sh"
python "$REPRO_ROOT/scripts/verify_queries.py"
bash "$REPRO_ROOT/scripts/01_check_environment.sh"
bash "$REPRO_ROOT/third_party/fetch_baselines.sh"
python -m qmapli.repro data
bash "$REPRO_ROOT/scripts/04_build_all.sh"
bash "$REPRO_ROOT/scripts/02_prepare_postgres.sh"
python -m qmapli.repro prepare
if [[ "$MODE" == --quick ]]; then
  python -m qmapli.repro quick
else
  python -m qmapli.repro build
  python -m qmapli.repro benchmark
  python -m qmapli.repro analyze
  python -m qmapli.repro compare
fi
bash "$REPRO_ROOT/scripts/run_tests.sh"
