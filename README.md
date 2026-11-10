# Q-COST: Quantum-Inspired Cost Optimization of Spatial Trees for Workload-Aware Learned Indexing

## Project Overview

Q-COST optimizes joint spatial-subtree configurations using workload-aware candidate ranking, recursive conditional costs, and quantum-inspired minimum-finding search. This distribution assembles the existing research implementations, original pretrained controllers, frozen experiment identities, native query engines, experiment adapters, and independent Qiskit Aer validation.

The production index commits a root partition and replans its children. Its frozen default is **Analytic QMF**, with planning depth H=3 and candidate width K=4. Hybrid-QMF is supplied as a separate optimizer and as the original controlled-study implementations. Classical index construction does not execute quantum circuits. Gate experiments validate coherent operations over classically supplied cost tables; they do not demonstrate an end-to-end quantum speedup.

This is an audited reproduction distribution, not a claim that every historical measurement has been rerun. QUICK executes actual algorithms on explicitly identified small inputs. FULL retains the original algorithm parameters, dataset identities, cohorts, budgets, and seeds where recoverable. External node payloads, historical training samples, and some figure-specific campaign inputs still require the authors' artifacts. These limitations are described below and in `docs/feature_status.json` and `docs/validation.json`.

## Key Features

- Two-dimensional input normalization, workload features, frozen R4 scoring, legal Top-K partitions, and root-commit/replan construction.
- Joint configurations, leaf-visit and candidate-scan costs, conditional-state caching, recursive exact optimization, and root selection.
- Analytic QMF, Random Search, deterministic Beam Search, cached anytime and Hybrid-QMF optimizers; cache and incumbent-feedback ablations.
- Portable C++17 serialization/loading and exact range-ID/count queries, with fresh latency, throughput, size, build-time and memory measurements.
- Original controller definitions/training, 15 original seed-0 checkpoints, 80 offline node references, and the actual small FULL query workload files.
- Independent reversible QROM, threshold comparison, phase oracle, diffusion, uncomputation, Aer shots and elementary-gate resource accounting.

## Repository Structure

```text
README.md                      Sole README and all usage instructions
LICENSE                        Pending author confirmation; no new license grant
requirements*.txt              Classical, plotting, baseline and independent quantum environments
environment.yml                Classical Conda environment
configs/                       Frozen algorithms, seeds, data hashes, node identities and training protocols
models/                        15 checkpoints, model manifest and CST normalizer
references/                    Offline Exact references; read only after search returns
src/python/qmapli/             Features, candidate generation, scoring, training and production index
src/python/hybrid_qmf/          Hybrid-QMF public API
src/python/qcost_experiments/   Original ablation/selection and controlled-comparison implementations
src/python/qcost_repro/         Data preparation, training, native bindings and validation
src/python/qmf_quantum/         Independent formal gate-validation implementation
src/cpp/                       Portable native index runtime and query CLI
src/baselines/                 Research baseline adapters and recorded Flood/LISA patch
src/postgres/                  Optional QMF extension and unchanged formal C++ libpq client
reproduce/                     Executable workflows, audits, plotting and packaging tools
experiments/workloads/         20 original normalized workload CSVs, verified byte for byte
experiments/plotting/          Final plotting sources and small curated historical scalar exports
tests/                         Classical/native/model tests and independent quantum tests
docs/                          Machine-readable provenance, feature status and executed validation
licenses/                      Preserved upstream notice
MANIFEST.sha256                Hashes of distribution files, excluding the manifest itself
```

Large point datasets, generated indexes, experiment run directories, plots, logs, third-party worktrees and virtual environments are excluded. Historical scalar plotting inputs are explicitly distinguished from fresh measurements. Plotting inputs are not used as algorithm outputs or as search oracles.

## Requirements

The validated classical environment is Linux x86-64, Python 3.10.12, NumPy 1.26.4, pandas 2.3.3, SciPy 1.15.3, PyTorch 2.4.1, pytest 8.4.2 and PyYAML 6.0.3. C++ requires CMake >=3.20 and a C++17 compiler; validation used CMake 3.22.1 and GCC 11.4. A GPU is optional.

