"""Compute, phase-mark, uncompare, uncompute; all work registers restored."""
from qiskit import QuantumCircuit, QuantumRegister
from .qrom_oracle import qrom_gate, padded_table
from .reversible_comparator import comparator_gate


def oracle_circuit(costs, bits: int, threshold: int):
    table, layout = padded_table(costs, bits)
    if not isinstance(threshold, int) or not 0 <= threshold <= (1 << bits) - 1:
        raise ValueError('Oracle must never mark reserved invalid addresses')
    addr = QuantumRegister(layout.address, 'addr')
    value = QuantumRegister(bits, 'cost')
    flag = QuantumRegister(1, 'flag')
    qc = QuantumCircuit(addr, value, flag, name=f'O_tau_{threshold}')
    lookup, _ = qrom_gate(costs, bits)
    compare = comparator_gate(bits, threshold)
    qc.append(lookup, list(addr) + list(value))
    qc.append(compare, list(value) + list(flag))
    qc.z(flag[0])
    qc.append(compare.inverse(), list(value) + list(flag))
    qc.append(lookup.inverse(), list(addr) + list(value))
    return qc, layout
