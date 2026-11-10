#!/usr/bin/env python3
"""Independent real-gate Qiskit Aer validation; emits measured metrics only."""
import argparse
import csv
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/python'))
from qmf_quantum_circuit_prototype import run_grover_circuit, gate_level_qmf

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['QUICK', 'FULL'], default='QUICK')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cost-table', type=Path, help='Optional JSON integer-cost table for QUICK')
    p.add_argument('--max-size', type=int, choices=[4,8,16,32,64], default=64,
                   help='FULL: stop after this original staged size; values below 64 are partial runs')
    p.add_argument('--cost-bits', type=int, default=3)
    p.add_argument('--shots', type=int, default=2048)
    p.add_argument('--seed', type=int, default=42)
    a = p.parse_args()
    if a.mode == 'FULL':
        if a.cost_table:
            p.error('FULL uses the preserved original deterministic gate-validation tables')
        a.output.mkdir(parents=True, exist_ok=False)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT / 'src/python'))
        subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                        str(ROOT / 'tests/quantum')], env=env, check=True)
        stages = []
        for n in [4,8,16,32,64]:
            if n > a.max_size:
                break
            subprocess.run([sys.executable, '-B', '-m', 'qmf_quantum.stage_validation',
                            '--size', str(n), '--output-root', str(a.output.resolve())],
                           env=env, check=True)
            row = json.loads((a.output / f'stage_{n}/result.json').read_text())
            stages.append(dict(N=n, status=row['status'], tests_passed=row['tests_passed']))
        result = dict(status='PASS', mode='FULL', partial=a.max_size < 64, stages=stages,
                      original_protocol=True, synthetic_gate_validation_tables=True,
                      qiskit=importlib.metadata.version('qiskit'),
                      aer=importlib.metadata.version('qiskit-aer'), quantum_speedup_claimed=False)
        (a.output / 'quantum_validation.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return
    costs = json.loads(a.cost_table.read_text()) if a.cost_table else [7, 4, 5, 3, 6, 2, 1, 0]
    if a.shots < 1:
        p.error('shots must be positive')
    a.output.mkdir(parents=True, exist_ok=False)
    threshold = min(costs) + 1
    n = 2 ** math.ceil(math.log2(len(costs)))
    mass = sum(c < threshold for c in costs) / n
    rows = []
    for iterations in [0, 1, 2]:
        circuit, compiled, counts, observed = run_grover_circuit(
            costs, threshold, iterations, a.cost_bits, shots=a.shots, seed=a.seed)
        expected = math.sin((2 * iterations + 1) * math.asin(math.sqrt(mass))) ** 2
        # Sampling uncertainty is checked against a conservative finite-shot bound.
        assert abs(observed - expected) <= max(.08, 5 / math.sqrt(a.shots))
        rows.append(dict(iterations=iterations, shots=a.shots, qubits=circuit.num_qubits,
                         depth=compiled.depth(), gates=sum(compiled.count_ops().values()),
                         gate_counts=dict(compiled.count_ops()), counts=counts,
                         expected_probability=expected, measured_probability=observed))
    result = dict(status='PASS', mode=a.mode, synthetic_demonstration=a.cost_table is None,
                  original_paper_figure_reproduced=False, costs=costs, threshold=threshold,
                  cost_bits=a.cost_bits, seed=a.seed, circuits=rows,
                  qmf=gate_level_qmf(costs, a.cost_bits, seed=a.seed, max_trials=20, max_grover_iterations=24),
                  qiskit=importlib.metadata.version('qiskit'), aer=importlib.metadata.version('qiskit-aer'),
                  classical_precomputation='Costs supplied classically; reversible table QROM synthesis is O(N)',
                  quantum_speedup_claimed=False)
    (a.output / 'quantum_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
