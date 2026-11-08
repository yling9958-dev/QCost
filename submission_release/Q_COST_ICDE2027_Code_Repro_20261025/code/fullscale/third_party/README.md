# External Source Retrieval

No complete third-party source is vendored. `fetch_baselines.sh` retrieves exact
Git revisions into POSIX runtime storage, checks HEAD and clean tracked state,
then applies the frozen learnedbench patch to a separate copy. C++ adapter bodies
are copied verbatim from the final source commit.

GitHub/network failure is a dependency-fetch blocker, never permission to replace
an implementation with a simplified substitute. RSMI is supplementary only and
is not fetched. Its compile-time unavailable stub remains because the shared
runtime factory references it; it is never in the primary method suite.
