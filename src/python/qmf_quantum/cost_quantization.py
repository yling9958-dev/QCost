"""Monotone affine quantization, reserving the maximum code for invalid addresses."""
from dataclasses import dataclass, asdict
import numpy as np


@dataclass(frozen=True)
class Quantization:
    bits: int
    minimum: float
    maximum: float
    valid_max_code: int
    invalid_code: int
    step: float
    max_abs_error: float
    original_minimum_count: int
    quantized_minimum_count: int
    all_quantized_minima_original_optimal: bool
    monotonic_order_preserved: bool
    distinct_original: int
    distinct_quantized: int

    def as_dict(self):
        return asdict(self)


def quantize_costs(costs, bits: int) -> tuple[np.ndarray, Quantization]:
    x = np.asarray(costs, dtype=np.float64)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError('Need >=2 finite nonnegative costs')
    if not isinstance(bits, int) or not 2 <= bits <= 16:
        raise ValueError('Cost width must be an integer in [2,16]')
    lo, hi = float(x.min()), float(x.max())
    maximum_code = (1 << bits) - 2
    step = (hi - lo) / maximum_code
    codes = np.zeros(len(x), dtype=np.int64) if hi == lo else np.rint((x - lo) / step).astype(np.int64)
    codes = np.clip(codes, 0, maximum_code)
    decoded = lo + codes * step
    order = np.argsort(x, kind='stable')
    minimum_mask = x == lo
    quantized_mask = codes == codes.min()
    info = Quantization(bits, lo, hi, maximum_code, maximum_code + 1, step,
                        float(np.max(np.abs(decoded - x))), int(minimum_mask.sum()),
                        int(quantized_mask.sum()), bool(np.all(minimum_mask[quantized_mask])),
                        bool(np.all(np.diff(codes[order]) >= 0)), len(np.unique(x)), len(np.unique(codes)))
    return codes, info
