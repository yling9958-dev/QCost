# Known Limitations

- GeoLife raw redistribution remains intentionally excluded. The recovered
  historical conversion and frozen trajectory order now reconstruct the exact
  selected prefix from the SHA-locked official GeoLife 1.3 ZIP.
- Stage-A 37/37 is a source-export verification attestation. Historical Stage-B
  figures/results are omitted; package tests rehash the R4 weights and production
  artifacts, not absent original historical payloads.
- LISA/Flood/Boost lack directly comparable query-ready persistent Size under
  the frozen protocol. They remain in all other valid comparisons.
- RSMI official source revision `112e349ccb13b3f5b24062b2511ef9650951ea72`:
  BUILD_RESOURCE_BLOCKED at the frozen 1800-second pilot build limit. It is not
  replaced by a fake implementation and is not a primary benchmark method.
- QMF was not fastest to build and did not have lowest memory. The original
  5 x 2.4 GiB evaluation was not run; conservative memory headroom was insufficient.
- This minimal build excludes the unused RSMI/LibTorch link. Its impact on loader
  cost and RSS cannot be called performance-equivalent without measurement.
- Timing depends on scheduling, CPU frequency, caches and versions. No timing
  value is expected to be bitwise reproducible; quick mode is not a full ranking.
