import numpy as np
import pytest

from hybrid_qmf import optimize
from hybrid_qmf.qmf_frontier_operator import visible_distribution
from qmapli.workload_action_interaction.actions import enumerate_actions, split_positions


class ConstantScorer:
    def score_actions(self, points, queries, actions):
        return np.zeros(len(actions))


@pytest.fixture
def context():
    rng = np.random.default_rng(20260910)
    points = rng.uniform(size=(1024, 2))
    queries = np.array([
        [0, 0, 1, 1], [0, 0, 0.5, 0.5], [0.3, 0.2, 0.7, 0.9],
        [0.8, 0.1, 1, 0.4], [0.2, 0.6, 0.6, 1],
    ])
    return points, queries


def test_full_optimizer_matches_independently_computed_one_level_cost(context):
    points, queries = context
    actions = sorted(
        (a for a in enumerate_actions(points, 0.05)
         if a.valid and min(a.left_count, a.right_count) >= 256),
        key=lambda a: a.key,
    )[:4]

    def leaf_cost(part):
        lo, hi = part.min(axis=0), part.max(axis=0)
        hits = np.count_nonzero(
            (queries[:, 2] >= lo[0]) & (queries[:, 0] <= hi[0])
            & (queries[:, 3] >= lo[1]) & (queries[:, 1] <= hi[1])
        )
        return (1.2779084295340111e-09 * hits
                + 3.428255707467659 * hits * len(part)) / len(queries)

    costs = []
    for action in actions:
        left, right = split_positions(points, action)
        costs.append(leaf_cost(points[left]) + leaf_cost(points[right]))
    result = optimize(points, queries, ConstantScorer(), h=1, seed=7)
    assert result["stats"]["proven_optimal"] is True
    assert result["stats"]["selected_cost"] == pytest.approx(min(costs))
    assert result["plan"] is not None


def test_attempt_budget_keeps_feasible_initial_plan(context):
    points = np.random.default_rng(20260910).uniform(size=(2048, 2))
    result = optimize(points, context[1], ConstantScorer(), h=2, attempts=0, trace=False)
    assert result["plan"] is not None
    assert result["stats"]["stop_reason"] == "attempt_budget"
    assert result["stats"]["proven_optimal"] is False
    assert result["events"] == []


def test_fixed_seed_preserves_selected_configuration(context):
    points = np.random.default_rng(11).uniform(size=(2048, 2))
    first = optimize(points, context[1], ConstantScorer(), h=2, seed=37)
    second = optimize(points, context[1], ConstantScorer(), h=2, seed=37)
    assert first["stats"]["selected_configuration"] == second["stats"]["selected_configuration"]
    assert first["stats"]["selected_cost"] == second["stats"]["selected_cost"]


def test_comparison_methods_are_not_exported(context):
    with pytest.raises(ValueError, match="Only the full Hybrid-QMF"):
        optimize(*context, ConstantScorer(), method="M4")


def test_empty_context_is_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        optimize(np.empty((0, 2)), np.empty((0, 4)), ConstantScorer())


@pytest.mark.parametrize("values,threshold", [([1, 2, 3, 4], 3), ([1, 1, 1], 1)])
def test_frontier_distribution_is_normalized(values, threshold):
    probabilities, info = visible_distribution(values, threshold)
    assert np.all(probabilities >= 0)
    assert probabilities.sum() == pytest.approx(1)
    assert 0 <= info["amplified_mass"] <= 1
