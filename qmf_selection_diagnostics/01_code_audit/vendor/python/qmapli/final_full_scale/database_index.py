"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import numpy as np

from ..indexes.qmap_nai.index import HybridPrefixNode, PrefixHybridIndex

class _ExportableIndex:
    variant = "full"

    def __init__(self, query_index):
        self.query_index = query_index

def _new_node(points, indices, depth, prefix_code, node_id, *, local_points=None):
    local = points[indices] if local_points is None else np.asarray(local_points, dtype=np.float64)
    return HybridPrefixNode(
        node_id=int(node_id),
        depth=int(depth),
        prefix_code=np.uint64(prefix_code),
        point_indices=np.asarray(indices, dtype=np.int64),
        mbr=(
            float(local[:, 0].min()), float(local[:, 1].min()),
            float(local[:, 0].max()), float(local[:, 1].max()),
        ),
    )
