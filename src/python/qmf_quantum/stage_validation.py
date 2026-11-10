"""Barriered, small-scale gate correctness and statistics; each size is a separate task."""
import argparse
import json
import math
import os
from pathlib import Path
import time
import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qmf_quantum.qrom_oracle import qrom_gate, padded_table, qrom_logical_controls
from qmf_quantum.phase_oracle import oracle_circuit
from qmf_quantum.reversible_comparator import comparator_gate
from qmf_quantum.grover_diffusion import build_grover_circuit
from qmf_quantum.quantum_backend import GateBackend, evolve_circuit_state
from qmf_quantum.quantum_minimum_finding import gate_level_qmf
from qmf_quantum.cost_quantization import quantize_costs
from qmf_quantum.configuration_adapter import ConfigurationRecord, ConfigurationTable



def encode(qc, start, bits, integer):
    for k in range(bits):
        if (integer >> k) & 1:
            qc.x(start + k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', type=int, choices=[4, 8, 16, 32, 64], required=True)
    ap.add_argument('--statevector-method', choices=['qiskit', 'aer'], default='qiskit')
    ap.add_argument('--output-root', type=Path, required=True)
    args = ap.parse_args()
    n = args.size
    ROOT = args.output_root
    JOB = ROOT / f'stage_{n}'
    JOB.mkdir(parents=True, exist_ok=False)
    def evolve(qc):
        return evolve_circuit_state(qc) if args.statevector_method == 'aer' else Statevector.from_instruction(qc).data
    # The independent release wrapper executes the retained unit tests before
    # these staged experiments. Historical guard receipt paths are not inputs.
    if n > 4:
        previous = ROOT / f'stage_{n // 2}'
        assert json.loads((previous / 'result.json').read_text())['status'] == 'PASS'
    tests = []
    started = time.perf_counter()
    bits = 4
    values = [1 + (13 * i) % 14 for i in range(n)]
    values[n // 2] = 0
    lookup, layout = qrom_gate(values, bits)
    table, _ = padded_table(values, bits)
    for i in range(n):
        qc = QuantumCircuit(layout.address + bits)
        encode(qc, 0, layout.address, i)
        qc.append(lookup, qc.qubits)
        state = evolve(qc)
        assert abs(abs(state[i + (values[i] << layout.address)]) - 1) < 1e-9
        qc.append(lookup.inverse(), qc.qubits)
        state = evolve(qc)
        assert abs(abs(state[i]) - 1) < 1e-9
    tests.append({'test': 1, 'name': 'QROM basis lookup', 'status': 'PASS', 'basis_states': n})
    qc = QuantumCircuit(layout.address + bits)
    qc.h(range(layout.address))
    qc.append(lookup, qc.qubits)
    state = evolve(qc)
    expected = np.zeros_like(state)
    for i, c in enumerate(values):
        expected[i + (c << layout.address)] = 1 / math.sqrt(n)
    assert np.allclose(state, expected, atol=1e-9)
    tests.append({'test': 2, 'name': 'QROM superposition', 'status': 'PASS'})
    for tau in [0, 1, 7, 15, 16]:
        gate = comparator_gate(bits, tau)
        for c in range(16):
            qc = QuantumCircuit(bits + 1)
            encode(qc, 0, bits, c)
            qc.append(gate, qc.qubits)
            state = evolve(qc)
            assert abs(abs(state[c + (int(c < tau) << bits)]) - 1) < 1e-9
    tests.append({'test': 3, 'name': 'Reversible comparator', 'status': 'PASS'})
    for tau in [0, 1, 7, 15]:
        oracle, layout = oracle_circuit(values, bits, tau)
        qc = QuantumCircuit(*oracle.qregs)
        qc.h(qc.qregs[0])
        qc.compose(oracle, inplace=True)
        state = evolve(qc)
        expected = np.array([-1 if v < tau else 1 for v in values]) / math.sqrt(n)
        reference = next((i for i, v in enumerate(values) if v >= tau), 0)
        assert np.allclose(state[:n] / state[reference], expected / expected[reference], atol=1e-9)
        assert np.linalg.norm(state[n:]) < 1e-9
    tests += [{'test': 4, 'name': 'Relative phase signs including global-phase cases', 'status': 'PASS'},
              {'test': 5, 'name': 'Clean cost/flag/ancilla uncomputation', 'status': 'PASS'}]
    jopt = max(1, int(math.floor(math.pi / 4 * math.sqrt(n) - 0.5)))
    measurements = []
    resources = []
    # Wider registers are validated by real coherent Grover circuits too.
    for b in [4, 6, 8]:
        wide = [1 + (13 * i) % ((1 << b) - 2) for i in range(n)]
        wide[n // 2] = 0
        backend = GateBackend(wide, b)
        js = sorted({0, 1, jopt}) if b == 4 else [1]
        for j in js:
            qc, this_layout = build_grover_circuit(wide, b, 1, j, measure=False)
            state = evolve(qc)
            theory = math.sin((2 * j + 1) * math.asin(math.sqrt(1 / n))) ** 2
            actual = float(abs(state[n // 2]) ** 2)
            assert abs(actual - theory) < 1e-8
            assert np.linalg.norm(state[n:]) < 1e-8
            for seed in range(20261009, 20261014):
                execution = backend.execute(1, j, shots=2048, seed=seed)
                hit = sum(v for k, v in execution.counts.items() if int(k, 2) == n // 2) / 2048
                tolerance = max(0.035, 6 * math.sqrt(theory * (1 - theory) / 2048))
                assert abs(hit - theory) < tolerance
                measurements.append({'N': n, 'bits': b, 'j': j, 'M': 1, 'space': n,
                                     'seed': seed, 'shots': 2048, 'theory': theory,
                                     'statevector_probability': actual, 'measured_probability': hit})
                if seed == 20261009:
                    resources.append({'N': n, 'bits': b, 'j': j,
                                      'qrom_logical_controlled_x': qrom_logical_controls(wide, b),
                                      **execution.as_dict()})
    tests += [{'test': 6, 'name': 'Grover exact amplification', 'status': 'PASS', 'bits': [4, 6, 8]},
              {'test': 7, 'name': 'Actual Aer measurement distribution', 'status': 'PASS', 'seeds': 5}]
    seeds = list(range(20261009, 20261029))
    minimum_runs = []
    backend = GateBackend(values, bits)
    for seed in seeds:
        run = gate_level_qmf(values, values, bits, budget=math.ceil(2 * math.sqrt(n)), seed=seed, backend=backend)
        assert 0 <= run['selected_index'] < n
        assert run['selected_cost'] == values[run['selected_index']]
        assert run['selected_cost'] <= run['initial_cost']
        minimum_runs.append(run)
    tests.append({'test': 8, 'name': 'Finite-budget QMF validity and monotonicity', 'status': 'PASS',
                  'seeds': 20, 'hit_rate': sum(r['selected_cost'] == 0 for r in minimum_runs) / 20,
                  'optimality_guarantee': False})
    for b in [4, 6, 8]:
        _, q = quantize_costs(np.array(values) * 1.234567 + 10, b)
        assert q.monotonic_order_preserved and q.max_abs_error <= q.step / 2 + 1e-10
    tests.append({'test': 9, 'name': 'Quantization monotonicity/error', 'status': 'PASS'})
    mock = tuple(ConfigurationRecord(i, {'key': f'root_{i % 2}'}, float(v), (), 1 / n)
                 for i, v in enumerate(values))
    mapping = ConfigurationTable(mock, {'scope': 'mapping unit test; synthetic IDs'}, {'root_0': 0, 'root_1': 1}, 0)
    for i, record in enumerate(mock):
        assert mapping.reconstruct(i) == record
    tests.append({'test': 10, 'name': 'Address to configuration/root mapping unit test', 'status': 'PASS',
                  'real_data_test': 'pending Phase 7'})
    out = {'status': 'PASS', 'N': n, 'main_bits': 4, 'validated_coherent_bits': [4, 6, 8],
           'statevector_validation_method': args.statevector_method,
           'provenance': 'deterministic synthetic cost table for gate correctness only',
           'seeds': seeds, 'tests': tests, 'tests_passed': len(tests), 'tests_failed': 0,
           'measurement_results': measurements, 'resource_results': resources,
           'minimum_finding_runs': minimum_runs, 'elapsed_seconds': time.perf_counter() - started}
    with (JOB / 'result.json').open('x') as f:
        json.dump(out, f, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k not in
                      ['measurement_results', 'resource_results', 'minimum_finding_runs']}, indent=2))


if __name__ == '__main__':
    main()
