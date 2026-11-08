"""QMF index construction and range-query support."""

from __future__ import annotations

import numpy as np

def _quantize(points: np.ndarray, bits: int = 16) -> np.ndarray:
    return np.floor(np.clip(points, 0, 1) * ((1 << bits) - 1)).astype(np.uint64)

def zorder_code(points: np.ndarray, bits: int = 16) -> np.ndarray:
    q = _quantize(points, bits)
    x, y = q[:,0], q[:,1]
    code = np.zeros(len(points), dtype=np.uint64)
    for i in range(bits):
        code |= ((x >> i) & 1) << (2*i + 1)
        code |= ((y >> i) & 1) << (2*i)
    return code.astype(np.float64) / float((1 << (2*bits)) - 1)

def _rot(n: int, x: int, y: int, rx: int, ry: int):
    if ry == 0:
        if rx == 1:
            x = n - 1 - x
            y = n - 1 - y
        x, y = y, x
    return x, y

def _xy2d(n: int, x: int, y: int) -> int:
    d = 0; s = n // 2
    while s > 0:
        rx = 1 if (x & s) else 0
        ry = 1 if (y & s) else 0
        d += s * s * ((3 * rx) ^ ry)
        x, y = _rot(s, x, y, rx, ry)
        s //= 2
    return d

def hilbert_code(points: np.ndarray, bits: int = 12) -> np.ndarray:
    q = _quantize(points, bits).astype(np.int64)
    n = 1 << bits
    vals = np.fromiter((_xy2d(n, int(x), int(y)) for x, y in q), dtype=np.float64, count=len(q))
    return vals / float(n*n - 1)
