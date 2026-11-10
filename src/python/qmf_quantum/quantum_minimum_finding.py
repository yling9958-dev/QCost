"""Finite-budget Dürr–Høyer/BBHT-style improvement using actual Aer circuit shots.

This is a quantum-circuit implementation on a classical simulator, not a QPU.
The controller never inspects all costs to obtain marked counts or the optimum.
Original floating costs verify improvements; quantization collisions can leave
lower original costs unmarked. A measured unmarked but lower-cost state may
still improve the incumbent. No exact-optimum certificate under finite budget.
"""
from dataclasses import asdict
import math
import time
import numpy as np
from .classical_controller import QueryAccounting, maximum_iterations
from .quantum_backend import GateBackend


def gate_level_qmf(costs, quantized_costs, bits: int, *, budget: int, seed: int,
                   backend: GateBackend | None = None, bbht_lambda=8 / 7):
    x = np.asarray(costs, dtype=np.float64)
    codes = np.asarray(quantized_costs, dtype=np.int64)
    if len(x) != len(codes) or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError('Original/quantized tables must have equal nonempty size >=2')
    if budget < 1 or not 1 < bbht_lambda < 4 / 3:
        raise ValueError('Positive budget and BBHT growth in (1,4/3) required')
    started = time.perf_counter()
    backend = backend or GateBackend(codes, bits)
    if backend.costs != tuple(codes) or backend.bits != bits:
        raise ValueError('Backend table or cost width mismatch')
    rng = np.random.default_rng(seed)
    incumbent = int(rng.choice(len(x), p=np.full(len(x), 1 / len(x))))
    initial = incumbent
    initial_cost = float(x[incumbent])
    accounting = QueryAccounting()
    m = 1.0
    padded_size = 1 << ((len(x) - 1).bit_length())
    history = []
    update_time = 0.0
    while accounting.budget_charged_units < budget:
        remaining = budget - accounting.budget_charged_units
        j = int(rng.integers(0, maximum_iterations(m, remaining) + 1))
        threshold = int(codes[incumbent])
        measurement_seed = int(rng.integers(0, (1 << 31) - 1))
        measured, execution = backend.measure_one(threshold, j, measurement_seed)
        accounting.logical_oracle_queries += j
        accounting.grover_iterations += j
        accounting.quantum_circuit_executions += 1
        accounting.shots += 1
        accounting.budget_charged_units += j + 1
        update_started = time.perf_counter()
        before = incumbent
        valid = measured < len(x)
        improved = False
        marked = False
        if valid:
            accounting.classical_verification_queries += 1
            marked = bool(codes[measured] < threshold)
            improved = bool(x[measured] < x[incumbent])
            if improved:
                incumbent, m = measured, 1.0
            else:
                m = min(bbht_lambda * m, math.sqrt(padded_size))
        else:
            accounting.invalid_address_measurements += 1
            m = min(bbht_lambda * m, math.sqrt(padded_size))
        update_time += time.perf_counter() - update_started
        history.append({**execution.as_dict(), 'measured_address': measured,
                        'valid_address': valid, 'marked_at_measurement': marked,
                        'improved_original_cost': improved, 'incumbent_before': before,
                        'incumbent_after': incumbent, 'cost_after': float(x[incumbent]),
                        'next_m': m})
    times = {name: sum(r[name] for r in history) for name in
             ['synthesis_seconds', 'transpilation_seconds', 'simulation_seconds']}
    times['classical_threshold_update_seconds'] = update_time
    total = time.perf_counter() - started
    times['total_search_seconds'] = total
    times['other_controller_seconds'] = max(0, total - sum(times[k] for k in
            ['synthesis_seconds', 'transpilation_seconds', 'simulation_seconds',
             'classical_threshold_update_seconds']))
    return {'method': 'Gate-Level QMF', 'seed': seed, 'budget': budget,
            'initial_index': initial, 'initial_cost': initial_cost,
            'selected_index': incumbent, 'selected_cost': float(x[incumbent]),
            'selected_quantized_cost': int(codes[incumbent]),
            'original_N': len(x), 'initialization_space': padded_size,
            'accounting': {**asdict(accounting), 'qrom_invocations': accounting.qrom_invocations},
            'times': times, 'history': history, 'finite_budget_optimality_guarantee': False,
            'controller': 'BBHT lambda=8/7, m reset after strict original-cost improvement',
            'tie_breaking': 'strict original-cost improvement; keep incumbent on equal original cost',
            'backend': 'Aer statevector, actual u/cx gates and measurement, no QPU'}
