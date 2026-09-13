| Dataset | Points | Build_s | Mean_ms | P95_ms | P99_ms | QPS | PeakMemory_MiB | Correctness | BuildRank | SizeRank | MeanRank | P95Rank | P99Rank | QPSRank | MemoryRank | Top1Count | Size_MiB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GeoLife | 181000000 | N/A | N/A | N/A | N/A | N/A | 21579.6 | NOT_RUN | N/A/5 | N/A/4 | N/A/5 | N/A/5 | N/A/5 | N/A/5 | N/A/5 | 0 | N/A |

| Dataset | BuildRank | SizeRank | MeanRank | P95Rank | P99Rank | QPSRank | MemoryRank | Top1Count |
|---|---|---|---|---|---|---|---|---|
| GeoLife | N/A/5 | N/A/4 | N/A/5 | N/A/5 | N/A/5 | N/A/5 | N/A/5 | 0 |


GeoLife

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
