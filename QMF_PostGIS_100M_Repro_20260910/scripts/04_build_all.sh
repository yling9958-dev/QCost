#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
cmake -S "$REPRO_ROOT/src/qmap/cpp" -B "$QMAP_BUILD_ROOT" -DCMAKE_BUILD_TYPE=Release -DQMF_BASELINES="$QMF_RUNTIME/baselines"
cmake --build "$QMAP_BUILD_ROOT" -j "${QMF_BUILD_JOBS:-2}"
mkdir -p "$QMF_RUNTIME/extension"
cp "$REPRO_ROOT"/src/postgres/* "$QMF_RUNTIME/extension/"
source_alias="$QMF_RUNTIME/repro-source"
if [[ -e "$source_alias" && ! -L "$source_alias" ]]; then
  echo "Runtime source alias exists and is not a symlink: $source_alias" >&2
  exit 2
fi
ln -sfn "$REPRO_ROOT" "$source_alias"
make -C "$QMF_RUNTIME/extension" with_llvm=no \
  PG_CPPFLAGS="-I$source_alias/src/qmap/cpp/include" \
  QMAP_CPP_BUILD_ROOT="$QMAP_BUILD_ROOT" \
  QMAP_RUNTIME_INSTALL_DIR="$QMAP_BUILD_ROOT/lib"
