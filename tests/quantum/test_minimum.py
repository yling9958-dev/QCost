import numpy as np
import pytest
pytest.importorskip('qiskit')
pytest.importorskip('qiskit_aer')
from qmf_quantum.quantum_minimum_finding import gate_level_qmf
from qmf_quantum.cost_quantization import quantize_costs


def test_small_minimum_and_separate_accounting():
    x = np.array([3., 1., 0., 2.])
    codes, _ = quantize_costs(x, 4)
    for seed in range(5):
        result = gate_level_qmf(x, codes, 4, budget=40, seed=seed)
        assert result['selected_index'] == 2
        a = result['accounting']
        assert a['budget_charged_units'] <= 40
        assert a['logical_oracle_queries'] == a['grover_iterations']
        assert a['qrom_invocations'] == 2 * a['grover_iterations']
        assert a['shots'] == a['quantum_circuit_executions'] == len(result['history'])
        assert a['classical_verification_queries'] == 1 + len(result['history'])
        trace = [r['cost_after'] for r in result['history']]
        assert all(left >= right for left, right in zip(trace, trace[1:]))


def test_padded_invalid_addresses_never_replace_incumbent():
    x = np.array([3., 0., 2.])
    codes, _ = quantize_costs(x, 4)
    result = gate_level_qmf(x, codes, 4, budget=40, seed=5)
    assert result['selected_index'] < 3
    assert result['selected_cost'] == x[result['selected_index']]
    for trial in result['history']:
        if not trial['valid_address']:
            assert trial['incumbent_before'] == trial['incumbent_after']


def test_budget_one_has_no_quantum_executions():
    x = np.array([4., 2., 0., 1.])
    codes, _ = quantize_costs(x, 4)
    result = gate_level_qmf(x, codes, 4, budget=1, seed=8)
    assert result['accounting']['shots'] == 0
    assert result['history'] == []