Native comparison baselines additionally require Git, patch, Boost headers, libpq development headers/libraries and PostgreSQL development tools. Database experiments require a separately prepared PostgreSQL/PostGIS database; validation used PostgreSQL 14.24 and PostGIS 3.2. Compilation of the optional QMF extension needs matching PostgreSQL server development headers.

The original quantum environment uses **NumPy 2.2.6, Qiskit 2.5.2 and qiskit-aer 0.17.2**. Install it independently: it conflicts with the pinned classical NumPy version. The gate-only environment does not need PyTorch.

QUICK uses thousands of points and CPU execution. The four FULL raw CSVs total 18,085,018,618 bytes; their normalized CSVs require approximately 37 GB more, before indexes, database tables and experiment outputs. Full-scale memory/time depend strongly on the method. The original database campaign used a 24 GiB memory limit, a 22 GiB soft target and 43,200-second phase timeouts; the portable wrappers do not impose those original systemd/cgroup settings. Node-study provenance records four threads, an 8 GiB limit and a 300-second node limit; fresh portable wrappers record their own timing/thread scope. Use sufficient dedicated disk and memory for a FULL campaign.

## Installation

Run commands from the extracted project root. On Debian/Ubuntu, native prerequisites can be installed with:

```bash
sudo apt-get install python3-venv build-essential cmake git patch libboost-dev libpq-dev postgresql-server-dev-14
```

Use the matching server development version if PostgreSQL differs. PostgreSQL/PostGIS server installation and database credentials are managed separately.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip 'setuptools>=64' wheel
python -m pip install -r requirements.txt
python -m pip install --no-build-isolation --no-deps -e .
python -B reproduce/check_environment.py
```

Alternatively, `environment.yml` defines the classical Conda environment. Install `requirements-analysis.txt` for plotting, and `requirements-baselines.txt` for psycopg2 database wrappers. All Python workflows locate source, models and configurations relative to their own project root. Dataset, node and output paths are command-line arguments. Prefer fresh output directories; most runners refuse to overwrite an existing run.

## Datasets

GeoLife, Gowalla and NYC Taxi are real-coordinate benchmark inputs; Skewed 2D is the frozen synthetic benchmark input. Their processed benchmark sizes are not the sizes of the providers' original archives. QUICK generated data and development prefixes are labelled as such and do not replace these FULL inputs.

## Dataset Download

The supplied [QW-index dataset document](https://anonymous.4open.science/r/QW-index-56DD/database/RAADME.md) resolves to this [raw metadata endpoint](https://anonymous.4open.science/api/repo/QW-index-56DD/file/database/RAADME.md). The actual links below were extracted from that document; all four returned HTTP 200 with matching content lengths during packaging. Remote complete bodies were not downloaded again. The existing local raw files were fully hashed and matched the frozen identities. Check every newly downloaded file locally before FULL execution.

| Dataset | Download | Points | Raw bytes |
|---|---|---:|---:|
| GeoLife | [geolife_2d_4p2G.csv](https://qindex.bj.bcebos.com/database/geolife_2d_4p2G.csv) | 181,000,000 | 4,521,210,875 |
| Gowalla | [gowalla_2d_4p2G.csv](https://qindex.bj.bcebos.com/database/gowalla_2d_4p2G.csv) | 183,000,000 | 4,529,100,291 |
| NYC Taxi | [nyc_taxi_2d_4p2G.csv](https://qindex.bj.bcebos.com/database/nyc_taxi_2d_4p2G.csv) | 181,000,000 | 4,525,000,004 |
| Skewed 2D | [skewed_2d.csv](https://qindex.bj.bcebos.com/database/skewed_2d.csv) | 204,986,702 | 4,509,707,448 |

Obtain data under the source providers' terms. Original sources are [Microsoft GeoLife](https://www.microsoft.com/en-us/download/details.aspx?id=52367), [SNAP Gowalla](https://snap.stanford.edu/data/loc-gowalla.html) and [NYC TLC Trip Records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page). TLC location-zone identifiers alone are not longitude/latitude. The skewed-distribution methodological reference is [Qi et al., PVLDB 2018](https://www.vldb.org/pvldb/vol11/p621-qi.pdf); FULL uses the frozen CSV above, rather than a newly generated approximation. Do not apply the external repository's separate 200,000-point sampling recipe to Q-COST FULL.

```bash
mkdir -p data/raw
curl -fL --output data/raw/geolife_2d_4p2G.csv https://qindex.bj.bcebos.com/database/geolife_2d_4p2G.csv
curl -fL --output data/raw/gowalla_2d_4p2G.csv https://qindex.bj.bcebos.com/database/gowalla_2d_4p2G.csv
curl -fL --output data/raw/nyc_taxi_2d_4p2G.csv https://qindex.bj.bcebos.com/database/nyc_taxi_2d_4p2G.csv
curl -fL --output data/raw/skewed_2d.csv https://qindex.bj.bcebos.com/database/skewed_2d.csv
python -B reproduce/prepare_external.py --raw-root data/raw --output data/prepared --check-only
python -B reproduce/prepare_external.py --raw-root data/raw --output data/prepared
```

The original converter performs two-pass float64 affine min-max normalization, preserves source-row order as uint32 IDs, and does not filter, deduplicate or replicate points. FULL checks raw SHA256/size, point counts, bounds and normalized SHA256 against `configs/input_identities.json`, then copies the actual included workloads unchanged. Native stored coordinates use float32; returned IDs and counts are checked against that stored representation with inclusive rectangle bounds.

```text
data/
  raw/{geolife_2d_4p2G,gowalla_2d_4p2G,nyc_taxi_2d_4p2G,skewed_2d}.csv
  prepared/
    geolife/
      points/points.csv         id,x,y; normalized coordinates
      points/metadata.json
      queries/{train,validation,correctness,warmup,performance}.csv
      queries/manifest.json
      preparation.json
    gowalla/                   Same layout
    nyc_taxi/
    skewed_2d/
  nodes/NODE_ID/input.npz       External frozen optimizer inputs
