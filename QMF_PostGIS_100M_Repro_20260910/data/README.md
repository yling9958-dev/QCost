# Frozen GeoLife Input

The internal FULL package contains the authoritative experiment input at
`frozen/geolife_100m.csv`. It is exactly 104,857,576 bytes with SHA256
`56a07a638db478485ba5e78ff45bc7300987ef45d7d4a319666a5dabbcaa555e`,
4,197,223 point IDs, and 3,956,264 unique coordinates.

Run `bash data/verify_geolife_100m.sh` before use. Normal reproduction accepts
only this package-local file and copies it to the POSIX runtime directory.

The PUBLIC package excludes the CSV. Its explicit recovery workflow is
documented in `recovery/README.md`. The reconstruction consumes Microsoft's
official GeoLife GPS Trajectories 1.3 archive and the frozen trajectory-order
manifest, formats longitude and latitude to eight decimal places in that exact
order, and retains complete records while the output remains within the first
100 MiB. This produces the exact frozen prefix without materializing the
historical 4.2 GiB expanded file.
