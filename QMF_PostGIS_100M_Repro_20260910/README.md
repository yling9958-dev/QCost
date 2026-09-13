# QMF-Index Standalone Reproducibility Package

**THIS PACKAGE IS THE AUTHORITATIVE BASELINE FOR ALL FUTURE QMF-INDEX
EXPERIMENTS.** Do not use historical QMap-LI implementations for future
final-paper experiments unless they are explicitly required for historical
comparison. Future 5 x 2.4 GB experiments must branch from this baseline.

Frozen experiment: GeoLife approximately 100 MiB, PostgreSQL 14.24, PostGIS
3.2.0, eight methods, and seven primary metrics.

Functional identity:

- Dataset SHA: PASS
- Query SHA: PASS
- Stage A: 37/37 PASS
- Logical tree SHA: PASS
- Full-suite correctness: 40,000/40,000 exact, missing 0, extra 0
- Validated QMF result: 5/7 primary metrics Top-1

```bash
bash scripts/reproduce_all.sh --quick
bash scripts/reproduce_all.sh --full
```

The internal FULL package includes the exact frozen input at
`data/frozen/geolife_100m.csv`. This local file is the only automatic data
source. Builds, PostgreSQL state, indexes, logs, and results are written to the
POSIX path `${QMF_RUNTIME:-${QMF_RUNTIME_ROOT:-/var/tmp/qmf-repro}}`, so the
source package may live on exFAT and may be relocated.

The PUBLIC package omits the dataset because its license prohibits
redistribution. A public-package user who accepts the upstream terms may run
`bash data/recovery/fetch_geolife.sh` explicitly to download the official
archive and reconstruct the frozen file. Normal reproduction never searches
historical directories and never falls back to old QMap-LI files.

Quick mode verifies the complete package, dataset, queries, Stage A, adapters,
PostgreSQL loading, one complete QMF build, logical tree and serialized index,
all 5,000 QMF correctness queries, one timing repetition, and the no-online-QMF
contract. It does not establish a new eight-method performance ranking. Full
mode preserves the frozen eight-method, three-build, five-timing-repetition
protocol. See [REPRODUCE.md](REPRODUCE.md) for prerequisites and interpretation.

The source is the frozen export from commit
`8b16e5ec9d1c59596c72a2bb19b37c4e3ae8aae8`. No QMF algorithm, dataset,
query, or metric definition was changed during standalone hardening.
