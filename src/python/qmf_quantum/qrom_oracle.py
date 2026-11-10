"""Coherent table XOR, synthesized from X and multi-controlled X gates."""
from dataclasses import dataclass
from qiskit import QuantumCircuit, QuantumRegister


@dataclass(frozen=True)
class RegisterLayout:
    address: int
    cost: int
    flag: int = 1
    ancilla: int = 0

    @property
    def total(self):
        return self.address + self.cost + self.flag + self.ancilla

    def as_dict(self):
        return {'address_qubits': self.address, 'cost_qubits': self.cost,
                'flag_qubits': self.flag, 'ancilla_qubits': self.ancilla,
                'total_circuit_qubits': self.total,
                'fault_tolerant_physical_qubits': 'NOT_ESTIMATED',
                'register_order_little_endian': ['address', 'cost', 'flag']}


def padded_table(costs, bits: int):
    values = [int(x) for x in costs]
    if len(values) < 2 or len(values) > 64:
        raise ValueError('Prototype safety cap: 2 <= N <= 64; no full H3 QROM synthesis')
    sentinel = (1 << bits) - 1
    if not 2 <= bits <= 16 or any(v != x or not 0 <= v < sentinel for v, x in zip(values, costs)):
        raise ValueError('Use exact nonnegative integer costs below the reserved sentinel')
    address_bits = (len(values) - 1).bit_length()
    return values + [sentinel] * ((1 << address_bits) - len(values)), RegisterLayout(address_bits, bits)


def controlled_x(qc, controls, target):
    if not controls:
        qc.x(target)
    elif len(controls) == 1:
        qc.cx(controls[0], target)
    else:
        qc.mcx(controls, target)


def qrom_gate(costs, bits: int):
    table, layout = padded_table(costs, bits)
    address = QuantumRegister(layout.address, 'addr')
    value = QuantumRegister(bits, 'cost')
    qc = QuantumCircuit(address, value, name='U_C')
    for i, c in enumerate(table):
        if c == 0:
            continue
        zero_controls = [address[k] for k in range(layout.address) if not (i >> k) & 1]
        for q in zero_controls:
            qc.x(q)
        for k in range(bits):
            if (c >> k) & 1:
                controlled_x(qc, list(address), value[k])
        for q in reversed(zero_controls):
            qc.x(q)
    return qc.to_gate(label='U_C'), layout


def qrom_logical_controls(costs, bits):
    table, _ = padded_table(costs, bits)
    return sum(c.bit_count() for c in table)
