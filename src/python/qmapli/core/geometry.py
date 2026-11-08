"""QMF index construction and range-query support."""

from __future__ import annotations

def boxes_intersect(box, query):
    return not (
        box[2] < query[0]
        or box[0] > query[2]
        or box[3] < query[1]
        or box[1] > query[3]
    )

def query_covers_box(query, box):
    return (
        query[0] <= box[0]
        and query[1] <= box[1]
        and query[2] >= box[2]
        and query[3] >= box[3]
    )
