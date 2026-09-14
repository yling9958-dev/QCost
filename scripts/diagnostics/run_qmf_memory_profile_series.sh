#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "usage: $0 INPUT_ROOT OUTPUT_ROOT [QUERY_CSV]" >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INPUT_ROOT="$1"
OUTPUT_ROOT="$2"
QUERY_CSV="${3:-$PROJECT_ROOT/results/four_dataset_paper_protocol_20260911/02_queries/geolife_2d_4p2G/train_normalized.csv}"

if [ ! -f "$QUERY_CSV" ]; then
  echo "query CSV not found: $QUERY_CSV" >&2
  exit 2
fi

profiles=(
  "1000000:1m"
  "5000000:5m"
  "10000000:10m"
  "25000000:25m"
  "50000000:50m"
)

for profile in "${profiles[@]}"; do
  count="${profile%%:*}"
  slug="${profile##*:}"
  input="$INPUT_ROOT/geolife_${slug}.csv"
  output="$OUTPUT_ROOT/$slug"
  unit="qmf-audit-profile-20260914-$slug"
  if [ ! -f "$input" ]; then
    echo "profile input not found: $input" >&2
    exit 2
  fi
  if [ -e "$output/time.txt" ] || [ -e "$output/qmap_uniform_qmf.idx" ]; then
    echo "refusing to overwrite profile evidence: $output" >&2
    exit 2
  fi
  mkdir -p "$output"
  systemd-run --user --wait --collect --unit="$unit" \
    --property=MemoryAccounting=yes \
    --property=MemoryHigh=23622320128 \
    --property=MemoryMax=25769803776 \
    --property=MemorySwapMax=0 \
    --property=StandardOutput=journal \
    --property=StandardError=journal \
    bash "$PROJECT_ROOT/scripts/diagnostics/run_qmf_memory_profile.sh" \
      "$count" "$input" "$output" "$QUERY_CSV"
done
