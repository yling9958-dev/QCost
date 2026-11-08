# Q-COST / QMF / Hybrid-QMF Reproducible Project

This repository contains the runnable project, original trained controllers,
training code, experiment implementations, frozen configurations, and tests.
It has one README, in English. Datasets, query payloads, logs, plotting directories,
generated indexes, build outputs, and duplicate release snapshots are not tracked.
External comparison-index implementations remain excluded.

## Included Components

```text
models/                         15 original seed-0 checkpoints, hashes and CST normalization
configs/                        Training/index parameters, seeds and frozen input identities
references/                     80 original offline Exact references (no point/query data)
src/python/qmapli/              Model definitions, training losses, features and production QMF
src/python/hybrid_qmf/          Full Hybrid-QMF public API
src/python/qcost_experiments/   Separate original ablation and instrumented selection implementations
src/python/qcost_repro/         Portable preparation, training, validation and native bindings
src/cpp/                       C++17 query core, C API and query CLI
src/postgres/                  Optional PostgreSQL extension
reproduce/                     Runnable preparation, training, experiment and verification commands
tests/                         Unit, model, training and end-to-end tests
licenses/                      Original license notice for restored QMap-LI source
```

### Why More Than One Model Is Included

Production QMF uses the same frozen `models/r4.pt` across datasets.
QMF and Hybrid-QMF are search algorithms, not separately trained neural models,
so they do not each require another checkpoint.

The original training run also saved these 14 controllers, now included together
with their definitions and training code:

```text
aq.pt          aq_zeroent.pt   qf.pt          qf_gap.pt
noq_base.pt    noq_gap.pt      frozenq.pt     caqf.pt
qb3.pt         cst.pt          qold.pt        c2.pt
c4.pt          c5.pt
```

All 15 files are original seed-0 artifacts, copied without retraining or changing
their contents. `models/manifest.json` records each name, seed, size and SHA-256.
CST additionally requires `models/cst_normalizer.json`, recovered from the original
development training split. Model seeds 1-4 can be trained with the commands below;
their historical checkpoints were not found and are not fabricated.
The R0-R4 representation-study definitions and training entry point are also
included, but these study variants are not interchangeable with production R4
checkpoint files.

## Environment and Quick Start

Use Linux, Python 3.10, a C++17 compiler and CMake 3.20 or later.
A GPU is not required. Install the pinned Python dependencies, then expose the
source package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip "setuptools>=64" wheel
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src/python"
# Optional editable package and qcost-* command installation:
python -m pip install --no-build-isolation --no-deps -e .
```

Validate the project and run a small complete workflow without downloading data:

```bash
python -B reproduce/check_project.py
python -B -m pytest -q -p no:cacheprovider tests
QCOST_RUN=$(mktemp -d /tmp/qcost-run.XXXXXX)
python -B reproduce/smoke.py --output "$QCOST_RUN/smoke"
```

The smoke workflow verifies all 15 original models, prepares isolated training
inputs, trains a new R4 model, builds the native library, builds both QMF index
modes, checks exact returned IDs and counts, and runs five Hybrid ablations plus
four selection/feedback variants. It writes only to a fresh output directory.
Smoke results are not published paper measurements.

Gate-level tests are optional: install `requirements-circuit.txt` to enable them.
Otherwise, the quantum-circuit test module is skipped. Production QMF and
Hybrid-QMF scheduling runs on the CPU; the optional gate-level prototype does
not establish end-to-end quantum speedup.

## Dataset Sources and Preparation

Datasets are obtained externally, not uploaded to this repository.

- GeoLife: [Microsoft GeoLife GPS Trajectories](https://www.microsoft.com/en-us/download/details.aspx?id=52367).
- Gowalla: [SNAP check-in data (.txt.gz)](https://snap.stanford.edu/data/loc-gowalla_totalCheckins.txt.gz).
- NYC Taxi: [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
- Skewed 2D: [Qi et al., *Theoretically Optimal and Empirically Efficient R-trees with Strong Parallelizability*, PVLDB 2018](https://www.vldb.org/pvldb/vol11/p621-qi.pdf).
  Section 6.1 is the synthetic skewed-data generation reference, not a dataset archive.

Download the desired source separately and select a fresh output directory:

```bash
# GeoLife ZIP: longitude/latitude extracted from sorted .plt members.
python reproduce/prepare_data.py prepare --format geolife \
  --source /path/to/Geolife.zip --output /path/to/new-geolife

