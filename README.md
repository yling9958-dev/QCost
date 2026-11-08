# QMF / Hybrid-QMF Source Code

This repository contains the project's own indexing and optimization source code,
required model parameters, and tests. It excludes external comparison indexes,
experiment records, logs, plotting directories, papers, datasets, and duplicate
release snapshots. This is the project's only README.

## Repository Layout

```text
src/
  python/
    qmapli/                         # R4 scoring, QMF construction, static indexes and queries
    hybrid_qmf/                     # Shared caching, recursive evaluation, QMF scheduling and incumbent feedback
    qmf_quantum_circuit_prototype.py # Optional small-scale gate-level prototype
  cpp/                              # C++17 query core, C API and query CLI
  postgres/                         # Optional PostgreSQL extension
models/r4.pt                        # Original R4 parameters, not a dataset
tests/                              # Source tests using temporary synthetic inputs
requirements.txt
requirements-circuit.txt             # Required only for the gate-level prototype
```

## Environment

Use Python 3.10, a C++17 compiler, and CMake 3.20 or later. Python dependencies
retain the original project's versions:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src/python"
```

## Building and Querying

Normalize input coordinates consistently. Point CSV files use the column names
`x,y,id`; training query files must include `xmin,ymin,xmax,ymax`. IDs must fit
within the uint32 range.

```bash
python -m qmapli.wg_qmf.build_static_qw_index \
  --mode uniform_qmf --r4-checkpoint models/r4.pt \
  --points /path/to/points.csv --train-queries /path/to/train.csv \
  --index /path/to/output/qmf.idx --metadata /path/to/output/metadata.json \
  --context-seed 20260910 --beta-leaf 1.2779084295340111e-09 \
  --beta-point 3.428255707467659 --max-depth 8 --min-leaf-size 256 \
  --max-leaves 128 --budget-factor 2.0

cmake -S src/cpp -B build
cmake --build build --parallel 2
build/bin/qmf_query --method qmap_uniform_qmf \
  --index /path/to/output/qmf.idx --queries /path/to/queries.csv \
  --output /path/to/output/query_ids.csv
```

The C++ query CSV column order is
`query_id,selectivity_group,split,xmin,ymin,xmax,ymax`.
The alternative build mode `wg_qmf` uses the query method `qmap_qw`.

Import Hybrid-QMF with `from hybrid_qmf import optimize`. It takes an N-by-2
point array, a Q-by-4 query array, and an R4 scorer implementing
`score_actions(points, queries, actions)`. The defaults are H=3 and K=4.
The full Hybrid-QMF implementation is retained without external comparison methods.

## Testing

```bash
PYTHONPATH=src/python python -m pytest -q -p no:cacheprovider tests
```

Tests generate small inputs in temporary directories and compile the native query
core without depending on experiment directories from the original workstation.
Gate-level tests run only when the dependencies in `requirements-circuit.txt` are
installed; otherwise, they are skipped automatically. Production QMF and
Hybrid-QMF scheduling runs on the CPU. The gate-level prototype validates only
small quantum circuits and does not demonstrate end-to-end quantum speedup.

The optional PostgreSQL extension requires PostgreSQL server development headers.
After building the C++ core above, run `make -C src/postgres with_llvm=no` to build
the shared library without requiring an additional LLVM C++ toolchain.
This command does not install the extension into a database.

## Datasets

Dataset files, preprocessed copies, and query workloads are not tracked in Git.
Use the following original sources and synthetic-data reference:

- GeoLife: [Microsoft GeoLife GPS Trajectories](https://www.microsoft.com/en-us/download/details.aspx?id=52367).
- Gowalla: [SNAP check-in data (.txt.gz)](https://snap.stanford.edu/data/loc-gowalla_totalCheckins.txt.gz).
- NYC Taxi: [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
- Skewed 2D (synthetic): [Qi et al., *Theoretically Optimal and Empirically Efficient R-trees with Strong Parallelizability*, PVLDB 2018](https://www.vldb.org/pvldb/vol11/p621-qi.pdf).
  Section 6.1 describes synthetic skewed-data generation; this is a reference
  paper, not a downloadable dataset archive.

These sources do not include this project's normalized datasets or query
workloads. Prepare inputs using the coordinate normalization and CSV schemas
described above before building an index.

## Licensing

This source-only cleanup does not grant a new license for the research code.
Without an explicit license, obtain permission from the project author before
public redistribution. External dependencies, including NumPy, PyTorch, and
PostgreSQL, remain subject to their respective licenses.
