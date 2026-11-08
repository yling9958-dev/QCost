"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

def normalized_prior(probabilities: np.ndarray) -> np.ndarray:
    values = np.asarray(probabilities, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0 or np.any(values < 0) or not np.isfinite(values).all():
        raise ValueError("prior probabilities must be finite and non-negative")
    total = float(values.sum())
    if total <= 0:
        raise ValueError("prior probability mass must be positive")
    return values / total

def analytic_distribution(
    probabilities: np.ndarray,
    costs: np.ndarray,
    threshold: float,
    iterations: int,
) -> np.ndarray:
    """Two-subspace simulation; marked mass is backend-private information."""

    prior = normalized_prior(probabilities)
    marked = np.asarray(costs, dtype=np.float64) < float(threshold)
    good_mass = float(prior[marked].sum())
    if good_mass <= 1e-15 or good_mass >= 1.0 - 1e-15:
        return prior.copy()
    theta = float(np.arcsin(np.sqrt(good_mass)))
    amplified = float(np.sin((2 * int(iterations) + 1) * theta) ** 2)
    output = np.empty_like(prior)
    output[marked] = prior[marked] * amplified / good_mass
    output[~marked] = prior[~marked] * (1.0 - amplified) / (1.0 - good_mass)
    output /= output.sum()
    return output

@dataclass(frozen=True)
class AnalyticAmplitudeBackend:
    def distribution(self, probabilities, costs, threshold, iterations):
        return analytic_distribution(probabilities, costs, threshold, iterations)

    def measure(self, probabilities, costs, threshold, iterations, rng):
        distribution = self.distribution(probabilities, costs, threshold, iterations)
        return int(rng.choice(len(distribution), p=distribution))
