"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import numpy as np

import pandas as pd

def read_points(path):
    frame = pd.read_csv(path, usecols=["x", "y", "id"],
                        dtype={"x": np.float64, "y": np.float64, "id": np.int64},
                        float_precision="round_trip")
    return (np.ascontiguousarray(frame[["x", "y"]].to_numpy()),
            np.ascontiguousarray(frame["id"].to_numpy()))
