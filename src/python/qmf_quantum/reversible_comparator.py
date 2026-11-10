"""Strict less-than XOR comparator using disjoint binary prefixes, no carry ancilla."""
from qiskit import QuantumCircuit, QuantumRegister
from .qrom_oracle import controlled_x


def comparator_gate(bits: int, threshold: int):
    if not isinstance(threshold, int) or not 0 <= threshold <= 1 << bits:
        raise ValueError('Integer threshold outside cost-register range')
    cost = QuantumRegister(bits, 'cost')
    flag = QuantumRegister(1, 'flag')
    qc = QuantumCircuit(cost, flag, name='less_than')
    if threshold == 1 << bits:
        qc.x(flag[0])
    else:
        for j in range(bits - 1, -1, -1):
            if not (threshold >> j) & 1:
                continue
            indices = list(range(j, bits))
            zeros = [k for k in indices if k == j or not (threshold >> k) & 1]
            for k in zeros:
                qc.x(cost[k])
            controlled_x(qc, [cost[k] for k in indices], flag[0])
            for k in reversed(zeros):
                qc.x(cost[k])
    return qc.to_gate(label=f'C < {threshold}')
