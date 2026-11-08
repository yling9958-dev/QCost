# Reproduction guide

## 1. Environment and integrity

Use Linux, Python 3.10, a fresh environment, and the requirement files in the
package root. `requirements-analysis.txt` records the environment used for the
export's table/figure validation. The original optimizer campaign's dependency
record is `configs/requirements_frozen.txt`; the original full-scale dependency
locks and native system packages are in `code/fullscale/environment/`.
The exact observed packaging versions are in
`provenance/PACKAGING_ENVIRONMENT.json`. Recorded Torch is 2.4.1+cu118, with CPU
execution; a CPU installation does not require a GPU. Timing equivalence across
hardware/library environments is not assumed.

```bash
python -B reproduce/check_package.py
```

This checks every delivered file's SHA-256, Python syntax, shell syntax, all 80
node identities and offline-reference hashes, and the exclusion of point/query
data formats. The manifest excludes only itself.

Plots use Times New Roman, as the current project does. Fonts are not bundled.
Install that font separately if identical typography is required; the Section 4
plot utilities have their original fallback behavior. Changing fonts changes
layout, not measurements. PDF/SVG output remains vector and PNG uses 600 dpi.

## 2. Recompute tables and statistical comparisons without datasets

```bash
python -B reproduce/statistics.py --output /tmp/qcost-tables
```

Inputs are the real 12,000-row current five-variant table export and the 38,400
event-derived budget snapshots from 9,600 selection trajectories, with measured
node/seed identities. They contain no point clouds or query rectangles.
The script checks the original root costs, failures, budgets and seed coverage;
recomputes Table II, node-level intervals and paired effects; verifies all 3,040
selection-summary point estimates; and recomputes the 60 table/interaction
paired intervals and the two primary tests in each cohort. It regenerates both
LaTeX tables and requires agreement with the retained reference tables.

Thirty seeds are repeated measurements within a node. Resampling and pairing
use nodes as the independent units. Invalid roots remain in the optimal-rate
denominator; regret uses defined returns and paired differences use common
defined node/seed pairs. The table notes retain coverage and timing-batch limits.

The supplied snapshot CSVs do not replace the excluded full event logs. The
original `code/analysis/analyze_selection.py` contains the event-to-metric
definitions, including censoring and AUC. New instrumented runs can emit all
necessary event fields with the next command set.

## 3. Redraw the current empirical figures

```bash
python -B reproduce/figures.py --output /tmp/qcost-figures
# Or only the latest Figures 6–9:
python -B reproduce/figures.py --output /tmp/qcost-figures-6to9 --groups section4_2
```

The script copies only the corresponding plot inputs/scripts into the output
directory, so the delivered reference results are never overwritten. It emits
PNG/SVG/PDF. Figure 6 uses all real retained per-query latency measurements;
Figure 7 uses the confirmed Flood values and no speedup labels; Figure 8 retains
the original construction/storage scope and Flood Index Size=N/A. Figures
12/13/16 use the current filtered paper exports. Figures 1–5 are method/motivation
illustrations outside this empirical code bundle. No paper source is changed.

## 4. External datasets and node inputs

No spatial points or query rectangles are delivered. Obtain the original input
files separately and lay out the fixed node inputs as:

```text
/path/to/external-nodes/
  geolife_05d648fb4ec86485/input.npz
  ...
```

Each NPZ must contain the original `points` (N×2) and `queries` (Q×4) arrays.
The 80 file hashes, counts, datasets, cohort membership and frozen T_exact values
are in `configs/NODE_MANIFEST.json`. These are **identities**, not node payloads.
Each run checks the hash before loading. Arbitrary new samples cannot be labelled
as the fixed paper cohort. No automatic recreation of the exact frozen nodes
from unprocessed public datasets is claimed. The historical outcome-blind node
selection implementation and frozen candidate order are included for inspection;
its upstream sample/membership inputs are external data as well.

The four full-scale processed dataset identities, point counts and hashes are
in `external_inputs/FULLSCALE_MANIFEST.json`. The frozen full-scale workload
generator/protocol is in `code/fullscale/original_paper_controller/worker.py`
and `paper_protocol.py`. Training, correctness, warmup and timing query CSVs are
excluded. Existing GeoLife recovery code is in `code/fullscale/data/recovery/`;
that recipe reconstructs the historical 100 MiB input only, not the later four
full-scale datasets. No download is performed automatically by the main entry
points. Dataset-specific acquisition permissions remain with the upstream data.

## 5. Current five-variant Hybrid ablation

