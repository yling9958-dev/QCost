"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Protocol

import numpy as np

from .configuration import JointUniverse

from .quantum import AnalyticAmplitudeBackend, normalized_prior

class AmplitudeBackend(Protocol):
    def measure(self, probabilities, costs, threshold, iterations, rng) -> int: ...

@dataclass
class OracleAccounting:
    threshold_oracle_calls: int = 0
    verification_cost_calls: int = 0
    prior_state_preparations: int = 0
    reflection_calls: int = 0
    measurements: int = 0

    @property
    def configuration_cost_evaluations(self) -> int:
        return self.threshold_oracle_calls + self.verification_cost_calls

    @property
    def total_logical_quantum_operations(self) -> int:
        return (
            self.threshold_oracle_calls
            + self.prior_state_preparations
            + self.reflection_calls
            + self.measurements
        )

@dataclass(frozen=True)
class SearchResult:
    method: str
    selected_index: int
    selected_cost: float
    accounting: OracleAccounting
    evaluated_indices: tuple[int, ...]
    best_cost_trace: tuple[float, ...]
    cost_evaluation_trace: tuple[int, ...]
    threshold_call_trace: tuple[int, ...]

class AbstractPhaseCostOracle:
    """Cost table is private to the abstract phase-oracle backend."""

    def __init__(self, costs: np.ndarray, backend: AmplitudeBackend | None = None):
        values = np.asarray(costs, dtype=np.float64)
        if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
            raise ValueError("costs must be one finite non-empty vector")
        self.__costs = values.copy()
        self.backend = backend or AnalyticAmplitudeBackend()
        self.__order = np.argsort(self.__costs, kind="mergesort")
        self.__sorted_costs = self.__costs[self.__order]
        self.__cached_prior: np.ndarray | None = None
        self.__cached_cumulative: np.ndarray | None = None

    @property
    def size(self) -> int:
        return len(self.__costs)

    def evaluate(self, index: int) -> float:
        return float(self.__costs[int(index)])

    def measure(self, probabilities, threshold, iterations, rng) -> int:
        if isinstance(self.backend, AnalyticAmplitudeBackend):
            prior = normalized_prior(probabilities)
            if self.__cached_prior is None or not np.array_equal(prior, self.__cached_prior):
                self.__cached_prior = prior.copy()
                self.__cached_cumulative = np.cumsum(prior[self.__order])
                self.__cached_cumulative[-1] = 1.0
            assert self.__cached_cumulative is not None
            cutoff = int(np.searchsorted(self.__sorted_costs, float(threshold), side="left"))
            good_mass = float(self.__cached_cumulative[cutoff - 1]) if cutoff else 0.0
            if good_mass <= 1e-15 or good_mass >= 1.0 - 1e-15:
                target = float(rng.random())
            else:
                theta = float(np.arcsin(np.sqrt(good_mass)))
                amplified = float(np.sin((2 * int(iterations) + 1) * theta) ** 2)
                if float(rng.random()) < amplified:
                    target = float(rng.random()) * good_mass
                else:
                    target = good_mass + float(rng.random()) * (1.0 - good_mass)
            position = min(
                int(np.searchsorted(self.__cached_cumulative, target, side="right")),
                self.size - 1,
            )
            return int(self.__order[position])
        return self.backend.measure(
            probabilities, self.__costs, float(threshold), int(iterations), rng
        )

def _qmf(
    oracle: AbstractPhaseCostOracle,
    probabilities: np.ndarray,
    *,
    budget: int,
    seed: int,
    method: str,
    bbht_lambda: float = 8.0 / 7.0,
) -> SearchResult:
    prior = normalized_prior(probabilities)
    if len(prior) != oracle.size:
        raise ValueError("prior and cost-oracle sizes differ")
    budget = int(budget)
    if budget < 1:
        raise ValueError("oracle budget must be positive")
    rng = np.random.default_rng(int(seed))
    accounting = OracleAccounting(prior_state_preparations=1, measurements=1)
    incumbent = int(rng.choice(oracle.size, p=prior))
    incumbent_cost = oracle.evaluate(incumbent)
    accounting.verification_cost_calls += 1
    evaluated = [incumbent]
    trace = [incumbent_cost]
    cost_call_trace = [accounting.configuration_cost_evaluations]
    threshold_trace = [accounting.threshold_oracle_calls]
    m = 1.0
    while accounting.configuration_cost_evaluations < budget:
        remaining = budget - accounting.configuration_cost_evaluations
        maximum_iterations = min(max(int(np.ceil(m)) - 1, 0), max(remaining - 1, 0))
        iterations = int(rng.integers(0, maximum_iterations + 1))
        accounting.prior_state_preparations += 1
        accounting.threshold_oracle_calls += iterations
        accounting.reflection_calls += iterations
        measured = oracle.measure(prior, incumbent_cost, iterations, rng)
        accounting.measurements += 1
        measured_cost = oracle.evaluate(measured)
        accounting.verification_cost_calls += 1
        evaluated.append(measured)
        if measured_cost < incumbent_cost:
            incumbent, incumbent_cost, m = measured, measured_cost, 1.0
        else:
            m = min(float(bbht_lambda) * m, float(np.sqrt(oracle.size)))
        trace.append(incumbent_cost)
        cost_call_trace.append(accounting.configuration_cost_evaluations)
        threshold_trace.append(accounting.threshold_oracle_calls)
    return SearchResult(
        method=method,
        selected_index=incumbent,
        selected_cost=incumbent_cost,
        accounting=accounting,
        evaluated_indices=tuple(evaluated),
        best_cost_trace=tuple(trace),
        cost_evaluation_trace=tuple(cost_call_trace),
        threshold_call_trace=tuple(threshold_trace),
    )

