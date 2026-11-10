"""Aer executes compiled u/cx gates and measurement, never analytic Grover sampling."""
from collections import OrderedDict
from dataclasses import dataclass, asdict
import time
from qiskit import transpile
from qiskit_aer import AerSimulator
from .grover_diffusion import build_grover_circuit
from .resource_profiler import circuit_resources


def evolve_circuit_state(qc):
    """Exact Aer statevector from decomposed gates; no matrix-form oracle shortcut."""
    simulator = AerSimulator(method='statevector', max_parallel_threads=2,
                             max_parallel_experiments=1, max_memory_mb=2048)
    compiled = transpile(qc, basis_gates=['u', 'cx'], optimization_level=1,
                         seed_transpiler=20261009, num_processes=1)
    compiled.save_statevector()
    result = simulator.run(compiled, shots=1, seed_simulator=20261009).result()
    if not result.success:
        raise RuntimeError(str(result.status))
    import numpy as np
    return np.asarray(result.get_statevector())


@dataclass
class CircuitExecution:
    threshold: int
    grover_iterations: int
    shots: int
    seed_simulator: int
    counts: dict
    synthesis_seconds: float
    transpilation_seconds: float
    simulation_seconds: float
    cache_hit: bool
    resources: dict

    def as_dict(self):
        return asdict(self)


class GateBackend:
    def __init__(self, costs, bits: int, *, cache=True):
        self.costs = tuple(int(x) for x in costs)
        self.bits = bits
        self.simulator = AerSimulator(method='statevector', max_parallel_threads=2,
                                      max_parallel_experiments=1, max_parallel_shots=1,
                                      max_memory_mb=2048)
        self.cache_enabled = cache
        self.cache = OrderedDict()
        self.cache_operations = 0

    def execute(self, threshold: int, iterations: int, *, shots: int, seed: int):
        if shots < 1:
            raise ValueError('Positive shots required')
        key = (threshold, iterations)
        hit = key in self.cache
        if hit:
            compiled, resources, _ = self.cache.pop(key)
            self.cache[key] = (compiled, resources, len(compiled.data))
            synthesis = compilation = 0.0
        else:
            started = time.perf_counter()
            qc, layout = build_grover_circuit(self.costs, self.bits, threshold, iterations)
            synthesis = time.perf_counter() - started
            started = time.perf_counter()
            compiled = transpile(qc, basis_gates=['u', 'cx'], optimization_level=1,
                                 seed_transpiler=20261009, num_processes=1)
            compilation = time.perf_counter() - started
            resources = {**layout.as_dict(), **circuit_resources(compiled)}
            if resources['residual_multi_qubit_gates']:
                raise RuntimeError('Basis decomposition incomplete')
            operations = len(compiled.data)
            if self.cache_enabled and operations <= 150000:
                while self.cache and self.cache_operations + operations > 150000:
                    _, (_, _, removed) = self.cache.popitem(last=False)
                    self.cache_operations -= removed
                self.cache[key] = (compiled, resources, operations)
                self.cache_operations += operations
        started = time.perf_counter()
        result = self.simulator.run(compiled, shots=int(shots), seed_simulator=int(seed)).result()
        simulation = time.perf_counter() - started
        if not result.success:
            raise RuntimeError(str(result.status))
        counts = {str(k).replace(' ', ''): int(v) for k, v in result.get_counts().items()}
        return CircuitExecution(threshold, iterations, int(shots), int(seed), counts,
                                synthesis, compilation, simulation, hit, resources)

    def measure_one(self, threshold: int, iterations: int, seed: int):
        execution = self.execute(threshold, iterations, shots=1, seed=seed)
        # A single actual quantum measurement; there is no classical weighted sampler.
        selected = int(next(iter(execution.counts)), 2)
        return selected, execution
