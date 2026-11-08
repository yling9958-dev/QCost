"""Small-scale, genuine quantum-circuit QMF prototype (Qiskit >= 2, Aer).

Key distinction: coherent cost lookup is synthesized *from a classical integer
cost table* using controlled quantum gates. Grover iterations and measurement
are real quantum-circuit simulation, NOT analytic probability sampling.
The complete workflow does NOT claim end-to-end quantum speedup, because
classical cost precomputation and QROM circuit synthesis are O(N).

Run in a separate Python environment:
    pip install 'qiskit>=2,<3' 'qiskit-aer>=0.17,<1'
    python qmf_quantum_circuit_prototype.py --shots 2048 --output ./qmf_circuit_output
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Sequence


def _qiskit():
    try:
        from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
        from qiskit_aer import AerSimulator
    except ImportError as exc:
        raise RuntimeError(
            "Qiskit/Aer unavailable. Install into an isolated environment: "
            "pip install 'qiskit>=2,<3' 'qiskit-aer>=0.17,<1'"
        ) from exc
    return QuantumCircuit, QuantumRegister, ClassicalRegister, transpile, AerSimulator


def _validate_costs(costs: Sequence[int], cost_bits: int) -> tuple[int, list[int]]:
    vals = [int(c) for c in costs]
    if len(vals) < 2 or any(c < 0 or c >= 2**cost_bits for c in vals):
        raise ValueError("Need >=2 nonnegative integer costs fitting in cost_bits")
    if any(int(c) != c for c in costs):
        raise ValueError("Costs must be exact integers; quantize floats explicitly")
    n = max(1, (len(vals)-1).bit_length())
    # Invalid address states are deliberately never marked, since threshold
    # is always an actual cost and padding is the largest b-bit value.
    padded = vals + [2**cost_bits - 1] * (2**n - len(vals))
    return n, padded


def qrom_cost_xor(qc, address, cost_register, padded_costs: Sequence[int]):
    """Unitary |i>|v> -> |i>|v XOR C[i]> by multi-controlled X gates.

    Applying the same operation twice restores the cost register to zero.
    This is a real reversible QROM lookup synthesized from an existing table.
    """
    n = len(address)
    for idx, cost in enumerate(padded_costs):
        active_bits = [b for b in range(len(cost_register)) if (cost >> b) & 1]
        if not active_bits:
            continue
        zero_controls = [address[k] for k in range(n) if not ((idx >> k) & 1)]
        for q in zero_controls:
            qc.x(q)
        for b in active_bits:
            qc.mcx(list(address), cost_register[b])
        for q in reversed(zero_controls):
            qc.x(q)


def reversible_less_than_xor(qc, value, flag, threshold: int):
    """XOR [value < threshold] into flag using disjoint binary prefixes.

    No arithmetic library or measured classical control is used. For every
    set bit j in threshold, recognize values equal on higher bits but zero at
    bit j. These patterns are disjoint, hence XOR is equal to logical OR.
    Calling twice uncomputes the flag.
    """
    b = len(value)
    if threshold < 0 or threshold > 2**b:
        raise ValueError("Threshold outside cost register")
    if threshold == 0:
        return
    if threshold == 2**b:
        qc.x(flag)
        return
    for j in range(b-1, -1, -1):
        if (threshold >> j) & 1 == 0:
            continue
        controls = list(range(j, b))
        zero_indices = [k for k in controls
                        if (k == j or ((threshold >> k) & 1) == 0)]
        for k in zero_indices:
            qc.x(value[k])
        qc.mcx([value[k] for k in controls], flag)
        for k in reversed(zero_indices):
            qc.x(value[k])


def threshold_phase_oracle(qc, address, cost_register, flag, padded_costs,
                           threshold: int):
    """|i>|0>|0> -> (-1)^[C[i]<tau] |i>|0>|0>.

    Actual gate sequence: load cost, reversible comparison, Z phase on flag,
    uncompute comparison, uncompute cost. All workspace returns to zero.
    """
    qrom_cost_xor(qc, address, cost_register, padded_costs)
    reversible_less_than_xor(qc, cost_register, flag, threshold)
    qc.z(flag)
    reversible_less_than_xor(qc, cost_register, flag, threshold)
    qrom_cost_xor(qc, address, cost_register, padded_costs)


def grover_diffuser(qc, address):
    """Reflection about |+>^n, up to a physically irrelevant global phase."""
    qc.h(address)
    qc.x(address)
    if len(address) == 1:
        qc.z(address[0])
    else:
        qc.h(address[-1])
        qc.mcx(list(address[:-1]), address[-1])
        qc.h(address[-1])
    qc.x(address)
    qc.h(address)


def build_grover_circuit(costs: Sequence[int], threshold: int,
                         grover_iterations: int, cost_bits: int):
    QuantumCircuit, QuantumRegister, ClassicalRegister, _, _ = _qiskit()
    n, padded = _validate_costs(costs, cost_bits)
    if grover_iterations < 0:
        raise ValueError("grover_iterations must be >= 0")
    address = QuantumRegister(n, 'address')
    value = QuantumRegister(cost_bits, 'cost')
    flag = QuantumRegister(1, 'less')
    measured = ClassicalRegister(n, 'readout')
    qc = QuantumCircuit(address, value, flag, measured,
                        name='Gate-level threshold QMF')
    qc.h(address)
    for _ in range(grover_iterations):
        threshold_phase_oracle(qc, address, value, flag[0], padded, threshold)
        grover_diffuser(qc, address)
    qc.measure(address, measured)
    return qc


def run_grover_circuit(costs: Sequence[int], threshold: int,
                       grover_iterations: int, cost_bits: int,
                       shots: int, seed: int = 42):
    _, _, _, transpile, AerSimulator = _qiskit()
    qc = build_grover_circuit(costs, threshold, grover_iterations, cost_bits)
    simulator = AerSimulator(method='statevector')
    compiled = transpile(qc, simulator, optimization_level=1,
                         seed_transpiler=seed)
    result = simulator.run(compiled, shots=shots,
                           seed_simulator=seed).result()
    counts = result.get_counts(compiled)
    marked_hits = sum(count for key, count in counts.items()
                      if int(key.replace(' ', ''), 2) < len(costs)
                      and int(costs[int(key.replace(' ', ''), 2)]) < threshold)
    return qc, compiled, counts, marked_hits / shots


def gate_level_qmf(costs: Sequence[int], cost_bits: int, seed: int = 42,
                   max_trials: int = 16, max_grover_iterations: int = 24):
    """Durr-Hoyer/BBHT-style *gate-executed* threshold-improvement controller.

    Classical outer-loop incumbent/threshold, coherent Grover circuits on Aer.
    Sample by one actual circuit shot per attempt, never analytic RNG weights.
    No optimality guarantee under a fixed budget.
    """
    _, _, _, transpile, AerSimulator = _qiskit()
    n, _ = _validate_costs(costs, cost_bits)
    rng = random.Random(seed)
    incumbent = rng.randrange(len(costs))
    threshold = int(costs[incumbent])
    m = 1
    total_iterations = 0
    oracle_invocations = 0
    history = []
    backend = AerSimulator(method='statevector')
    for trial in range(max_trials):
        if threshold == 0 or total_iterations >= max_grover_iterations:
            break
        j = rng.randrange(m)
        if total_iterations + j > max_grover_iterations:
            j = max_grover_iterations - total_iterations
        circuit = build_grover_circuit(costs, threshold, j, cost_bits)
        compiled = transpile(circuit, backend, optimization_level=1,
                             seed_transpiler=seed + trial)
        result = backend.run(compiled, shots=1, memory=True,
                             seed_simulator=seed + trial).result()
        measured = result.get_memory(compiled)[0].replace(' ', '')
        idx = int(measured, 2)
        accepted = idx < len(costs) and int(costs[idx]) < threshold
        if accepted:
            incumbent, threshold, m = idx, int(costs[idx]), 1
        else:
            m = min(max(1, math.ceil(1.2*m)), 2**n)
        oracle_invocations += j
        total_iterations += j
        history.append({'trial':trial, 'grover_iterations':j,
                        'measured_index':idx, 'improved':accepted,
                        'incumbent':incumbent, 'threshold':threshold,
                        'qubits':circuit.num_qubits, 'depth':compiled.depth()})
    return {'best_index':incumbent, 'best_cost':threshold,
            'oracle_calls':oracle_invocations,
            'measurement_attempts':len(history), 'history':history}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shots',type=int,default=2048)
    parser.add_argument('--output',type=Path,default=Path('qmf_circuit_output'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    costs=[7, 4, 5, 3, 6, 2, 1, 0]
    threshold=1
    grover_iterations=2
    circuit, compiled, counts, marked_rate = run_grover_circuit(
        costs, threshold, grover_iterations, 3, args.shots)
    p=1/len(costs)
    expected=math.sin((2*grover_iterations+1)*math.asin(math.sqrt(p)))**2
    qmf_result=gate_level_qmf(costs,3,seed=42,max_trials=20,
                              max_grover_iterations=24)
    report={'costs':costs, 'threshold':threshold,
            'address_qubits':3, 'cost_qubits':3, 'flag_qubits':1,
            'iterations':grover_iterations, 'shots':args.shots,
            'expected_marked_probability':expected,
            'measured_marked_probability':marked_rate,
            'circuit_depth':compiled.depth(),
            'transpiled_gate_counts':dict(compiled.count_ops()),
            'measurement_counts':counts, 'qmf_result':qmf_result,
            'quantum_speedup_claimed':False,
            'cost_oracle':'table-based reversible QROM + threshold comparator'}
    (args.output/'report.json').write_text(
        json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (args.output/'circuit.txt').write_text(
        str(circuit.draw(output='text')),encoding='utf-8')
    try:
        fig=circuit.draw(output='mpl',fold=24,scale=0.65)
        fig.savefig(args.output/'circuit.png',dpi=180,bbox_inches='tight')
    except (ImportError,RuntimeError) as exc:
        print('PNG not exported (visualization dependency missing):',exc)
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