def workload_guided_qmf(
    costs,
    probabilities,
    *,
    budget,
    seed,
    backend=None,
    bbht_lambda=8.0 / 7.0,
) -> SearchResult:
    oracle = AbstractPhaseCostOracle(costs, backend)
    return _qmf(
        oracle,
        probabilities,
        budget=budget,
        seed=seed,
        method="WG-QMF",
        bbht_lambda=bbht_lambda,
    )

def uniform_qmf(
    costs,
    *,
    budget,
    seed,
    backend=None,
    bbht_lambda=8.0 / 7.0,
) -> SearchResult:
    costs = np.asarray(costs, dtype=np.float64)
    oracle = AbstractPhaseCostOracle(costs, backend)
    return _qmf(
        oracle,
        np.full(len(costs), 1.0 / len(costs)),
        budget=budget,
        seed=seed,
        method="Uniform-QMF",
        bbht_lambda=bbht_lambda,
    )

def _classical_result(method, costs, order, budget):
    values = np.asarray(costs, dtype=np.float64)
    selected = None
    selected_cost = float("inf")
    evaluated, trace = [], []
    for index in list(order)[: int(budget)]:
        value = float(values[int(index)])
        evaluated.append(int(index))
        if value < selected_cost:
            selected, selected_cost = int(index), value
        trace.append(selected_cost)
    if selected is None:
        raise ValueError("classical search budget must be positive")
    return SearchResult(
        method=method,
        selected_index=selected,
        selected_cost=selected_cost,
        accounting=OracleAccounting(verification_cost_calls=len(evaluated)),
        evaluated_indices=tuple(evaluated),
        best_cost_trace=tuple(trace),
        cost_evaluation_trace=tuple(range(1, len(evaluated) + 1)),
        threshold_call_trace=tuple(0 for _ in evaluated),
    )

def exhaustive_search(costs) -> SearchResult:
    return _classical_result("Exhaustive", costs, range(len(costs)), len(costs))

def prior_best_first(costs, probabilities, *, budget) -> SearchResult:
    prior = normalized_prior(probabilities)
    order = sorted(range(len(prior)), key=lambda index: (-prior[index], index))
    return _classical_result("Prior-Best-First", costs, order, budget)

def beam_search(costs, universe: JointUniverse, *, width: int, budget: int | None = None):
    """Beam over action-key prefixes scored by their joint prior mass."""

    configurations = universe.configurations
    prior = universe.probabilities
    prefixes: list[tuple[str, ...]] = [()]
    action_count = len(configurations[0].action_keys)
    for depth in range(action_count):
        candidates: dict[tuple[str, ...], float] = {}
        allowed = set(prefixes)
        for configuration, probability in zip(configurations, prior, strict=True):
            parent = configuration.action_keys[:depth]
            if parent not in allowed:
                continue
            child = configuration.action_keys[: depth + 1]
            candidates[child] = candidates.get(child, 0.0) + float(probability)
        prefixes = [
            prefix
            for prefix, _mass in sorted(
                candidates.items(), key=lambda item: (-item[1], item[0])
            )[: int(width)]
        ]
    selected = {
        configuration.action_keys: index for index, configuration in enumerate(configurations)
    }
    order = [selected[prefix] for prefix in prefixes]
    limit = len(order) if budget is None else min(int(budget), len(order))
    return _classical_result(f"Beam{int(width)}", costs, order, limit)
