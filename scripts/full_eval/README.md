# Test fixtures only

`worker.py` and `postgres_full.cpp` remain byte-for-byte unchanged because the
current `paper_eval` regression tests compare the frozen QMF build function and
exact correctness SQL against them. They are not a supported benchmark runner.

Historical orchestration moved to `archive/code_history_20260912/scripts/full_eval/`.
Use `scripts/run_paper_benchmark.sh` and `scripts/paper_eval/` for the current
paper benchmark. Do not execute these historical fixture files directly.
