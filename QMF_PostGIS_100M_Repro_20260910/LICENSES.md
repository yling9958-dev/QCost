# License and Provenance Policy

This export does not invent a new license for the research code. The supplied
QMF, adapters, clean-room Tsunami/LMSFC, R4 checkpoint and scripts are the project
owner's reproduction materials; consult the owner before public redistribution
if no explicit project license grant accompanies delivery.

- learnedbench: **NOASSERTION**. No upstream source is included. The fetch script
  checks out `f029ec27d0296bc672c4c8229a46a6f7e98b0e0b`; local use/redistribution
  terms must be reviewed separately. Only the project's adapter and frozen patch
  are included. Do not treat the patch as a license grant over upstream code.
- BMTree: MIT per the pinned author repository. Fetched, not vendored; retain its
  upstream LICENSE when using or distributing it.
- morton-nd: MIT, fetched pinned dependency of the shared baseline translation unit.
- Boost.Geometry 1.74: Boost Software License 1.0; installed system dependency.
- PostgreSQL 14.24: PostgreSQL License; PostGIS 3.2.0: GPL-2.0-or-later system code.
- GeoLife raw data: not redistributed; permission and exact processed-source
  retrieval are unresolved. See data/README.md.

No external compiled binaries, historical experimental outputs, database clusters,
or runtime logs are embedded. See third_party/provenance.csv for exact references.
