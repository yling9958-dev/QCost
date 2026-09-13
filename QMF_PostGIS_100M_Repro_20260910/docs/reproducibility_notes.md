# Reproduction Scope

Exact source reference: 8b16e5ec9d1c59596c72a2bb19b37c4e3ae8aae8.
Archive-local wrappers are packaging infrastructure, not new algorithms.
The original repository is read-only except the requested new dist/ZIP output.
The existing ignore rules are not changed to conceal generated package files;
git status may therefore show the newly requested untracked dist/ directory.

Clean-unzip verification must sanitize PYTHONPATH, LD_LIBRARY_PATH and project
environment variables. Only package-local Python sources and newly compiled C++
libraries may execute. Fetched source checkouts and the official GeoLife ZIP are
explicit external inputs, not hidden dependencies. The ZIP is converted using
the frozen trajectory order and rejected unless both archive and output hashes
match.

MANIFEST.sha256 covers all immutable deliverable files except itself. Runtime
products stay outside the archive. REPRO_PACKAGE_REPORT.md records actual tests;
the ZIP's own SHA/size are in an external companion report to avoid a circular
self-hash. A ZIP cannot contain its own final SHA256 as a verified field.

Fresh quick verification is a full-size QMF functional test, not a tiny synthetic
smoke test. It still does not replace a fresh eight-method five-repetition run.
