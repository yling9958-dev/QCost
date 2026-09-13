# Explicit Public Dataset Recovery

This directory reconstructs the exact frozen experiment input without any
historical research repository or expanded 4.2 GiB CSV.

After reviewing `../LICENSE_DATASET.md`, run:

```bash
bash data/recovery/fetch_geolife.sh
```

The script downloads the official GeoLife 1.3 ZIP into the POSIX runtime area,
or uses `QMF_GEOLIFE_ARCHIVE` when supplied. It validates the exact official ZIP
(313,164,406 bytes, SHA256
`1107c5ac064d0a23c8d021a8736a77e53abc75b227062e6260342c6a8d86bdb6`),
validates `geolife_plt_order.txt`, reconstructs `../frozen/geolife_100m.csv`,
and runs the full dataset verifier.

`prepare_geolife_source.py` and `verify_source.sh` validate inputs;
`build_geolife_100m.py` performs the deterministic conversion. A mismatch fails
without replacing an existing valid frozen file.
