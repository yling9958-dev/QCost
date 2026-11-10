"""Run with: pytest -q test_qmf_quantum_circuit_prototype.py
Requires qiskit, qiskit-aer and pytest in the chosen virtualenv.
"""
import math

import pytest
pytest.importorskip('qiskit')
pytest.importorskip('qiskit_aer')

from qiskit import QuantumCircuit, QuantumRegister
from qiskit.quantum_info import Statevector

from qmf_quantum_circuit_prototype import (
    _validate_costs,
    threshold_phase_oracle,
    run_grover_circuit,
    gate_level_qmf,
)


@pytest.mark.parametrize('tau', [0, 1, 2, 4, 7])
def test_oracle_phase_and_clean_ancilla(tau):
    costs=[7, 4, 5, 3, 6, 2, 1, 0]
    for idx in range(8):
        address=QuantumRegister(3,'a')
        value=QuantumRegister(3,'v')
        flag=QuantumRegister(1,'f')
        qc=QuantumCircuit(address,value,flag)
        for bit in range(3):
            if idx>>bit & 1:
                qc.x(address[bit])
        threshold_phase_oracle(qc,address,value,flag[0],costs,tau)
        sv=Statevector.from_instruction(qc)
        expected=-1.0 if costs[idx]<tau else 1.0
        assert abs(sv.data[idx] - expected) < 1e-9
        assert abs(sum(abs(amp)**2 for amp in sv.data)-1) < 1e-9
        assert all(abs(amp) < 1e-9 for j,amp in enumerate(sv.data) if j != idx)


def test_grover_probability_matches_theory():
    costs=[7,4,5,3,6,2,1,0]
    _, _, _, hit_rate=run_grover_circuit(costs,1,2,3,shots=2048,seed=7)
    expected=math.sin(5*math.asin(math.sqrt(1/8)))**2
    assert abs(hit_rate-expected) < 0.08


def test_qmf_end_to_end_real_gates():
    costs=[7,4,5,3,6,2,1,0]
    result=gate_level_qmf(costs,3,seed=1,max_trials=12,max_grover_iterations=12)
    assert 0 <= result['best_index'] < len(costs)
    assert result['best_cost'] == costs[result['best_index']]
    assert result['measurement_attempts'] >= 0
    assert all('qubits' in trial and 'depth' in trial for trial in result['history'])
