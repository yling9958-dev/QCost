#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
SOURCE="$QMF_RUNTIME/baselines/bmtree"
test "$(git -C "$SOURCE" rev-parse HEAD)" = 230ead0d82489b2f199baf165b0efa5f0c99b8c7
TARGET="$(mktemp -d "$QMF_RUNTIME/bmtree-work-XXXXXX")"
git -C "$SOURCE" archive HEAD | tar -x -C "$TARGET"
printf '%s\n' "$TARGET"
