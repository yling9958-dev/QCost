"""QMF index construction and range-query support."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...core.geometry import boxes_intersect

from ...core.morton import hilbert_code, zorder_code

def _mbr(points):
    return (
        float(points[:, 0].min()), float(points[:, 1].min()),
        float(points[:, 0].max()), float(points[:, 1].max()),
    )

def _sorted_intersection(first, second):
    first = np.sort(np.asarray(first, dtype=np.int64), kind="mergesort")
    second = np.sort(np.asarray(second, dtype=np.int64), kind="mergesort")
    output = np.empty(min(len(first), len(second)), dtype=np.int64)
    left = right = count = 0
    while left < len(first) and right < len(second):
        if first[left] == second[right]:
            output[count] = first[left]; count += 1; left += 1; right += 1
        elif first[left] < second[right]:
            left += 1
        else:
            right += 1
    return output[:count]

@dataclass
class LocalSegment:
    start: int
    end: int
    mbr: tuple[float, float, float, float]

class DualAxisSuffix:
    """Leaf-local suffix whose label and runtime use the same query method."""

    def __init__(self, strategy="adaptive_single_axis", grid_bits=3):
        self.strategy = str(strategy)
        self.grid_bits = int(grid_bits)

    def build(self, points, storage_positions=None):
        self.points = np.asarray(points, dtype=np.float64)
        self.storage_positions = (
            np.arange(len(self.points), dtype=np.int64)
            if storage_positions is None else np.asarray(storage_positions, dtype=np.int64)
        )
        self.x_order = np.argsort(self.points[:, 0], kind="mergesort")
        self.y_order = np.argsort(self.points[:, 1], kind="mergesort")
        self.x_sorted_values = self.points[self.x_order, 0].copy()
        self.y_sorted_values = self.points[self.y_order, 1].copy()
        self.x_sorted_positions = self.storage_positions[self.x_order].copy()
        self.y_sorted_positions = self.storage_positions[self.y_order].copy()
        self.segments = []
        self.segment_positions = np.empty(0, dtype=np.int64)
        if self.strategy in {"local_zorder", "local_hilbert"}:
            self._build_local_sfc()
        return self

    def build_static_export(self, points, storage_start):
        """Build only the arrays persisted by compact static format version 2."""
        if self.strategy in {"local_zorder", "local_hilbert"}:
            return self.build(points, np.arange(
                int(storage_start), int(storage_start) + len(points), dtype=np.int64
            ))
        self.points = np.asarray(points, dtype=np.float64)
        self.storage_positions = None
        self.x_order = None
        self.y_order = None
        self.x_sorted_values = None
        self.y_sorted_values = None
        self.x_sorted_positions = np.argsort(self.points[:, 0], kind="mergesort")
        self.x_sorted_positions += int(storage_start)
        self.y_sorted_positions = np.argsort(self.points[:, 1], kind="mergesort")
        self.y_sorted_positions += int(storage_start)
        self.segments = []
        self.segment_positions = np.empty(0, dtype=np.int64)
        return self

    def _build_local_sfc(self):
        box = _mbr(self.points)
        span = np.maximum(np.asarray([box[2] - box[0], box[3] - box[1]]), 1e-12)
        local = np.clip((self.points - np.asarray(box[:2])) / span, 0.0, 1.0)
        if self.strategy == "local_hilbert":
            codes = hilbert_code(local, bits=self.grid_bits)
        else:
            codes = zorder_code(local, bits=self.grid_bits)
        cell_count = 1 << (2 * self.grid_bits)
        keys = np.minimum(np.floor(codes * (cell_count - 1)).astype(np.int64), cell_count - 1)
        order = np.argsort(keys, kind="mergesort")
        self.segment_positions = self.storage_positions[order]
        ordered_points = self.points[order]
        ordered_keys = keys[order]
        start = 0
        while start < len(order):
            end = int(np.searchsorted(ordered_keys, ordered_keys[start], side="right"))
            self.segments.append(LocalSegment(start, end, _mbr(ordered_points[start:end])))
            start = end

    @staticmethod
    def _axis_slice(values, positions, lower, upper):
        left = int(np.searchsorted(values, lower, side="left"))
        right = int(np.searchsorted(values, upper, side="right"))
        return positions[left:right]

    def query_candidates(self, rect):
        rect = tuple(float(value) for value in rect)
        x = self._axis_slice(self.x_sorted_values, self.x_sorted_positions, rect[0], rect[2])
        y = self._axis_slice(self.y_sorted_values, self.y_sorted_positions, rect[1], rect[3])
        if self.strategy == "x_rank":
            return x.copy(), int(bool(len(x)))
        if self.strategy == "y_rank":
            return y.copy(), int(bool(len(y)))
        if self.strategy == "adaptive_single_axis":
            selected = x if len(x) <= len(y) else y
            return selected.copy(), int(bool(len(selected)))
        if self.strategy == "dual_axis_intersection":
            selected = _sorted_intersection(x, y)
            return selected, int(bool(len(x))) + int(bool(len(y)))
        selected = []
        intervals = 0
        for segment in self.segments:
            if boxes_intersect(segment.mbr, rect):
                selected.append(self.segment_positions[segment.start:segment.end])
                intervals += 1
        return (
            np.concatenate(selected) if selected else np.empty(0, dtype=np.int64),
            intervals,
        )

    def candidate_count(self, rect):
        return int(len(self.query_candidates(rect)[0]))

    def query_counts_batch(self, queries):
        """Vectorized count path with the same search bounds as runtime queries."""

        queries = np.asarray(queries, dtype=np.float64)
        x_left = np.searchsorted(self.x_sorted_values, queries[:, 0], side="left")
        x_right = np.searchsorted(self.x_sorted_values, queries[:, 2], side="right")
        y_left = np.searchsorted(self.y_sorted_values, queries[:, 1], side="left")
        y_right = np.searchsorted(self.y_sorted_values, queries[:, 3], side="right")
        x_count = x_right - x_left; y_count = y_right - y_left
        if self.strategy == "x_rank":
            return x_count.astype(np.int64), (x_count > 0).astype(np.int64)
        if self.strategy == "y_rank":
            return y_count.astype(np.int64), (y_count > 0).astype(np.int64)
        if self.strategy == "adaptive_single_axis":
            count = np.minimum(x_count, y_count)
            return count.astype(np.int64), (count > 0).astype(np.int64)
        counts, intervals = [], []
        for query in queries:
            selected, interval_count = self.query_candidates(query)
            counts.append(len(selected)); intervals.append(interval_count)
        return np.asarray(counts, dtype=np.int64), np.asarray(intervals, dtype=np.int64)

    def index_size_breakdown(self):
        arrays = (
            self.x_sorted_values, self.x_sorted_positions,
            self.y_sorted_values, self.y_sorted_positions,
            self.segment_positions,
        )
        compact = int(sum(value.nbytes for value in arrays))
        segment_bytes = int(len(self.segments) * (2 * 8 + 4 * 8))
        return {
            "sorted_values_bytes": int(self.x_sorted_values.nbytes + self.y_sorted_values.nbytes),
            "sorted_positions_bytes": int(self.x_sorted_positions.nbytes + self.y_sorted_positions.nbytes),
            "suffix_segment_bytes": segment_bytes + int(self.segment_positions.nbytes),
            "compact_suffix_bytes": compact + segment_bytes,
            "python_runtime_suffix_estimate": compact + segment_bytes + len(self.segments) * 96 + 512,
        }
