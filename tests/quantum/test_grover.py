import math
import numpy as np
import pytest
pytest.importorskip('qiskit')
pytest.importorskip('qiskit_aer')
from qiskit.quantum_info import Statevector
from qmf_quantum.grover_diffusion import build_grover_circuit, diffusion_gate
from qmf_quantum.quantum_backend import GateBackend


@pytest.mark.parametrize('values', [[3, 1, 0, 2], [3, 0, 2]])
@pytest.mark.parametrize('iterations', [0, 1, 2])
def test_grover_statevector_and_measured_probability(values, iterations):
    qc, layout = build_grover_circuit(values, 4, 1, iterations, measure=False)
    state = Statevector.from_instruction(qc).data
    padded_n = 1 << layout.address
    theta = math.asin(math.sqrt(1 / padded_n))
    theory = math.sin((2 * iterations + 1) * theta) ** 2
    optimal = values.index(0)
    actual = float(abs(state[optimal]) ** 2)
    assert actual == pytest.approx(theory, abs=1e-9)
    assert np.linalg.norm(state[padded_n:]) < 1e-9
    run = GateBackend(values, 4).execute(1, iterations, shots=2048, seed=20261009)
    probability = sum(v for k, v in run.counts.items() if int(k, 2) == optimal) / 2048
    assert abs(probability - theory) < max(0.035, 6 * math.sqrt(theory * (1 - theory) / 2048))
    assert run.resources['residual_multi_qubit_gates'] == 0


def test_diffusion_reflection_up_to_global_phase():
    from qiskit.quantum_info import Operator
    u = Operator(diffusion_gate(2)).data
    uniform = np.ones(4) / 2
    expected = 2 * np.outer(uniform, uniform) - np.eye(4)
    assert np.allclose(u, -expected, atol=1e-9)
