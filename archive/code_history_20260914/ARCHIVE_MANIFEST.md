# Paper Controller Code Archive

| Old path | Archived path | Reason | Source commit |
|---|---|---|---|
| `scripts/paper_eval/finish_repair.py` | `archive/code_history_20260914/scripts/paper_eval/finish_repair.py` | One-time automatic GeoLife-to-Gowalla handoff. It was not imported or invoked by the current runner, had no loaded systemd unit, and conflicts with the converged explicit `--resume` workflow. | `4cb969689f3e175d338256542ba975cfc3995a4a` |

The archived module is provenance only. It is not on the formal execution path
and must not be imported by `scripts/paper_eval`.