```

A small real-data development run can use `--datasets geolife --limit 8192` with a new output such as `data/development`. It uses prefix-specific normalization and regenerated development queries; FULL rejects that input. `reproduce/prepare_data.py` also retains CSV/GeoLife ZIP/Gowalla conversion and explicit synthetic generation. These alternate sources and generators produce new inputs and cannot reconstruct the frozen FULL files by assumption.

The separate historical **100 MiB GeoLife prefix** can be recovered from the official GeoLife 1.3 ZIP and the included trajectory-order manifest:

```bash
python -B reproduce/recover_geolife.py --archive data/raw/Geolife_Trajectories_1.3.zip --order configs/geolife_plt_order.txt --output data/recovery/geolife_100m.csv
```

This verifies the original archive/order/output hashes. Its 4,197,223 points are an earlier input; it does not reconstruct the later 181-million-point FULL CSV or the missing training-root memberships.

## Pretrained Models

`models/r4.pt` is the same frozen production prior for all four datasets. Its SHA256 is `0d10709b1440549e2aec605b1b68754aff0e8fbb9d793e0f31a64df9da213b5d`. `models/manifest.json` records the original 15 checkpoints: AQ, AQ-ZeroEnt, QF, QF-Gap, NoQ-Base, NoQ-Gap, FrozenQ, CAQF, QB3, CST, Qold, C2, C4, C5 and R4. All are seed 0; none was retrained for this release. CST also uses the included normalizer.

The retained factories strictly load state dictionaries, then check finite inference for 46 scalar features and a 7x4x4 spatial tensor per action. Feature extraction, normalization and model definitions are in `qmapli`; use the provided scorer instead of constructing arbitrary feature orders. Only trusted project checkpoint files should be loaded.

```bash
python -B -m qcost_repro.models
python -B reproduce/train_models.py prepare --smoke --output runs/training-smoke
python -B reproduce/train_models.py train --development runs/training-smoke/development.npz --confirmatory runs/training-smoke/confirmatory.npz --models R4 --seeds 0 --epochs 1 --output runs/trained-smoke
```

For full new training, omit `--smoke`/`--epochs`, use the retained training configurations and optionally supply separate `--geolife-development` and `--geolife-confirmatory` CSV roots to `prepare`. The default training models/seeds come from `configs/controller_training.yaml`; `train --representations` uses `configs/representation_training.yaml`. These commands generate new training results. Historical model seeds 1–4, exact historical GeoLife training membership and referenced Stage-A freeze documents were not found. Their old provenance fields remain in training YAML, but are not read as runtime input paths. Bitwise recovery of missing historical checkpoints is therefore not claimed. Production reproduction uses the supplied verified R4 weight.

## Quick Start

```bash
python -B reproduce/check_release.py
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider
python -B reproduce/run.py QUICK --output runs/quick
```

QUICK verifies all 15 models, trains R4 for one epoch on isolated generated training inputs, builds/reloads native indexes for both retained index modes, checks exact returned IDs and counts, and runs five Hybrid ablations and four selection/feedback variants. It also executes H=3/K=4 budget search on 4,096 explicitly synthetic points, seven optimizer/cache variants, and the nine H/K grid cells. No downloaded dataset is required. Metrics and validation receipts are written under `runs/quick`; these are new measurements, not paper numbers. Quantum validation has the separate entry below.

For a real-data prefix after downloading GeoLife:

```bash
python -B reproduce/prepare_external.py --raw-root data/raw --datasets geolife --limit 8192 --output data/development
python -B reproduce/run_index.py --points data/development/geolife/points/points.csv --queries data/development/geolife/queries --output runs/index-development
python -B reproduce/run_strategies.py --mode QUICK --points data/development/geolife/points/points.csv --queries data/development/geolife/queries --output runs/strategies-development
```

## Reproducing Experiments

The unified classical runner supports independently selectable FULL tasks:

```bash
python -B reproduce/run.py FULL --tasks indexes --data-root data/prepared --output runs/full-indexes
python -B reproduce/run.py FULL --tasks search efficiency sensitivity ablation selection --inputs-root data/nodes --output runs/full-nodes
```

The first command requires all four verified FULL datasets and workloads. The second requires the 40 Original nodes plus the 40 Validation nodes for selection diagnostics. `configs/NODE_MANIFEST.json` specifies each relative `NODE_ID/input.npz`, SHA256, cohort and offline reference. NPZ payloads contain numeric `points` (N,2) and `queries` (M,4), opened with `allow_pickle=False`. The package preserves all 80 answer references but excludes the point/query payloads. **No public download link for these exact node NPZ files was found in the supplied dataset repository. Obtain the frozen node artifacts from the authors; raw CSV downloads do not automatically supply them.** Offline references are opened only after optimization, never passed into search.

`reproduce/select_frozen_nodes.py` retains the original outcome-blind node census and rank-feature maximin ordering. With the authors' saved 20k samples and trace memberships laid out under an external root's `data/`, it can reconstruct the candidate order:

```bash
python -B reproduce/select_frozen_nodes.py --source-root data/original-node-source --output runs/node-census
```

This is a candidate-order reconstruction, not a substitute for missing source memberships or the final feasible-node NPZ artifacts.

Individual real implementations can be run as follows:

```bash
python -B reproduce/run_index.py --points data/prepared/geolife/points/points.csv --queries data/prepared/geolife/queries --output runs/qcost-geolife --repetitions 5
python -B reproduce/run_studies.py --task search --mode FULL --inputs-root data/nodes --output runs/search
python -B reproduce/run_studies.py --task efficiency --mode FULL --inputs-root data/nodes --output runs/efficiency
python -B reproduce/run_studies.py --task sensitivity --mode FULL --inputs-root data/nodes --output runs/sensitivity
python -B reproduce/run_optimizer.py --mode ablation --protocol both --inputs-root data/nodes --output runs/ablation
python -B reproduce/run_optimizer.py --mode selection --cohort Both --inputs-root data/nodes --output runs/selection
python -B reproduce/analyze_new_runs.py --runs runs/ablation --output runs/ablation-analysis
```

`run_studies.py --task efficiency` covers Recursive Exact, Analytic QMF, Cached Anytime, Hybrid-QMF and three cache-level ablations. The controlled builder covers R4 Greedy, Cost-H1, Recursive Exact and Analytic QMF using the actual original four-strategy implementation:

```bash
python -B reproduce/run_strategies.py --mode FULL --points data/controlled/geolife/points.csv --queries data/controlled/geolife/queries --output runs/construction
```

This requires the original **20,000-point** controlled sample and its queries, provided externally. It uses all five original seeds 11,23,37,51,73. A CSV with 20,000 rows alone does not establish historical sample membership; the runner records this identity limitation. QUICK accepts a labelled small development sample. Do not relabel the development prefix as the historical controlled sample.

### Traditional and learned-index baselines

```bash
python -m pip install -r requirements-baselines.txt
python -B reproduce/fetch_baselines.py --output external
python -B reproduce/run_baselines.py --points data/prepared/geolife/points/points.csv --queries data/prepared/geolife/queries --external external --output runs/baselines
python -B reproduce/export_bmtree_model.py --source external/baselines/bmtree --points data/prepared/geolife/points/points.csv --train-queries data/prepared/geolife/queries/train.csv --output runs/bmtree.model --metadata runs/bmtree-training.json --training-points 2000 --depth 4 --rollouts 2 --seed 1
python -B reproduce/run_baselines.py --points data/prepared/geolife/points/points.csv --queries data/prepared/geolife/queries --external external --methods bmtree --bmtree-model runs/bmtree.model --output runs/bmtree
```

The fetcher locks actual commits of [learnedbench](https://github.com/qyliu-hkust/learnedbench), [Learned-BMTree](https://github.com/gravesprite/Learned-BMTree) and [morton-nd](https://github.com/morton-nd/morton-nd), as recorded in `configs/baseline_dependencies.json`. It applies the original Flood/LISA duplicate-handling and no-TPIE compatibility patch in a separate copy. Flood and LISA use those adapted implementations; BMTree uses the authors' Tree/BMTEnv/MCTS code and a real model-code export. Tsunami and LMSFC are the existing local research reproductions, not official author implementations. Boost R*-tree is distinct from PostGIS GiST. These provenance qualifications also apply to the retained paper scalar exports. Third-party licenses must be checked at their upstream revisions before redistribution.

The optional QMF PostgreSQL extension can be compiled without installing it into a server:

```bash
python -B reproduce/build_postgres.py --output runs/postgres-extension
```

This builds the shared extension with PGXS and disables optional LLVM bitcode generation, which is unnecessary for the compiled runtime. Deploying functions into a separate experiment database requires the matching server version and appropriate database privileges; `src/postgres/qmap_benchmark--1.0.sql` provides the function definitions.

Set `QCOST_PG_DSN` to a database with PostGIS installed, using your local credential management. The following use an automatically created private table/schema and remove their own database objects on completion:

```bash
python -B reproduce/run_postgis.py --points data/prepared/geolife/points/points.csv --queries data/prepared/geolife/queries --output runs/postgis --repetitions 5
python -B reproduce/run_paper_sql.py --points data/prepared/geolife/points/points.csv --queries data/prepared/geolife/queries --output runs/paper-sql-postgis
```

`run_postgis.py` measures a psycopg2 client. `run_paper_sql.py` compiles the unchanged formal C++ libpq client: 1,000 bidirectional-ID correctness checks, 300 warmups, 3,000 performance queries and five rounds, prepared statements, jit off and no parallel gather. Its `--table schema.table` alternative operates on an existing `id,lon,lat,geom(Point,4326)` relation. Other `--method` values require their original database functions and persisted method-named index files; the included optional QMF extension supports the two QMF modes. The complete original multi-baseline server deployment/systemd campaign is not automatically recreated. The end-to-end SQL client was exercised for PostGIS and extension-backed QMF on the same real 8,192-point prefix; other extension-backed baseline SQL methods were not executed during packaging.

Portable native latency includes Python/ctypes call overhead; psycopg2 latency includes Python/client overhead. Original libpq latency includes its prepared-statement round trip. Native memory is process high-water RSS, including truth/input arrays; it is not the historical paper process estimator. Do not merge these different timing/memory scopes into historical figure columns. Outputs include mean/P95/P99 latency, QPS, index bytes, build seconds, correctness counts and applicable optimizer/cache/resource counters. Every measurement is computed from execution.

### Paper figures and experiment entries

| Paper result | Actual computation entry | Plot source/export group and limitations |
|---|---|---|
| Fig. 6: full-scale latency distribution | `run_index.py`, `run_baselines.py`, original client via `run_paper_sql.py` | `section4_2`, figure 6 additionally needs the excluded original per-query latency export |
| Figs. 7–8: full-scale build/size/query/memory comparisons | Same index/baseline entries, four frozen CSVs | `section4_2`; database/native timing and memory scopes differ as stated above |
| Fig. 9: workload areas | Index/baseline entries accept the corresponding workload directory | `section4_2`; final original area scalar exports retained; full campaign workload variants require author inputs |
| Fig. 10: four construction strategies | `run_strategies.py --mode FULL` | `section4_3_4_4`; original 20k sample identities require author inputs |
| Fig. 11: finite-budget search quality | `run_studies.py --task search --mode FULL` | `section4_3_4_4`; 40 frozen Original nodes, 30 seeds, budgets 32–512 |
| Fig. 12: optimizer time and cache work | `run_studies.py --task efficiency --mode FULL` | `revised`; fresh whole-pipeline timing is not a replacement for historical phase sums |
| Fig. 13 / Table II: Hybrid ablations | `run_optimizer.py --mode ablation` | `revised`; Random replacement retained, removed BestFirst is not reinstated |
| Fig. 14: gate-level validation | `run_quantum.py --mode FULL` | `section4_5_4_6`; original independent synthetic gate protocol |
| Fig. 15: H/K sensitivity | `run_studies.py --task sensitivity --mode FULL` | `section4_5_4_6`; H3 timing repeated three times, other H once |
| Fig. 16: index scalability | Index/baseline entries accept each original scale sample | `revised`; original scale membership/workloads still required; no invented sampling driver |
| Selection/feedback diagnostics | `run_optimizer.py --mode selection --cohort Both` | Fresh trace analysis, Original + Validation cohorts |

The final retained plotting sources can regenerate figures from their explicitly historical scalar CSVs, without running an experiment:

```bash
python -m pip install -r requirements-analysis.txt
python -B reproduce/plot_results.py --group section4_2 --output runs/plots-performance
python -B reproduce/plot_results.py --group section4_3_4_4 --output runs/plots-search
python -B reproduce/plot_results.py --group section4_5_4_6 --output runs/plots-quantum-hk
python -B reproduce/plot_results.py --group revised --output runs/plots-revised
```

`--data` accepts external exports with the original plotting schema. Figure 6 is requested using `--group section4_2 --figure 6 --data` with a directory containing the original `fullscale_latency_observations.csv`; that large repeated raw timing export is excluded. Generating a plot from preserved scalar data is not a successful fresh reproduction. Generated figures remain in the run directory and are not included in this release.

The original styles request Times New Roman and retain their font fallback. Fonts are not bundled; install the original font separately for matching typography. All four default plot groups were executed during packaging.

## Quantum Circuit Validation

Use a separate environment and the independent entry; do not install the classical package into this environment with dependency resolution enabled.

```bash
python3.10 -m venv .venv-quantum
.venv-quantum/bin/python -m pip install -r requirements-circuit.txt
.venv-quantum/bin/python -B reproduce/run_quantum.py --mode QUICK --output runs/quantum-quick
.venv-quantum/bin/python -B reproduce/run_quantum.py --mode FULL --output runs/quantum-full
```

QUICK uses the retained eight-entry demonstration, 3 cost bits, 2,048 shots and seed 42. It measures probabilities for 0,1,2 Grover iterations. Its compiled gates can include multi-controlled operations, so its counts should not be read as elementary-gate estimates.

FULL runs the 22 retained quantum unit tests, then the original staged N=4,8,16,32,64 experiments. It validates 4/6/8-bit costs, five shot seeds 20261009–20261013 at 2,048 shots, and 20 finite-budget QMF seeds 20261009–20261028. The original deterministic synthetic cost tables are generated by the original formula in `qmf_quantum/stage_validation.py`; they are inputs to actual circuits, not fabricated measurements. The backend decomposes to `u,cx`, checks for residual multi-qubit gates, and reports qubits, depth, gate counts, simulation/transpilation/synthesis time, sampled counts and measured success probabilities. Cost-register/flag ancillas must return to zero. Classical cost precomputation and O(N) QROM synthesis are explicitly counted separately from abstract search.

For a deliberately partial formal run, add `--max-size 4` (or 8,16,32). It is labelled partial in its receipt. Real-node configuration-table loading and address reconstruction are included, but full real-node gate experiments additionally require the original exported tables and node payloads. Gate simulation is independent of online indexing.

## Experimental Configuration

| Experiment | Frozen settings |
|---|---|
| Production tree | H=3, K=4, max configurations 16,384, minimum lookahead points 4,096, minimum leaf/child 256, minimum fraction .05, max depth 8, max leaves 128 |
| Unified cost | beta_leaf=1.2779084295340111e-09; beta_point=3.428255707467659; exact leaf visits and candidate scans |
| Analytic index budget | ceil(2*sqrt(N)) abstract budget; commit root and replan children |
| Main node study | 40 Original nodes, 10 per dataset, H=3/K=4; additional 40 Validation nodes for diagnostic generalization |
| Random/search seeds | 2026101100 through 2026101129; Random without replacement; Beam deterministic and measured once per effective budget |
| Budget study | requested 32,64,128,256,512 plus official 2sqrtN label; effective min(requested,N); 8*abs(spacing(optimum)) tie tolerance |
| H/K grid | H in 1,2,3; K in 2,3,4; three timing repetitions for H=3, one for other H |
| Controlled builds | 20,000 points, seeds 11,23,37,51,73; four original strategies |
| Workloads | seed 20260910; train/validation/correctness 1,000 each; warmup 300; performance 3,000; five timing rounds |
| Selectivity targets | areas .0001,.001,.01; clipped rectangles; aspects .5,1,2; actual point selectivity may differ |
| Hybrid ablation | Protocol A: .5*T_exact; Protocol B: uncapped completion; frozen per-node T_exact, 30 seeds |
| Selection diagnostics | QF,RF,QN,RN; traces through 1.0*T_exact; Original and Validation cohorts |
| Gate validation | Independent N=4..64, cost bits 4/6/8, 2,048 shots, original shot/QMF seeds above |

`configs/qmf_frozen.yaml`, `controlled_build.json`, `standalone_protocol.json`, `experiment_protocols.json`, `seeds.json` and the node/model manifests provide the authoritative executable settings and provenance. The original algorithms keep their own exact numerical comparisons internally. Portable wrapper timing is recorded explicitly; concurrency, new hardware, training or a changed workload does not reproduce historical timing by identity.

`docs/validation.json` records exactly what was executed during packaging, including failed attempts that were corrected, skipped optional dependencies and tasks not run. `docs/source_inventory.json` records the original recursive inspection; `docs/provenance.json` maps restored dependencies and retained resources. `reproduce/check_release.py` verifies syntax, imports, configurations, checkpoint/reference/workload hashes, the single-README constraint and forbidden artifacts. `MANIFEST.sha256` and the adjacent ZIP checksum/file list support independent integrity checks.

Packaging acceptance completed the classical QUICK workflow; all 15 original model checks; native and SQL correctness on declared small inputs; and all five original synthetic gate stages N=4 through 64. The combined test environment passed 82 tests. The pinned classical environment passed 53 tests and skipped four quantum modules because Aer was absent. Full hundred-million-point index campaigns, the complete 40-node/30-seed studies and missing historical sample reconstruction were not executed. Consult the validation receipt for exact environments and coverage.

## Citation

The retained manuscript lists Yaqi Ling, Hui Sun and Xiao Qin. The final publication venue/year and DOI remain unconfirmed. A manuscript citation is:

```bibtex
@misc{ling_qcost,
  author = {Yaqi Ling and Hui Sun and Xiao Qin},
  title = {{Q-COST}: Quantum-Inspired Cost Optimization of Spatial Trees for Workload-Aware Learned Indexing},
  note = {Research manuscript; final publication details pending}
}
```

Replace this with the authors' approved published entry when available.

## License

Project-wide licensing is pending author confirmation. The root `LICENSE` records that status and grants no new rights. `licenses/QMap-LI.LICENSE` preserves the original notice for the corresponding upstream code only. Confirm research-code, weight and metadata redistribution permissions, external baseline licenses and dataset-provider terms before GitHub publication. This packaging task performs no GitHub push.