# Gowalla compressed check-ins: longitude/latitude columns.
python reproduce/prepare_data.py prepare --format gowalla \
  --source /path/to/loc-gowalla_totalCheckins.txt.gz --output /path/to/new-gowalla

# Original processed x,y CSV, or any CSV with explicit coordinate column names.
python reproduce/prepare_data.py prepare --format csv \
  --source /path/to/raw-points.csv --x-column x --y-column y \
  --output /path/to/new-points

# New synthetic data: (x, y) -> (x, y**9), with an explicit seed.
python reproduce/prepare_data.py prepare --format skewed --points 100000 \
  --seed 20260910 --power 9 --output /path/to/new-skewed
```

For NYC Taxi, supply a source that actually has longitude/latitude fields, using
`--x-column pickup_longitude --y-column pickup_latitude` where appropriate.
Zone IDs are not coordinates; a zone-ID-only trip file cannot be substituted.

Preparation performs two bounded-memory passes, rejects invalid/nonfinite inputs,
retains source-row IDs, and writes `points.csv` and a hash/normalization manifest.
There is no silent filtering, deduplication or replication. `--limit N` creates
an explicitly recorded development subset, not a full-scale dataset.

The retained original GeoLife recovery recipe can reconstruct the historical
100 MiB prefix byte-for-byte from the exact official archive and trajectory order:

```bash
python reproduce/recover_geolife.py --archive /path/to/Geolife.zip \
  --order configs/geolife_plt_order.txt --output /path/to/new-geolife-100m.csv
```

This recipe checks the source archive and output hashes. It does not reconstruct
the later 181-million-point processed dataset.

## Production Index Reproduction

Generate the original full-scale query protocol from the prepared coordinate
domain, then build and validate an index:

```bash
python reproduce/prepare_data.py queries --metadata /path/to/new-points/metadata.json \
  --output /path/to/new-queries
python reproduce/run_index.py --points /path/to/new-points/points.csv \
  --queries /path/to/new-queries --output /path/to/new-qmf-run \
  --mode uniform_qmf --repetitions 5
```

The query generator retains seed 20260910 and the split counts: 1,000 training,
1,000 validation, 1,000 correctness, 300 warmup and 3,000 performance queries.
It preserves the clipped rectangle/aspect and float32-midpoint boundary rules.
Its inputs determine the actual workload identity; generated workloads are not
assumed to be the historical files without matching hashes.

The runner compiles the native core, builds using `configs/qmf_frozen.yaml`,
checks complete returned-ID sets and the count kernel, performs warmup and five
timing repetitions, and emits a new metrics manifest. `--mode wg_qmf` selects
the other supported production mode. Exact truth checks use the native index's
stored float32 point semantics. Full-data correctness is intentionally expensive.

New timings measure warmed native count calls through Python/ctypes, including
FFI overhead, excluding input I/O and truth checks. The recorded RSS is the whole
Python-process high-water mark. These scopes are explicit and are not the original
paper's SQL timing or memory estimator. Neither this workflow nor the smoke check
silently replaces historical measurements.

For direct building/querying without the reproduction runner:

```bash
python -m qmapli.wg_qmf.build_static_qw_index --help
cmake -S src/cpp -B build
cmake --build build --parallel 2
build/bin/qmf_query --method qmap_uniform_qmf --index /path/to/qmf.idx \
  --queries /path/to/new-queries/correctness.csv --output /path/to/new-ids.csv
```

Point CSV columns are `id,x,y`; training query files contain
`xmin,ymin,xmax,ymax`. The native query CLI expects
`query_id,selectivity_group,split,xmin,ymin,xmax,ymax` as its first seven columns.
The `wg_qmf` builder corresponds to native query method `qmap_qw`.

## Training the Original Model Family

Prepare fresh tensors using the retained synthetic distributions, query isolation,
feature/oracle definitions and development/confirmatory seeds:

```bash
python reproduce/train_models.py prepare --output /path/to/new-training-inputs
# Add --smoke for a small development-only functional check.
# Optional explicit external roots:
# --geolife-development /path/to/dev-root.csv
# --geolife-confirmatory /path/to/confirm-root.csv

