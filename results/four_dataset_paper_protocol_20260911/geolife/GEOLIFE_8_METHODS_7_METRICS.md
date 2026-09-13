GEOLIFE RESULT
181,000,000 POINTS

Methods attempted = 8/8; methods valid = 5/8; scientifically complete = NO.

| Method | Build(s) | Size(MiB) | Mean(ms) | P95(ms) | P99(ms) | QPS | PeakMem(MiB) | Correctness | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| QMF-Index | N/A | N/A | N/A | N/A | N/A | N/A | 21579.6 | NOT_RUN | HOST_SAFETY_STOP |
| PostGIS GiST | 1389.09 | 9765.8 | 464.307 | 123.71 | 1773.44 | 2.15375 | 215.715 | 1000/1000 exact | PASS |
| LISA | 83.774 | N/A | 54.144 | 21.886 | 348.321 | 18.4693 | 7903.09 | 1000/1000 exact | PASS |
| Flood | 104.637 | N/A | N/A | N/A | N/A | N/A | 21022.3 | NOT_RUN | HOST_SAFETY_STOP |
| Tsunami | 34.3669 | 4142.76 | 59.9498 | 95.8028 | 639.179 | 16.6806 | 7718.75 | 1000/1000 exact | PASS |
| LMSFC | 60.9454 | 4833.22 | 124.113 | 1163.32 | 1938.14 | 8.05714 | 8322.88 | 1000/1000 exact | PASS |
| BMTree | 3965.3 | 4865.59 | 29.4109 | 15.5341 | 162.442 | 34.001 | 17012.6 | 1000/1000 exact | PASS |
| Boost R*-tree | N/A | N/A | N/A | N/A | N/A | N/A | 21776.1 | NOT_RUN | HOST_SAFETY_STOP |

QMF-INDEX — GeoLife

Build_s = N/A

IndexSize_MiB = N/A

Mean_ms = N/A

P95_ms = N/A

P99_ms = N/A

QPS = N/A

PeakMemory_MiB = 21579.6

Correctness = NOT_RUN

Missing = N/A

Extra = N/A

Ranks:

Build_s = N/A/5

IndexSize_MiB = N/A/4

Mean_ms = N/A/5

P95_ms = N/A/5

P99_ms = N/A/5

QPS = N/A/5

PeakMemory_MiB = N/A/5

QMF TOP-1 COUNT = 0 / 7

Best competing method for Mean_ms = BMTree

Best competing method for P95_ms = BMTree

Best competing method for P99_ms = BMTree

Best competing method for QPS = BMTree

Build repetitions = 1. Only correctness-valid methods enter rankings. Missing measurements are N/A.

QMF_ALGORITHM_CHANGED = NO

PostGIS recovery: the original successful build measurement and exact correctness receipt are retained. The lost SQL runtime was restored in 1423.84 s. Its current index is 10240180224 bytes; the historical build index was 10347552768 bytes. Size in the repaired method row describes the current query-ready index. GiST insertion tie breaking can vary the physical layout. No timing repetition or query is selected or changed.
