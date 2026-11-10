"""Count actual decomposed circuit operations; no oracle/gate-count conflation."""
from collections import Counter


def circuit_resources(compiled):
    quantum_ops = [x for x in compiled.data if x.operation.name not in
                   {'measure', 'barrier', 'save_statevector'}]
    counts = Counter(x.operation.name for x in quantum_ops)
    arities = Counter(len(x.qubits) for x in quantum_ops)
    return {'transpiled_qubits': compiled.num_qubits,
            'transpiled_depth': compiled.depth(),
            'single_qubit_gates': arities[1], 'two_qubit_gates': arities[2],
            'residual_multi_qubit_gates': sum(v for k, v in arities.items() if k > 2),
            'gate_counts': dict(counts), 'basis': ['u', 'cx'],
            'hardware_coupling_map': None, 'optimization_level': 1}
