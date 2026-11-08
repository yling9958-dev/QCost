# Gate-level QMF: Small-scale proof of concept

Files:
- `qmf_quantum_circuit_prototype.py`: Qiskit/Aer demonstration of gate-executed quantum minimum-finding-style threshold search.
- `test_qmf_quantum_circuit_prototype.py`: exhaustive phase-oracle correctness and measurement tests.

## Isolated installation (on the user's machine)

```bash
python3 -m venv .venv-qmf-circuit
source .venv-qmf-circuit/bin/activate
python -m pip install --upgrade pip
python -m pip install 'qiskit>=2,<3' 'qiskit-aer>=0.17,<1' pytest matplotlib
python -m pytest -q test_qmf_quantum_circuit_prototype.py
python qmf_quantum_circuit_prototype.py --shots 2048 --output ./qmf_circuit_output
```

Artifacts: `qmf_circuit_output/circuit.txt`, `circuit.png` (requires optional plotting packages), `report.json`.

The demonstration uses three **index** qubits, three **cost** qubits, and one **flag** qubit, plus three classical measurement bits. All operations (controlled cost loading, reversible less-than comparison, phase flip, inverse operations, diffuser, measurement) are synthesized as **quantum gates** and simulated by Qiskit Aer; **it does not** sample from an analytical Grover success formula.

## Accuracy limits and scientific claims

- The QROM loader embeds a *precomputed classical cost table* as a gate-level circuit. A reversible quantum circuit does not by itself establish a quantum algorithmic speedup.
- The H=3 complete candidate universe can have up to 16,384 members. A naïve QROM for this universe entails many controlled gates and repeated synthesis; this prototype intentionally limits its scale.
- Actual spatial, workload, R4 neural scorer, and conditional subtree cost are still classical. Avoid claims that they are natively or coherently computed on quantum registers.
- Finite-budget minimum finding is probabilistic; check measured candidate cost classically before threshold updates, and compare to exact recursive H3 and classical argmin.
- Before publishing claims, record gate counts, transpiled circuit depth, qubit counts, total circuit runs/shots, probability estimates, errors due to cost quantization, and full oracle-synthesis costs.

## Integrating into QMF-Index

Keep the production CPU analytical search intact. Add a separately selectable `qiskit_circuit` backend for **small local configurations**, using small subsets of original cost tables with stable index-to-subtree mappings. For inputs exceeding the qubit/gate budget, report a controlled unsupported status or explicit classical fallback; never silently label a classical run as quantum.

Reversible lookup can be upgraded to on-demand cost computation only after a real circuit-level cost construction is designed and tested. The independently verified conditional additive cost and efficient recursive exact H3 baseline must remain in the comparison.
