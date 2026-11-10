"""QMF index construction and range-query support."""

from __future__ import annotations

import struct

from pathlib import Path

import numpy as np

MAGIC = b"QMAPNAI1"

VERSION = 1

VARIANTS = {"full": 0, "no_entangle": 1, "classical": 2}

STRATEGIES = {
    "x_rank": 0,
    "y_rank": 1,
    "adaptive_single_axis": 2,
    "dual_axis_intersection": 3,
    "local_zorder": 4,
    "local_hilbert": 5,
}

def _write_array(stream, values, dtype) -> None:
    array = np.ascontiguousarray(values, dtype=dtype)
    stream.write(array.astype(array.dtype.newbyteorder("<"), copy=False).tobytes())

def export_static_index(index, path, *, compact=False) -> int:
    """Write an already-built index without serializing training-only objects."""

    query_index = index.query_index
    nodes = query_index.nodes
    leaves = query_index.leaves
    node_numbers = {id(node): number for number, node in enumerate(nodes)}
    leaf_numbers = {id(node): number for number, node in enumerate(leaves)}
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if len(query_index.points) > np.iinfo(np.uint32).max or len(nodes) > np.iinfo(np.int32).max:
        raise OverflowError("static element offsets exceed the supported range")
    if np.any(query_index.ids < 0) or np.any(query_index.ids > np.iinfo(np.uint32).max):
        raise OverflowError("static point identifiers exceed uint32")

    with destination.open("wb") as stream:
        stream.write(MAGIC)
        stream.write(
            struct.pack(
                "<IIQQQ",
                2 if compact else VERSION,
                VARIANTS[index.variant],
                len(query_index.points),
                len(nodes),
                len(leaves),
            )
        )
        if compact:
            # Offsets count elements, not bytes; all file positions remain 64-bit.
            for values, dtype in ((query_index.points[:, 0], "<f4"),
                                  (query_index.points[:, 1], "<f4"), (query_index.ids, "<u4")):
                for start in range(0, len(values), 65536):
                    _write_array(stream, values[start:start + 65536], np.dtype(dtype))
        else:
            points = np.asarray(query_index.points, dtype=np.float32)
            ids = np.asarray(query_index.ids, dtype=np.uint32)
            for point, point_id in zip(points, ids):
                stream.write(struct.pack("<ffI", float(point[0]), float(point[1]), int(point_id)))

        for node in nodes:
            children = [node_numbers[id(child)] for child in node.children]
            left = children[0] if children else -1
            right = children[1] if len(children) > 1 else -1
            leaf_number = leaf_numbers.get(id(node), -1)
            strategy = STRATEGIES[node.suffix_strategy] if node.is_leaf else 255
            stream.write(
                struct.pack(
                    "<ffffIIiiiB3x",
                    *map(float, node.mbr),
                    int(node.storage_start),
                    int(node.storage_end),
                    int(left),
                    int(right),
                    int(leaf_number),
                    strategy,
                )
            )

        for leaf in leaves:
            suffix = leaf.suffix
            count = len(suffix.points)
            stream.write(struct.pack("<I", count))
            if not compact:
                _write_array(stream, suffix.x_sorted_values, np.dtype("<f4"))
            _write_array(stream, suffix.x_sorted_positions, np.dtype("<u4"))
            if not compact:
                _write_array(stream, suffix.y_sorted_values, np.dtype("<f4"))
            _write_array(stream, suffix.y_sorted_positions, np.dtype("<u4"))
            stream.write(struct.pack("<I", len(suffix.segment_positions)))
            _write_array(stream, suffix.segment_positions, np.dtype("<u4"))
            stream.write(struct.pack("<I", len(suffix.segments)))
            for segment in suffix.segments:
                stream.write(
                    struct.pack(
                        "<IIffff",
                        int(segment.start),
                        int(segment.end),
                        *map(float, segment.mbr),
                    )
                )
    return destination.stat().st_size

def export_compact_static_index(index, path) -> int:
    """Store coordinates once, preserving the version-1 float32 bit patterns."""
    return export_static_index(index, path, compact=True)
