# Reference System

Ubuntu 22.04, Intel i7-10700, 8 physical/16 logical cores, approximately 31 GiB RAM.
PostgreSQL 14.24, PostGIS 3.2.0, Boost 1.74. Compiler/CPU and Python dependency
versions are locked in this directory. Build uses C++17, Release, -O3, -DNDEBUG,
-march=native and _GLIBCXX_USE_CXX11_ABI=0 as in the reference runtime.
CPU-specific compilation means a binary must not be copied to a different ISA.

Use POSIX storage for virtual environments, fetched checkouts, CMake, pgdata and
temporary state. The archive itself may reside on exFAT. Runtime scripts reject
non-POSIX runtime locations. Host-native results are authoritative.

The dedicated cluster uses a Unix socket only; no external TCP listener. The
original database/cluster is never altered. PostgreSQL performance settings are
copied from the frozen host to config/postgres.conf.repro; the benchmark retains
the original per-session jit/parallel overrides.
