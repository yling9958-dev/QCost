#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
archive="${1:?usage: verify_source.sh OFFICIAL_GEOLIFE_ZIP}"
expected_bytes=313164406
expected_sha=1107c5ac064d0a23c8d021a8736a77e53abc75b227062e6260342c6a8d86bdb6
actual_bytes="$(stat -c %s "$archive")"
actual_sha="$(sha256sum "$archive" | awk '{print $1}')"
[[ "$actual_bytes" == "$expected_bytes" ]] || { echo 'GEOLIFE_ARCHIVE_BYTES_MISMATCH' >&2; exit 1; }
[[ "$actual_sha" == "$expected_sha" ]] || { echo 'GEOLIFE_ARCHIVE_SHA_MISMATCH' >&2; exit 1; }
python "$SCRIPT_DIR/prepare_geolife_source.py" \
  --archive "$archive" --order "$SCRIPT_DIR/geolife_plt_order.txt" >/dev/null
echo 'GEOLIFE_SOURCE_VERIFICATION = PASS'
