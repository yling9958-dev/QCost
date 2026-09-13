#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
if [[ -f "$QMF_RUNTIME/pg_data/PG_VERSION" ]]; then
  "$(pg_config --bindir)/pg_ctl" -D "$QMF_RUNTIME/pg_data" -m fast -w stop
fi
echo 'Runtime retained for audit; no original/source files are deleted.'
