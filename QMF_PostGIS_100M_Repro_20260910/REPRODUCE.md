# Fresh-Machine Reproduction

## Prerequisites

Use Ubuntu 22.04/Linux and a POSIX runtime filesystem. Install the system
packages recorded in `environment/apt_packages.txt` and Python dependencies in
`environment/python_transitive.lock`. The reference environment is PostgreSQL
14.24, PostGIS 3.2.0, Boost 1.74, and GCC 11.4. Exact installed versions are
recorded under `environment/`.

Allow approximately 15 GiB of free runtime disk and preferably 16-32 GiB RAM.
Set `QMF_RUNTIME` to a fresh POSIX directory and `QMF_PGPORT` to an unused port
when the defaults `/var/tmp/qmf-repro` and 55439 are unsuitable. Do not share a
runtime directory between concurrent runs.

## Internal FULL Package

The authoritative input is `data/frozen/geolife_100m.csv`. Verify it directly:

```bash
bash scripts/00_verify_archive.sh
bash data/verify_geolife_100m.sh
bash scripts/run_tests.sh
bash scripts/reproduce_all.sh --quick
bash scripts/reproduce_all.sh --full
```

The reproduction scripts fail if the local file is absent or wrong. They do not
inspect environment variables for historical CSV paths and do not search any
other project directory.

## Public Recovery

The public archive excludes GeoLife data. After reviewing
`data/LICENSE_DATASET.md`, reconstruct it explicitly with:

```bash
bash data/recovery/fetch_geolife.sh
```

Set `QMF_GEOLIFE_ARCHIVE` to a lawfully acquired official GeoLife 1.3 ZIP to
avoid downloading it. Recovery verifies the archive byte count and SHA, the
18,670-entry trajectory order, and the reconstructed dataset byte count, SHA,
record count, coordinate uniqueness, and bounds. It never requires the old
expanded 4.2 GiB processed CSV.

## Frozen Protocol

Quick mode runs one complete QMF build and all 5,000 correctness queries but
only one timing repetition. Full mode runs all eight primary methods, three
build repetitions where specified, 40,000 correctness executions, 1,000 warmup
queries per method, 15,000 measured queries per method per repetition, and five
timing repetitions: 600,000 measured executions total.

Exact functional requirements are the dataset, query, checkpoint, logical-tree,
serialized-index, and returned-ID hashes. Performance diagnostics use: build
+/-25%, persistent size <=0.1%, mean +/-20%, P95 +/-25%, P99 +/-30%, QPS
+/-20%, and peak memory +/-20%. QMF must retain rank 1 for size among the five
comparable persistent methods and for mean, P95, P99, and QPS.

Results are written to `$QMF_RUNTIME/results/current`. Stop the dedicated local
PostgreSQL cluster with `bash scripts/clean_runtime.sh`; the script retains
runtime evidence and does not touch unrelated PostgreSQL instances.
