"""Only incumbent bookkeeping and measurement verification are classical here."""
from dataclasses import dataclass
import math


@dataclass
class QueryAccounting:
    logical_oracle_queries: int = 0
    grover_iterations: int = 0
    quantum_circuit_executions: int = 0
    shots: int = 0
    classical_verification_queries: int = 1
    invalid_address_measurements: int = 0
    budget_charged_units: int = 1

    @property
    def qrom_invocations(self):
        return 2 * self.logical_oracle_queries


def maximum_iterations(m: float, remaining: int):
    return min(max(math.ceil(m) - 1, 0), max(remaining - 1, 0))
