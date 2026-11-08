#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPRO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
QMF_RUNTIME="${QMF_RUNTIME:-${QMF_RUNTIME_ROOT:-/var/tmp/qmf-repro}}"

mkdir -p "$QMF_RUNTIME/downloads"
archive="${QMF_GEOLIFE_ARCHIVE:-$QMF_RUNTIME/downloads/Geolife_Trajectories_1_3.zip}"
if [[ ! -f "$archive" ]]; then
  url="${QMF_GEOLIFE_ARCHIVE_URL:-https://download.microsoft.com/download/F/4/8/F4894AA5-FDBC-481E-9285-D5F8C4C4F039/Geolife%20Trajectories%201.3.zip}"
  curl --fail --location "$url" -o "$archive.part"
  mv "$archive.part" "$archive"
fi

bash "$SCRIPT_DIR/verify_source.sh" "$archive"
python "$SCRIPT_DIR/build_geolife_100m.py" \
  --archive "$archive" \
  --order "$SCRIPT_DIR/geolife_plt_order.txt" \
  --output "$REPRO_ROOT/data/frozen/geolife_100m.csv"
bash "$REPRO_ROOT/data/verify_geolife_100m.sh"
