#!/usr/bin/env bash
set -euo pipefail
export REPRO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export QMF_RUNTIME="${QMF_RUNTIME:-${QMF_RUNTIME_ROOT:-/var/tmp/qmf-repro}}"
mkdir -p "$QMF_RUNTIME"
case "$(stat -f -c %T "$QMF_RUNTIME")" in
  exfat|fuseblk|vfat|msdos) echo 'Runtime/build directory must be POSIX; set QMF_RUNTIME to /var/tmp/qmf-repro' >&2; exit 2;;
esac
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPRO_ROOT/src/common/python${PYTHONPATH:+:$PYTHONPATH}"
export QMAP_PROJECT_ROOT="$REPRO_ROOT"
export QMAP_BUILD_ROOT="$QMF_RUNTIME/build"
export QMAP_BASELINE_WORK="$QMF_RUNTIME/baselines"
export PGHOST="$QMF_RUNTIME/pg_socket" PGPORT="${QMF_PGPORT:-55439}" PGDATABASE=qmf_repro
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
unset QMAP_QMF_SIMD CMAKE_PREFIX_PATH LD_LIBRARY_PATH
export QMAP_QMF_SCALAR=1
