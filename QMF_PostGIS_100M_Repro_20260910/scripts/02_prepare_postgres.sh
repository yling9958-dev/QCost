#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
PGBIN="$(pg_config --bindir)"
mkdir -p "$PGHOST"
if [[ ! -f "$QMF_RUNTIME/pg_data/PG_VERSION" ]]; then
  "$PGBIN/initdb" -D "$QMF_RUNTIME/pg_data" --auth-local=trust --auth-host=scram-sha-256 --encoding=UTF8 --locale=C.UTF-8
  cp "$REPRO_ROOT/config/postgres.conf.repro" "$QMF_RUNTIME/pg_data/repro.conf"
  printf "\ninclude = 'repro.conf'\n" >> "$QMF_RUNTIME/pg_data/postgresql.conf"
fi
if ! "$PGBIN/pg_ctl" -D "$QMF_RUNTIME/pg_data" status >/dev/null 2>&1; then
  "$PGBIN/pg_ctl" -D "$QMF_RUNTIME/pg_data" -l "$QMF_RUNTIME/postgres.log" -o "-k '$PGHOST' -p $PGPORT -c listen_addresses=''" -w start
fi
if ! psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='qmf_repro'" | grep -qx 1; then
  createdb qmf_repro
fi
psql -X -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
python -m qmapli.repro install-sql
