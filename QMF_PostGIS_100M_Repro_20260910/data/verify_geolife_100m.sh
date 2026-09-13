#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPRO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
dataset="${1:-$REPRO_ROOT/data/frozen/geolife_100m.csv}"
if [[ ! -f "$dataset" ]]; then
  echo "FROZEN_DATASET_MISSING: $dataset" >&2
  echo "Public-package users must explicitly run: bash data/recovery/fetch_geolife.sh" >&2
  exit 1
fi
python "$SCRIPT_DIR/recovery/build_geolife_100m.py" \
  --verify-only \
  --output "$dataset" >/dev/null
echo 'DATASET_VERIFICATION = PASS'
