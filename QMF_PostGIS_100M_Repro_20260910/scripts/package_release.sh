#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPRO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DELIVERY_ROOT="$(cd "$REPRO_ROOT/.." && pwd)"
PACKAGE_NAME="$(basename "$REPRO_ROOT")"
DIST="$DELIVERY_ROOT/dist"
FULL="$DIST/QMF_PostGIS_100M_Repro_FULL_20260910.zip"
PUBLIC="$DIST/QMF_PostGIS_100M_Repro_PUBLIC_20260910.zip"
STAGE="$(mktemp -d /var/tmp/qmf-public-package.XXXXXX)"
trap 'rm -rf -- "$STAGE"' EXIT

bash "$SCRIPT_DIR/00_verify_archive.sh"
bash "$REPRO_ROOT/data/verify_geolife_100m.sh"
mkdir -p "$DIST"

rm -f -- "$FULL" "$PUBLIC" "$FULL.sha256" "$PUBLIC.sha256"
(cd "$DELIVERY_ROOT" && zip -q -r "$FULL" "$PACKAGE_NAME")

cp -a "$REPRO_ROOT" "$STAGE/$PACKAGE_NAME"
rm -f -- "$STAGE/$PACKAGE_NAME/data/frozen/geolife_100m.csv"
(cd "$STAGE/$PACKAGE_NAME" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum | sed 's#  \./#  #' > MANIFEST.sha256)
(cd "$STAGE" && zip -q -r "$PUBLIC" "$PACKAGE_NAME")

(cd "$DIST" && sha256sum "$(basename "$FULL")" > "$(basename "$FULL").sha256")
(cd "$DIST" && sha256sum "$(basename "$PUBLIC")" > "$(basename "$PUBLIC").sha256")

unzip -Z1 "$FULL" > "$STAGE/full.list"
unzip -Z1 "$PUBLIC" > "$STAGE/public.list"
grep -Fxq "$PACKAGE_NAME/data/frozen/geolife_100m.csv" "$STAGE/full.list"
if grep -Fxq "$PACKAGE_NAME/data/frozen/geolife_100m.csv" "$STAGE/public.list"; then
  echo 'PUBLIC_PACKAGE_CONTAINS_RESTRICTED_DATASET' >&2
  exit 1
fi
echo "FULL_PACKAGE=$FULL"
echo "PUBLIC_PACKAGE=$PUBLIC"
