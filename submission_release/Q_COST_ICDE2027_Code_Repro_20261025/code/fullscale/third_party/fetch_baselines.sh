#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../scripts/common.sh"
fetch() {
  local name="$1" url="$2" revision="$3" dest="$QMF_RUNTIME/baselines/$1"
  if [[ ! -d "$dest/.git" ]]; then
    mkdir -p "$dest"
    git -C "$dest" init -q
    git -C "$dest" remote add origin "$url"
  fi
  if ! git -C "$dest" rev-parse --verify HEAD >/dev/null 2>&1; then
    for attempt in 1 2 3; do
      if git -C "$dest" -c http.version=HTTP/1.1 fetch --depth 1 origin "$revision"; then break; fi
      sleep 2
    done
    git -C "$dest" checkout --detach "$revision"
  fi
  test "$(git -C "$dest" rev-parse HEAD)" = "$revision"
  test -z "$(git -C "$dest" status --porcelain --untracked-files=no)"
}
fetch learnedbench https://github.com/qyliu-hkust/learnedbench.git f029ec27d0296bc672c4c8229a46a6f7e98b0e0b
fetch bmtree https://github.com/gravesprite/Learned-BMTree.git 230ead0d82489b2f199baf165b0efa5f0c99b8c7
fetch morton-nd https://github.com/morton-nd/morton-nd.git 3795491a4aa3cdc916c8583094683f0d68df5bc0
if [[ ! -d "$QMF_RUNTIME/learnedbench-patched" ]]; then
  mkdir -p "$QMF_RUNTIME/learnedbench-patched"
  git -C "$QMF_RUNTIME/baselines/learnedbench" archive HEAD | tar -x -C "$QMF_RUNTIME/learnedbench-patched"
  patch -d "$QMF_RUNTIME/learnedbench-patched" -p1 < "$REPRO_ROOT/third_party/patches/flood-lisa-no-tpie.patch"
fi
