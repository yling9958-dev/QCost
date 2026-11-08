"""QMF index construction and range-query support."""

from __future__ import annotations

import numpy as np

import pandas as pd

DTYPES = {"x": np.float64, "y": np.float64, "id": np.int64}

def read_points(path, *, expected_count=None, chunk_size=1_000_000, trace=None):
    options = dict(usecols=["x", "y", "id"], dtype=DTYPES,
                   float_precision="round_trip")
    if expected_count is None:
        frame = pd.read_csv(path, **options)
        if trace is not None:
            trace.emit("during_point_load", rows_loaded=len(frame), expected_count="unknown")
        return (np.ascontiguousarray(frame[["x", "y"]].to_numpy()),
                np.ascontiguousarray(frame["id"].to_numpy()))

    count = int(expected_count)
    if count < 1 or int(chunk_size) < 1:
        raise ValueError("expected_count and chunk_size must be positive")
    points = np.empty((count, 2), dtype=np.float64)
    identifiers = np.empty(count, dtype=np.int64)
    offset = 0
    for frame in pd.read_csv(path, chunksize=int(chunk_size), **options):
        end = offset + len(frame)
        if end > count:
            raise ValueError("point CSV contains more rows than expected")
        points[offset:end, 0] = frame["x"].to_numpy(copy=False)
        points[offset:end, 1] = frame["y"].to_numpy(copy=False)
        identifiers[offset:end] = frame["id"].to_numpy(copy=False)
        offset = end
        if trace is not None and (offset == count or offset % (10 * int(chunk_size)) == 0):
            trace.emit("during_point_load", rows_loaded=offset, expected_count=count)
    if offset != count:
        raise ValueError(f"point CSV row count differs: expected {count}, observed {offset}")
    return points, identifiers
