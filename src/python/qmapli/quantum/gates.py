"""Differentiable unitary gates for the custom PyTorch statevector backend."""

from __future__ import annotations

import torch


def ry_gate(angle: torch.Tensor | float) -> torch.Tensor:
    angle = torch.as_tensor(angle)
    half = angle / 2.0
    cosine = torch.cos(half).to(torch.complex64)
    sine = torch.sin(half).to(torch.complex64)
    return torch.stack(
        (
            torch.stack((cosine, -sine), dim=-1),
            torch.stack((sine, cosine), dim=-1),
        ),
        dim=-2,
    )


def rz_gate(angle: torch.Tensor | float) -> torch.Tensor:
    angle = torch.as_tensor(angle)
    half = angle.to(torch.float32) / 2.0
    zero = torch.zeros_like(half)
    negative = torch.exp(torch.complex(zero, -half))
    positive = torch.exp(torch.complex(zero, half))
    zeros = torch.zeros_like(negative)
    return torch.stack(
        (
            torch.stack((negative, zeros), dim=-1),
            torch.stack((zeros, positive), dim=-1),
        ),
        dim=-2,
    )


def _apply_single_qubit_gate(
    state: torch.Tensor, gate: torch.Tensor, qubit: int, num_qubits: int
) -> torch.Tensor:
    if not 0 <= qubit < num_qubits:
        raise ValueError(f"invalid qubit {qubit} for {num_qubits} qubits")
    batch = state.shape[0]
    tensor = state.reshape(batch, *([2] * num_qubits))
    axis = qubit + 1
    permutation = [0, axis] + [
        index for index in range(1, num_qubits + 1) if index != axis
    ]
    moved = tensor.permute(permutation).reshape(batch, 2, -1)
    if gate.ndim == 2:
        updated = torch.einsum("ij,bjk->bik", gate, moved)
    else:
        updated = torch.einsum("bij,bjk->bik", gate, moved)
    inverse = [0] * len(permutation)
    for new_axis, old_axis in enumerate(permutation):
        inverse[old_axis] = new_axis
    restored = updated.reshape(
        batch, 2, *([2] * (num_qubits - 1))
    ).permute(inverse)
    return restored.reshape(batch, 1 << num_qubits)


def _apply_two_qubit_gate(state, gate, first, second, num_qubits):
    if first == second:
        raise ValueError("two-qubit gate requires distinct qubits")
    batch = state.shape[0]
    tensor = state.reshape(batch, *([2] * num_qubits))
    axes = [first + 1, second + 1]
    permutation = [0] + axes + [
        axis for axis in range(1, num_qubits + 1) if axis not in axes
    ]
    moved = tensor.permute(permutation).reshape(batch, 4, -1)
    if gate.ndim == 2:
        updated = torch.einsum("ij,bjk->bik", gate, moved)
    else:
        updated = torch.einsum("bij,bjk->bik", gate, moved)
    inverse = [0] * len(permutation)
    for new_axis, old_axis in enumerate(permutation):
        inverse[old_axis] = new_axis
    shape = [batch, 2, 2] + [2] * (num_qubits - 2)
    return updated.reshape(shape).permute(inverse).reshape(batch, 1 << num_qubits)


def two_qubit_gate(kind: str, angle=None, device=None):
    kind = str(kind).lower()
    if kind == "cnot":
        return torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
            dtype=torch.complex64,
            device=device,
        )
    if kind == "cz":
        return torch.diag(
            torch.tensor([1, 1, 1, -1], dtype=torch.complex64, device=device)
        )
    if kind == "cry":
        rotation = ry_gate(angle).to(device)
        gate = torch.eye(4, dtype=torch.complex64, device=device)
        gate[2:, 2:] = rotation
        return gate
    raise ValueError(f"unsupported two-qubit gate: {kind}")
