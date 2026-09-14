"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import time

import hashlib

import struct

from dataclasses import dataclass, field

import numpy as np

from ...core.geometry import boxes_intersect, query_covers_box

from .suffix import DualAxisSuffix

@dataclass
class HybridPrefixNode:
    node_id: int
    depth: int
    prefix_code: np.uint64
    point_indices: np.ndarray
    mbr: tuple[float, float, float, float]
    split_action: object | None = None
    threshold: float | None = None
    children: list["HybridPrefixNode"] = field(default_factory=list)
    suffix_strategy: str = "adaptive_single_axis"
    storage_start: int = 0
    storage_end: int = 0
    suffix: DualAxisSuffix | None = None

    @property
    def is_leaf(self):
        return not self.children

def _merge_ranges(ranges):
    if not ranges:
        return []
    ordered = sorted((int(start), int(end)) for start, end in ranges if end > start)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]

class PrefixHybridIndex:
    """Static query-only kernel; controller execution is strictly build-time."""

    def build(self, points, ids, root, *, static_export=False, trace=None):
        self.original_points = np.asarray(points, dtype=np.float64)
        self.original_ids = np.asarray(ids, dtype=np.int64)
        self.root = root
        leaf_indices = []
        leaf_membership = hashlib.sha256()

        def order(node):
            if node.is_leaf:
                start = sum(len(value) for value in leaf_indices)
                leaf_indices.append(np.asarray(node.point_indices, dtype=np.int64))
                membership = np.ascontiguousarray(node.point_indices, dtype=np.dtype("<i8"))
                leaf_membership.update(struct.pack("<QQ", int(node.node_id), len(membership)))
                leaf_membership.update(memoryview(membership).cast("B"))
                node.storage_start = start
                node.storage_end = start + len(node.point_indices)
                return node.storage_start, node.storage_end
            ranges = [order(child) for child in node.children]
            node.storage_start = min(value[0] for value in ranges)
            node.storage_end = max(value[1] for value in ranges)
            return node.storage_start, node.storage_end

        order(root)
        self.leaf_membership_sha256 = leaf_membership.hexdigest()
        original_positions = np.concatenate(leaf_indices) if leaf_indices else np.empty(0, dtype=np.int64)
        if trace is not None:
            trace.emit("layout_permutation_ready", permutation_bytes=original_positions.nbytes,
                       leaf_count=len(leaf_indices))
        self.storage_original_positions = None if static_export else original_positions
        self.points = self.original_points[original_positions]
        self.ids = self.original_ids[original_positions]
        if trace is not None:
            trace.emit("layout_reordered_storage_ready", points_bytes=self.points.nbytes,
                       ids_bytes=self.ids.nbytes)
        if static_export:
            self.original_points = None
            self.original_ids = None
            leaf_indices.clear()
            del original_positions
        self.nodes = []
        self.leaves = []
        stack = [root]
        while stack:
            node = stack.pop(); self.nodes.append(node)
            if node.is_leaf:
                self.leaves.append(node)
                start, end = node.storage_start, node.storage_end
                suffix = DualAxisSuffix(node.suffix_strategy)
                node.suffix = (
                    suffix.build_static_export(self.points[start:end], start)
                    if static_export else
                    suffix.build(self.points[start:end], np.arange(start, end, dtype=np.int64))
                )
                if static_export:
                    node.point_indices = np.empty(0, dtype=np.int64)
                if trace is not None and (len(self.leaves) == 1 or len(self.leaves) % 16 == 0):
                    trace.emit("layout_suffix_milestone", completed_leaves=len(self.leaves),
                               leaf_points=end - start)
            else:
                stack.extend(reversed(node.children))
        self._build_compact_arrays()
        return self

    def _build_compact_arrays(self):
        self.node_mbr = np.asarray([node.mbr for node in self.nodes], dtype=np.float64)
        self.node_depth = np.asarray([node.depth for node in self.nodes], dtype=np.uint16)
        self.node_prefix = np.asarray([node.prefix_code for node in self.nodes], dtype=np.uint64)
        self.node_storage_start = np.asarray([node.storage_start for node in self.nodes], dtype=np.int64)
        self.node_storage_end = np.asarray([node.storage_end for node in self.nodes], dtype=np.int64)
        self.node_is_leaf = np.asarray([node.is_leaf for node in self.nodes], dtype=np.bool_)

    def _collect(self, node, query, full_ranges, partial_positions, interval_counter):
        if not boxes_intersect(node.mbr, query):
            return
        if query_covers_box(query, node.mbr):
            full_ranges.append((node.storage_start, node.storage_end))
            interval_counter[0] += 1
            return
        if node.is_leaf:
            positions, intervals = node.suffix.query_candidates(query)
            if len(positions):
                partial_positions.append(positions)
            interval_counter[0] += int(intervals)
            return
        for child in node.children:
            self._collect(child, query, full_ranges, partial_positions, interval_counter)

    def candidate_positions(self, query):
        full_ranges, partial_positions, interval_counter = [], [], [0]
        self._collect(self.root, tuple(float(value) for value in query), full_ranges, partial_positions, interval_counter)
        merged = _merge_ranges(full_ranges)
        chunks = [np.arange(start, end, dtype=np.int64) for start, end in merged]
        chunks.extend(partial_positions)
        # Tree leaves are disjoint and traversal never emits an ancestor and a
        # descendant together, so no np.unique de-duplication is required.
        positions = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.int64)
        return positions, interval_counter[0]

    def range_query(self, query):
        started = time.perf_counter()
        positions, interval_count = self.candidate_positions(query)
        if len(positions):
            points = self.points[positions]
            mask = (
                (points[:, 0] >= query[0]) & (points[:, 0] <= query[2])
                & (points[:, 1] >= query[1]) & (points[:, 1] <= query[3])
            )
            result_positions = positions[mask]
        else:
            result_positions = positions
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {
            "result_ids": self.ids[result_positions],
            "candidate_ids": self.ids[positions],
            "candidate_size": int(len(positions)),
            "result_size": int(len(result_positions)),
            "interval_count": int(interval_count),
            "latency_ms": float(latency_ms),
        }

    def range_query_batch(self, queries):
        return [self.range_query(query) for query in np.asarray(queries, dtype=np.float64)]

    def index_size_breakdown(self):
        tree_arrays = (
            self.node_mbr, self.node_depth, self.node_prefix,
            self.node_storage_start, self.node_storage_end, self.node_is_leaf,
        )
        tree_bytes = int(sum(value.nbytes for value in tree_arrays))
        leaf_storage = int(self.points.nbytes + self.ids.nbytes + self.storage_original_positions.nbytes)
        suffix_rows = [leaf.suffix.index_size_breakdown() for leaf in self.leaves]
        sorted_values = sum(row["sorted_values_bytes"] for row in suffix_rows)
        sorted_positions = sum(row["sorted_positions_bytes"] for row in suffix_rows)
        segments = sum(row["suffix_segment_bytes"] for row in suffix_rows)
        compact = tree_bytes + leaf_storage + sorted_values + sorted_positions + segments
        python_estimate = compact + len(self.nodes) * 256 + sum(
            row["python_runtime_suffix_estimate"] for row in suffix_rows
        )
        return {
            "raw_points_shared_bytes": int(self.original_points.nbytes),
            "leaf_storage_bytes": leaf_storage,
            "sorted_values_bytes": int(sorted_values),
            "sorted_positions_bytes": int(sorted_positions),
            "prefix_tree_array_bytes": tree_bytes,
            "suffix_segment_bytes": int(segments),
            "bitmap_bytes": 0,
            "global_code_bytes": int(self.node_prefix.nbytes),
            "compact_serialized_size_bytes": int(compact),
            "python_runtime_resident_estimate_bytes": int(python_estimate),
        }

    def index_size_bytes(self):
        return self.index_size_breakdown()["compact_serialized_size_bytes"]
