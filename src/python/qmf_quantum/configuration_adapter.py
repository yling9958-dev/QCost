"""Plain-data address to actual configuration/root mapping, no original imports."""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np


@dataclass(frozen=True)
class ConfigurationRecord:
    configuration_id: int
    root_action: dict
    original_cost: float
    action_keys: tuple[str, ...]
    prior_probability: float


@dataclass
class ConfigurationTable:
    records: tuple[ConfigurationRecord, ...]
    provenance: dict
    full_root_optima: dict
    full_optimal_cost: float

    @property
    def costs(self):
        return np.array([r.original_cost for r in self.records], dtype=np.float64)

    def reconstruct(self, address: int):
        if not 0 <= address < len(self.records):
            raise ValueError('Invalid padded address has no configuration/root action')
        return self.records[address]

    def subset(self, size: int, seed: int):
        if not 2 <= size <= len(self.records):
            raise ValueError('Invalid subset size')
        # Cost-independent sampling. Sorting preserves original enumeration order.
        selected = np.sort(np.random.default_rng(seed).choice(len(self.records), size=size, replace=False))
        meta = {**self.provenance, 'subset_size': size, 'subset_seed': seed,
                'selection_rule': 'uniform without replacement, independent of costs; ascending full ID',
                'selected_configuration_ids': [int(x) for x in selected],
                'not_full_H3_search': True}
        return ConfigurationTable(tuple(self.records[int(i)] for i in selected), meta,
                                  self.full_root_optima, self.full_optimal_cost)

    def metrics(self, selected: int):
        r = self.reconstruct(selected)
        x = self.costs
        minimum, maximum = float(x.min()), float(x.max())
        tol = 8 * float(np.spacing(max(abs(minimum), 1.0)))
        local_opt_roots = {v.root_action['key'] for v in self.records
                           if abs(v.original_cost - minimum) <= tol}
        global_tol = 8 * float(np.spacing(max(abs(self.full_optimal_cost), 1.0)))
        root_min = float(self.full_root_optima[r.root_action['key']])
        return {'configuration_id': r.configuration_id, 'root_action': r.root_action,
                'selected_cost': r.original_cost, 'subset_optimal_cost': minimum,
                'normalized_gap': (r.original_cost - minimum) / max(maximum - minimum, 1e-12),
                'optimal_configuration_hit': bool(abs(r.original_cost - minimum) <= tol),
                'subset_optimal_root_hit': r.root_action['key'] in local_opt_roots,
                'full_H3_optimal_root_hit': bool(abs(root_min - self.full_optimal_cost) <= global_tol),
                'root_regret': max(0.0, root_min - self.full_optimal_cost),
                'root_regret_definition': 'min full H3 cost conditioned on selected root minus full H3 optimum'}


def load_table(path: Path):
    doc = json.loads(Path(path).read_text())
    records = tuple(ConfigurationRecord(int(r['configuration_id']), r['root_action'],
                                        float(r['original_cost']), tuple(r['action_keys']),
                                        float(r['prior_probability'])) for r in doc['records'])
    return ConfigurationTable(records, doc['provenance'], doc['full_root_optima'], doc['full_optimal_cost'])
