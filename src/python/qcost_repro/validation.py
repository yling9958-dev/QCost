"""Independent legality and objective checks, called only after optimization."""

import numpy as np
from qmapli.wg_qmf.cost_oracle import evaluate_subtree_costs
from qmapli.workload_action_interaction.actions import enumerate_actions, split_positions

BETA_LEAF = 1.2779084295340111e-09
BETA_POINT = 3.428255707467659


def verify_plan(plan, points, queries):
    if plan is None:
        return False, None
    actions = {item.path: item.action for item in plan.actions}
    leaves = []

    def walk(local, path, depth):
        if depth == 0:
            leaves.append((len(local), tuple(np.r_[local.min(0), local.max(0)])))
            return
        action = actions[path]
        legal = [a for a in enumerate_actions(local, .05)
                 if a.valid and min(a.left_count, a.right_count) >= 256]
        assert any(a == action for a in legal), "Illegal split action"
        left, right = split_positions(local, action)
        walk(local[left], path + (0,), depth - 1)
        walk(local[right], path + (1,), depth - 1)

    walk(points, (), plan.depth)
    assert len(leaves) == len(plan.leaves) == 2 ** plan.depth
    assert all(n == leaf.point_count and np.array_equal(bounds, leaf.bounds)
               for (n, bounds), leaf in zip(leaves, plan.leaves))
    cost = evaluate_subtree_costs([plan], queries, beta_leaf=BETA_LEAF,
                                 beta_point=BETA_POINT).costs[0]
    return True, float(cost)
