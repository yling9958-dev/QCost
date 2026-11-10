"""Reflection about the full padded uniform address space, up to global -1."""
from qiskit import QuantumCircuit
from .qrom_oracle import controlled_x
from .phase_oracle import oracle_circuit


def diffusion_gate(address_bits: int):
    qc = QuantumCircuit(address_bits, name='D')
    qc.h(qc.qubits)
    qc.x(qc.qubits)
    if address_bits == 1:
        qc.z(0)
    else:
        qc.h(address_bits - 1)
        controlled_x(qc, list(qc.qubits[:-1]), qc.qubits[-1])
        qc.h(address_bits - 1)
    qc.x(qc.qubits)
    qc.h(qc.qubits)
    return qc.to_gate(label='D')


def build_grover_circuit(costs, bits: int, threshold: int, iterations: int, measure=True):
    if not isinstance(iterations, int) or iterations < 0:
        raise ValueError('Nonnegative integer Grover iteration count required')
    oracle, layout = oracle_circuit(costs, bits, threshold)
    qc = QuantumCircuit(*oracle.qregs, name=f'Grover_j{iterations}_tau{threshold}')
    address = qc.qregs[0]
    qc.h(address)
    diffuse = diffusion_gate(layout.address)
    phase = oracle.to_gate(label=f'O_{threshold}')
    for _ in range(iterations):
        qc.append(phase, qc.qubits)
        qc.append(diffuse, address)
    if measure:
        from qiskit import ClassicalRegister
        readout = ClassicalRegister(layout.address, 'readout')
        qc.add_register(readout)
        qc.measure(address, readout)
    return qc, layout