python reproduce/train_models.py train \
  --development /path/to/new-training-inputs/development.npz \
  --confirmatory /path/to/new-training-inputs/confirmatory.npz \
  --output /path/to/new-models
```

By default this trains all 15 architectures with seeds 0-4 and the original
controller hyperparameters. Use `--models R4 QF AQ`, `--seeds 0` or `--epochs 1`
for explicitly smaller runs. The complete model families, ranking/gap/top-1 losses,
Adam fitting, validation selection, feature preparation and CST normalization
are included. New checkpoints never overwrite the originals in `models/`.

The default preparation uses the original synthetic protocol. Historical GeoLife
root selection depended on external sample/membership inputs; providing arbitrary
new roots does not reproduce their identities. Exact historical prepared tensors
can be supplied in the safe NPZ schema implemented by
`qcost_repro.training.save_prepared/load_prepared`. Bitwise training equality
across software/threading environments is not promised.

To train representation-study variants:

```bash
python reproduce/train_models.py train --representations --models R0 R1 R2 R3 R4 \
  --development /path/to/new-training-inputs/development.npz \
  --confirmatory /path/to/new-training-inputs/confirmatory.npz \
  --output /path/to/new-representation-models
```

This uses the Stage-A training hyperparameters in
`configs/representation_training.yaml`. These outputs are labeled study artifacts,
not replacements for the original production checkpoints.

## Hybrid-QMF and Frozen Node Experiments

The public API is `from hybrid_qmf import optimize`. Supply N-by-2 points,
Q-by-4 queries and an R4 scorer implementing
`score_actions(points, queries, actions)`. The full algorithm defaults to H=3,
K=4. The separate original experiment implementations are preserved because their
instrumentation/accounting differs; their timings must not be pooled.

For the original 40-node cohort or the additional 40 validation nodes, supply
the exact external `NODE_ID/input.npz` files identified in
`configs/NODE_MANIFEST.json`:

```bash
python reproduce/run_optimizer.py --mode ablation \
  --inputs-root /path/to/external-nodes --output /path/to/new-ablation
python reproduce/run_optimizer.py --mode selection --cohort Both \
  --inputs-root /path/to/external-nodes --output /path/to/new-selection
python reproduce/analyze_new_runs.py --runs /path/to/new-selection \
  --output /path/to/new-selection-analysis
```

Ablations are Full, Random, NoCache, NoFeedback and Enumeration. Selection variants
are QF, RF, QN and RN. The 30 original seeds and frozen node-level T_exact budgets
are retained. The runner checks input hashes, runs one experiment at a time,
refuses incompatible resume manifests, and reads offline Exact references only
after optimization returns. It verifies returned plans independently.
`qcost_repro.recursive_exact` retains the original independent Exact solver.

Use `--limit-nodes 2 --limit-seeds 1 --protocol B` for a partial ablation check.
Partial runs and safety timeouts are explicitly recorded, not complete campaigns.
The data-free smoke command exercises the same implementations with new synthetic
inputs when the exact external node files are unavailable.

## PostgreSQL Extension

After building the C++ core, install PostgreSQL server development headers and run:

```bash
make -C src/postgres with_llvm=no
```

This builds the shared module without requiring an LLVM C++ toolchain and does
not install it into a database. Native extension installation/database creation
must be performed explicitly in an appropriate environment.

## Reproduction Boundaries and Licensing

All available original controller checkpoints and the runnable source workflows
are included. Logs, plots and spatial inputs remain excluded as requested.
The four official source/reference links are not downloads of the exact historical
normalized datasets, fixed node samples, or workload files. Their identities and
hashes are retained in `configs/FULLSCALE_MANIFEST.json` and
`configs/NODE_MANIFEST.json`. No full-scale experiment or exact reconstruction of
all historical inputs is claimed merely because the project passes its tests.

The original QMap-LI license notice for restored model/training source is retained
in `licenses/QMap-LI.LICENSE`. This packaging does not assign a new license to
other research artifacts. External dependencies remain subject to their own licenses.
