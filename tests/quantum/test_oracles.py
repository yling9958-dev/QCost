import numpy as np
import pytest
pytest.importorskip('qiskit')
pytest.importorskip('qiskit_aer')
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qmf_quantum.qrom_oracle import qrom_gate, padded_table
from qmf_quantum.reversible_comparator import comparator_gate
from qmf_quantum.phase_oracle import oracle_circuit
from qmf_quantum.cost_quantization import quantize_costs


def encode(qc, bits, start, integer):
    for k in range(bits):
        if (integer >> k) & 1:
            qc.x(start + k)


@pytest.mark.parametrize('size', [4, 5, 8])
def test_qrom_basis_superposition_and_inverse(size):
    values = [(3 * i + 1) % 14 for i in range(size)]
    gate, layout = qrom_gate(values, 4)
    padded, _ = padded_table(values, 4)
    for i in range(1 << layout.address):
        qc = QuantumCircuit(layout.address + 4)
        encode(qc, layout.address, 0, i)
        qc.append(gate, qc.qubits)
        state = Statevector.from_instruction(qc).data
        assert abs(state[i + (padded[i] << layout.address)]) == pytest.approx(1, abs=1e-10)
        qc.append(gate.inverse(), qc.qubits)
        state = Statevector.from_instruction(qc).data
        assert abs(state[i]) == pytest.approx(1, abs=1e-10)
    qc = QuantumCircuit(layout.address + 4)
    qc.h(range(layout.address))
    qc.append(gate, qc.qubits)
    expected = np.zeros(1 << qc.num_qubits, dtype=complex)
    for i, c in enumerate(padded):
        expected[i + (c << layout.address)] = 1 / np.sqrt(1 << layout.address)
    assert np.allclose(Statevector.from_instruction(qc).data, expected, atol=1e-10)


@pytest.mark.parametrize('bits', [2, 3, 4])
def test_comparator_exhaustive(bits):
    for tau in range((1 << bits) + 1):
        gate = comparator_gate(bits, tau)
        for c in range(1 << bits):
            for initial_flag in (0, 1):
                qc = QuantumCircuit(bits + 1)
                encode(qc, bits, 0, c)
                if initial_flag:
                    qc.x(bits)
                qc.append(gate, qc.qubits)
                expected = c + ((initial_flag ^ int(c < tau)) << bits)
                state = Statevector.from_instruction(qc).data
                assert abs(state[expected]) == pytest.approx(1, abs=1e-10)
                qc.append(gate.inverse(), qc.qubits)
                state = Statevector.from_instruction(qc).data
                assert abs(state[c + (initial_flag << bits)]) == pytest.approx(1, abs=1e-10)


@pytest.mark.parametrize('threshold', [0, 1, 6, 14, 15])
def test_phase_relative_sign_and_clean_workspace(threshold):
    values = [0, 3, 10, 7, 13]
    oracle, layout = oracle_circuit(values, 4, threshold)
    table, _ = padded_table(values, 4)
    qc = QuantumCircuit(layout.total)
    qc.h(range(layout.address))
    qc.compose(oracle, inplace=True)
    state = Statevector.from_instruction(qc).data
    expected = np.array([-1 if c < threshold else 1 for c in table]) / np.sqrt(len(table))
    # Same superposition, compare relative phases with an unmarked reference.
    reference = next((i for i, c in enumerate(table) if c >= threshold), 0)
    assert np.allclose(state[:len(table)] / state[reference], expected / expected[reference], atol=1e-9)
    assert np.linalg.norm(state[len(table):]) < 1e-9
    # All-marked / all-unmarked cases separately accept irrelevant global phase.
    assert np.allclose(np.abs(state[:len(table)]), 1 / np.sqrt(len(table)), atol=1e-9)


def test_quantization_monotonic_error_and_ties():
    x = np.array([100, 100.00001, 100.2, 101, 110, 100])
    for bits in [4, 6, 8]:
        codes, info = quantize_costs(x, bits)
        assert info.monotonic_order_preserved
        assert info.max_abs_error <= info.step / 2 + 1e-12
        assert np.all(codes < info.invalid_code)
        assert codes[0] == codes[1] == codes[5] == 0
        assert not info.all_quantized_minima_original_optimal
