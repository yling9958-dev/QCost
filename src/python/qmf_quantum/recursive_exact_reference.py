"""Exact DP on a supplied conditional candidate family, diagnostic only.

The family was exported from an already-materialized original H3 universe.
This implementation does not score R4 or generate/filter data splits. Export
cost is O(N H) and must not be hidden in claims about DP end-to-end efficiency.
The original Recursive Exact H3 implementation is neither imported nor changed.
"""
from dataclasses import dataclass


@dataclass
class Solution:
    hits: int
    scans: int
    cost: float
    action_keys: tuple
    feasible_configurations: int


def solve_conditional_problem(problem):
    q = int(problem['query_count'])
    bl = float(problem['beta_leaf'])
    bp = float(problem['beta_point'])
    states = problem['states']
    counters = {'internal_states': 0, 'leaf_evaluations': 0,
                'complete_configurations_materialized': 0}

    def cost(hits, scans):
        return bl * (float(hits) / q) + bp * (float(scans) / q)

    def solve(key):
        state = states[key]
        if state['leaf']:
            counters['leaf_evaluations'] += 1
            h, s = int(state['hits']), int(state['scans'])
            return Solution(h, s, cost(h, s), (), 1)
        counters['internal_states'] += 1
        best = None
        feasible = 0
        for option in state['options']:
            left, right = solve(option['left']), solve(option['right'])
            h, s = left.hits + right.hits, left.scans + right.scans
            value = cost(h, s)
            feasible += left.feasible_configurations * right.feasible_configurations
            if best is None or value < best.cost:
                best = Solution(h, s, value,
                                (option['action']['key'],) + left.action_keys + right.action_keys, 0)
        if best is None:
            raise ValueError('Exported conditional state has no feasible full-depth option')
        best.feasible_configurations = feasible
        return best

    solution = solve(problem['root'])
    return solution, counters
