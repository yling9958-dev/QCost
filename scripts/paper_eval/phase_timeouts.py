"""Shared formal method phase limits; infrastructure timeout amendment 2026-09-13."""

# No method-specific overrides. Normalize/load/auxiliary SQL keep their own limits.
TIMEOUTS_S = {'build':43200, 'correctness':43200, 'timing':43200}