```bash
python -m pip install -r requirements-optimizer.txt
# Small complete-optimization check on real external inputs:
python -B reproduce/run_optimizer.py --mode ablation \
  --inputs-root /path/to/external-nodes --output /tmp/qcost-smoke \
  --limit-nodes 2 --limit-seeds 1 --protocol B
# Fresh 40 × 30 × 5 × 2 campaign, serial:
python -B reproduce/run_optimizer.py --mode ablation \
  --inputs-root /path/to/external-nodes --output /path/to/new-ablation
```

Variants are `Full`, `Random`, `NoCache`, `NoFeedback`, `Enumeration`; the Random
variant is M4 uniform random frontier selection, not M6 BestFirst. All retain the
original objective and candidate generation. H=3, K=4, seeds
2026101100–2026101129. Protocol A uses 0.5 times the frozen node T_exact; Protocol
B runs to completion with a separately reported 120-second safety timeout.
A timeout is never successful completion. Full solves are checked against Exact
after the optimizer returns. The optimizer never receives offline root costs.
The original optimizer timer includes initialization, selection, recursive work,
cache maintenance and return serialization; input I/O and model loading are
shared preconditions. No future incumbent after the deadline is accepted.

The new wrapper balances variant order across node/seed units and runs one
optimizer at a time with one thread and one available CPU. It records its own
source/model/environment manifest and refuses incompatible checkpoint reuse.
It does not insert smoke/reproduction measurements into the historical results.
Wall-clock quality may vary on another machine because the frozen time budgets
are historical; compare a new campaign's variants within its common environment.

## 6. QMF × Feedback diagnostics

```bash
python -B reproduce/run_optimizer.py --mode selection --cohort Both \
  --inputs-root /path/to/external-nodes --output /path/to/new-selection
```

This invokes the delivered instrumented implementation for QF, RF, QN and RN,
through 1.0T_exact on each node. Event times permit offline extraction at
0.25/0.50/0.75/1.00T_exact. Candidate selections, completed evaluations,
incumbents, cache operations and exact evaluations are retained. The current
four-component/Random ablation and this instrumented campaign have distinct
source versions and must not have their timing rows pooled.

Export newly measured runs into a separate CSV/node-summary directory with:

```bash
python -B reproduce/analyze_new_runs.py --runs /path/to/new-selection \
  --output /path/to/new-selection-analysis
```

The same command accepts the ablation wrapper's run folder. Its coverage receipt
keeps partial protocols and failed runs explicit.

## 7. Production index and native adapters

```bash
python -B reproduce/build_qcost_index.py --help
python -B reproduce/build_qcost_index.py \
  --mode uniform_qmf --r4-checkpoint models/r4.pt \
  --points /path/to/normalized-points.csv --point-count POINT_COUNT \
  --train-queries /path/to/train-normalized.csv \
  --index /path/to/new-output/qcost.idx --metadata /path/to/new-output/metadata.json \
  --context-seed 20260910 --beta-leaf 1.2779084295340111e-09 \
  --beta-point 3.428255707467659 --max-depth 8 --min-leaf-size 256 \
  --max-leaves 128 --budget-factor 2.0
```

Points CSV has `x,y,id`; training CSV has `xmin,ymin,xmax,ymax`. These must use
the original shared normalization and workload protocol. This entry point calls
the retained production implementation, separate from the H=3 node experiment.
For the C++/PostgreSQL runtime, install the recorded native dependencies and use:

```bash
export QMF_RUNTIME=/var/tmp/qcost-fresh-runtime
bash code/fullscale/scripts/03_fetch_baselines.sh
bash code/fullscale/scripts/04_build_all.sh
```

These are explicit opt-in fetch/build commands for pinned third-party revisions.
Neither is run by `check_package.py`, statistics or plotting. Native build and
full-dataset performance were not rerun while packaging. The old campaign
controller includes host-specific systemd/database/repair state and is retained
as source history, not advertised as a fresh-machine one-command controller.
Use the provided production builder/runtime and frozen protocol when setting up
a new full-scale environment. No missing old runtime state is silently invented.

## 8. Optional gate-level check

In a separate environment, install `requirements-circuit.txt`, then:

```bash
python -B -m pytest -q -p no:cacheprovider code/gate_prototype/test_qmf_quantum_circuit_prototype.py
```

This is the existing small-circuit validation, not a hardware speedup claim.
The main spatial optimizers run on the CPU and do not require Qiskit/Aer.

## 9. Provenance

`provenance/SOURCE_FILES.json` links every copied source/results file to its
original SHA-256. Historical absolute paths inside provenance columns are labels,
not runtime dependencies of the new entry points. `MANIFEST.sha256` identifies
the delivered files, including documented packaging edits. The source workspace
contains uncommitted research changes; the recorded Git commit alone is not a
complete identity. The delivered hash list is authoritative for this snapshot.

