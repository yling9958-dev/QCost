"""Build an isolated QMF diagnostic artifact and emit deterministic tree evidence."""
import csv
import hashlib
import os
from pathlib import Path
import struct
import sys

import numpy as np
import yaml

from qmapli.indexes.qmap_nai.index import PrefixHybridIndex
from qmapli.wg_qmf.build_static_qw_index import main


output = Path(sys.argv[1])
point_path = Path(sys.argv[2])
point_count = int(sys.argv[3])
query_path = Path(sys.argv[4])
output.mkdir(parents=True, exist_ok=True)
captured = {}
original = PrefixHybridIndex.build


def audited(self, *args, **kwargs):
    result = original(self, *args, **kwargs)
    parents = {child.node_id: node.node_id for node in self.nodes for child in node.children}
    rows = []
    for node in sorted(self.nodes, key=lambda value: value.node_id):
        rows.append({
            "node_id": node.node_id,
            "parent_id": parents.get(node.node_id, -1),
            "axis": node.split_action.axis if node.children else -1,
            "threshold": float(node.threshold).hex() if node.children else "",
            "left_child": node.children[0].node_id if node.children else -1,
            "right_child": node.children[1].node_id if node.children else -1,
            "is_leaf": int(not node.children),
            "point_start": node.storage_start,
            "point_end": node.storage_end,
            "bbox": "|".join(float(item).hex() for item in node.mbr),
        })
    captured["rows"] = rows
    membership = getattr(self, "leaf_membership_sha256", None)
    if membership is None:
        digest = hashlib.sha256()
        for node in self.leaves:
            values = np.ascontiguousarray(node.point_indices, dtype=np.dtype("<i8"))
            digest.update(struct.pack("<QQ", int(node.node_id), len(values)))
            digest.update(memoryview(values).cast("B"))
        membership = digest.hexdigest()
    captured["membership"] = membership
    return result


PrefixHybridIndex.build = audited
root = Path(os.environ["REPRO_ROOT"])
config = yaml.safe_load((root / "config/qmf_frozen_config.yaml").read_text())
main([
    "--mode", "uniform_qmf",
    "--r4-checkpoint", str(root / "config/r4.pt"),
    "--points", str(point_path),
    "--point-count", str(point_count),
    "--train-queries", str(query_path),
    "--index", str(output / "qmap_uniform_qmf.idx"),
    "--metadata", str(output / "metadata.json"),
    "--context-seed", "20260902",
    "--beta-leaf", str(config["beta_leaf"]),
    "--beta-point", str(config["beta_point"]),
    "--max-depth", str(config["max_depth"]),
    "--min-leaf-size", str(config["min_leaf_size"]),
    "--max-leaves", str(config["max_leaves"]),
    "--budget-factor", str(config["budget_sqrt_factor"]),
    "--memory-stage-trace", str(output / "QMF_MEMORY_STAGE_TRACE.csv"),
])
with (output / "tree_decision_manifest.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(captured["rows"][0]),
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(captured["rows"])
(output / "leaf_membership.sha256").write_text(captured["membership"] + "\n")
