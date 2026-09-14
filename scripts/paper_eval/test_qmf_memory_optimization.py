"""Algorithm-equivalence gates for QMF memory ownership changes."""
import ast
import csv
import hashlib
import json
import struct
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import support as s
import orchestrate

sys.path.insert(0, str(s.BASE/'src/common/python'))
from qmapli.indexes.qmap_nai.index import PrefixHybridIndex
from qmapli.wg_qmf.index import QWBuildConfig, build_qw_static_index
from qmapli.wg_qmf.point_io import read_points
from qmapli.wg_qmf.cached_features import _density_histogram


EXPECTED_TREE_SHA = "95fafaa6d63e4d4c9b7b731f9c2c89fb0fd2b6fb78300a1982353925589f6ac6"
EXPECTED_MEMBERSHIP_SHA = "8c38b797942245e460290c06241edc49239ef90ff1abb81a0525bf3c1cd4f182"
EXPECTED_INDEX_SHA = "7d0a7de9d6e4780995c46b2e515aca105e7e5f8a22a57ff5ff96ff145c4cf6b2"
def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def qmf_fixture(tmp_path_factory):
    destination = tmp_path_factory.mktemp("qmf-memory")/"fixture.idx"
    rng = np.random.Generator(np.random.PCG64(20260913))
    points = rng.random((1024, 2), dtype=np.float64)
    points[100:110] = points[99]
    ids = np.arange(len(points), dtype=np.int64) * 3 + 7
    lower = rng.random((32, 2)) * 0.8
    queries = np.column_stack((lower, np.minimum(lower + 0.2, 1.0)))
    captured = {}
    class Trace:
        def __init__(self): self.events=[]
        def emit(self, phase, **details): self.events.append((phase,details))
    trace=Trace()
    original = PrefixHybridIndex.build

    def audited(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        parents = {child.node_id: node.node_id for node in self.nodes for child in node.children}
        rows = []
        for node in sorted(self.nodes, key=lambda value: value.node_id):
            rows.append({
                "node_id": node.node_id,
                "parent_id": parents.get(node.node_id, -1),
                "depth": node.depth,
                "axis": node.split_action.axis if node.children else -1,
                "threshold": float(node.threshold).hex() if node.children else "",
                "left": node.children[0].node_id if node.children else -1,
                "right": node.children[1].node_id if node.children else -1,
                "start": node.storage_start,
                "end": node.storage_end,
                "bbox": [float(value).hex() for value in node.mbr],
            })
        captured["tree"] = rows
        captured["index"] = self
        return result

    PrefixHybridIndex.build = audited
    try:
        metadata = build_qw_static_index(
            mode="uniform_qmf", r4_checkpoint=s.BASE/'config/r4.pt',
            points=points, ids=ids, train_queries=queries,
            output_path=destination, context_seed=1729,
            beta_leaf=1.2779084295340111e-09, beta_point=3.428255707467659,
            build_config=QWBuildConfig(
                max_depth=3, min_leaf_size=32, max_leaves=4,
                minimum_lookahead_points=64, lookahead_depth=3,
                top_k=4, budget_sqrt_factor=2.0,
                suffix_strategy="dual_axis_intersection"),
            trace=trace,
        )
    finally:
        PrefixHybridIndex.build = original
    tree_sha = hashlib.sha256(json.dumps(captured["tree"], sort_keys=True).encode()).hexdigest()
    return {"path": destination, "points": points, "ids": ids, "queries": queries,
            "tree_sha": tree_sha, "index": captured["index"], "metadata": metadata,
            "trace":trace.events}


def test_qmf_point_io_memory_equivalence(tmp_path):
    source = tmp_path/"points.csv"
    source.write_text(
        "x,y,id\n0.1,-0.0,7\n1.0000000000000002,1e-300,8\n"
        "-1.7976931348623157e308,1.7976931348623157e308,2147483649\n"
        "0.33333333333333331,-2.2250738585072014e-308,9\n")
    frame = pd.read_csv(source, usecols=["x", "y", "id"],
                        dtype={"x": np.float64, "y": np.float64, "id": np.int64},
                        float_precision="round_trip")
    expected_points = np.ascontiguousarray(frame[["x", "y"]].to_numpy())
    expected_ids = np.ascontiguousarray(frame["id"].to_numpy())
    for chunk_size in (1, 2, 3, 10):
        points, ids = read_points(source, expected_count=4, chunk_size=chunk_size)
        assert points.flags.c_contiguous and ids.flags.c_contiguous
        assert np.array_equal(points.view(np.uint64), expected_points.view(np.uint64))
        assert np.array_equal(ids, expected_ids)
    with pytest.raises(ValueError, match="more rows"):
        read_points(source, expected_count=3, chunk_size=2)
    with pytest.raises(ValueError, match="row count differs"):
        read_points(source, expected_count=5, chunk_size=2)


def test_qmf_feature_histogram_bitwise_equivalence():
    rng = np.random.Generator(np.random.PCG64(5519))
    points = rng.random((10003, 2), dtype=np.float64)
    points[:5] = [[0., 0.], [1., 1.], [.25, .5], [.5, .75], [.75, .25]]
    lower = points.min(axis=0)
    spans = np.maximum(points.max(axis=0) - lower, 1e-12)
    normalized = np.clip((points-lower)/spans, 0., 1.)
    expected, _, _ = np.histogram2d(
        normalized[:, 0], normalized[:, 1], bins=4, range=((0., 1.), (0., 1.)))
    for chunk_size in (1, 7, 1000, len(points) + 1):
        observed = _density_histogram(points, lower, spans, chunk_size)
        assert np.array_equal(observed.view(np.uint64), expected.view(np.uint64))


def test_qmf_tree_digest_unchanged(qmf_fixture):
    assert qmf_fixture["tree_sha"] == EXPECTED_TREE_SHA
    assert qmf_fixture["metadata"]["leaf_membership_sha256"] == EXPECTED_MEMBERSHIP_SHA


def test_qmf_split_decisions_unchanged(qmf_fixture):
    metadata = qmf_fixture["metadata"]
    assert metadata["selected_actions"] == {"x_q0.375": 1, "y_q0.375": 1, "y_q0.5": 1}
    assert metadata["configuration_count"] == 29376
    assert metadata["threshold_oracle_calls"] == 358
    assert metadata["verification_cost_calls"] == 203


def test_qmf_query_exactness(qmf_fixture, tmp_path):
    # The optimized materializer is byte-identical to the baseline static index;
    # exercise that artifact through the unchanged native query runtime as well.
    assert file_sha(qmf_fixture["path"]) == EXPECTED_INDEX_SHA
    binary = s.RUN/'common/build/bin/qmap_static_query'
    assert binary.is_file()
    query_path = tmp_path/'queries.csv'
    output = tmp_path/'results.csv'
    with query_path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['query_id','split','selectivity_group','xmin','ymin','xmax','ymax'])
        for ordinal, query in enumerate(qmf_fixture["queries"][:8]):
            writer.writerow([ordinal,'correctness','C',*query])
    subprocess.run([str(binary),'--method','qmap_uniform_qmf','--index',str(qmf_fixture["path"]),
                    '--queries',str(query_path),'--output',str(output)], check=True)
    stored = qmf_fixture["points"].astype(np.float32).astype(np.float64)
    expected = {}
    for ordinal, query in enumerate(qmf_fixture["queries"][:8]):
        mask = ((stored[:,0] >= query[0]) & (stored[:,0] <= query[2]) &
                (stored[:,1] >= query[1]) & (stored[:,1] <= query[3]))
        expected[str(ordinal)] = set(map(str, qmf_fixture["ids"][mask]))
    with output.open() as handle:
        for row in csv.DictReader(handle):
            observed = set(filter(None, row['result_ids'].split(';')))
            assert observed == expected[row['query_id']]


def test_qmf_no_algorithm_parameter_change():
    config = QWBuildConfig()
    assert config.lookahead_depth == 3
    assert config.top_k == 4
    assert config.budget_sqrt_factor == 2.0
    assert config.max_depth == 8 and config.min_leaf_size == 256 and config.max_leaves == 128


def test_qmf_h3_unchanged():
    assert QWBuildConfig().lookahead_depth == 3


def test_qmf_topk_unchanged():
    assert QWBuildConfig().top_k == 4


def test_qmf_search_budget_unchanged():
    assert QWBuildConfig().budget_sqrt_factor == 2.0


def test_qmf_cost_function_unchanged():
    # Full hashes are checked below using the original production source receipt.
    frozen = s.read_json(s.OUT/'00_environment/production_source_before.json')
    for relative in ("wg_qmf/search.py", "wg_qmf/cost_oracle.py", "wg_qmf/cached_oracle.py",
                     "wg_qmf/quantum.py", "workload_action_interaction/actions.py"):
        path = s.BASE/'src/common/python/qmapli'/relative
        assert file_sha(path) == frozen['src/common/python/qmapli/'+relative]


def test_qmf_core_algorithm_sources_unchanged():
    frozen = s.read_json(s.OUT/'00_environment/production_source_before.json')
    exact = (
        'wg_qmf/search.py', 'wg_qmf/cost_oracle.py', 'wg_qmf/cached_oracle.py',
        'wg_qmf/quantum.py', 'wg_qmf/prior.py',
        'workload_action_interaction/actions.py',
    )
    for relative in exact:
        assert file_sha(s.BASE/'src/common/python/qmapli'/relative) == \
            frozen['src/common/python/qmapli/'+relative]
    assert file_sha(s.BASE/'config/qmf_frozen_config.yaml') == \
        frozen['config/qmf_frozen_config.yaml']
    assert file_sha(s.BASE/'config/r4.pt') == frozen['config/r4.pt']


def test_qmf_enumerator_changed_only_by_lifetime_deletes():
    class RemoveDeletes(ast.NodeTransformer):
        def visit_Delete(self, node):
            return None
    path = s.BASE/'src/common/python/qmapli/wg_qmf/configuration.py'
    tree = ast.parse(path.read_text())
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == '_enumerate')
    function = RemoveDeletes().visit(function)
    ast.fix_missing_locations(function)
    digest = hashlib.sha256(ast.dump(function, include_attributes=False).encode()).hexdigest()
    assert digest == "781b829ef6cf1747fc7d4e02e0fdc032cfa10aca8b5be30d745dded2bdfcc9f8"


def test_qmf_online_quantum_disabled(qmf_fixture):
    assert qmf_fixture["metadata"]["online_quantum_search"] is False
    assert qmf_fixture["metadata"]["online_python_controller"] is False


def test_qmf_static_export_releases_training_memberships(qmf_fixture):
    index = qmf_fixture["index"]
    assert all(node.point_indices.size == 0 for node in index.nodes)
    assert index.storage_original_positions is None
    assert index.original_points is None and index.original_ids is None
    assert all(leaf.suffix.x_order is None and leaf.suffix.y_order is None for leaf in index.leaves)
    assert all(leaf.suffix.x_sorted_values is None and leaf.suffix.y_sorted_values is None
               for leaf in index.leaves)


def test_qmf_root_uses_canonical_view_and_reuses_identity_indices(qmf_fixture):
    initialized=[details for phase,details in qmf_fixture['trace']
                 if phase=='root_initialization']
    assert len(initialized)==1 and initialized[0]['root_indices_bytes']==0
    milestones=[details for phase,details in qmf_fixture['trace']
                if phase=='recursive_build_milestone']
    assert milestones[0]['node_id']==0 and milestones[0]['local_is_view'] is True
    split=[details for phase,details in qmf_fixture['trace']
           if phase=='after_split_decision' and details['node_id']==0]
    assert len(split)==1 and split[0]['identity_root_reuse'] is True


def test_qmf_unsplit_root_restores_identity_membership(tmp_path):
    rng=np.random.Generator(np.random.PCG64(27))
    points=rng.random((64,2),dtype=np.float64)
    ids=np.arange(len(points),dtype=np.int64)
    queries=np.asarray([[0.,0.,1.,1.]],dtype=np.float64)
    output=tmp_path/'single-leaf.idx'
    metadata=build_qw_static_index(
        mode='uniform_qmf',r4_checkpoint=s.BASE/'config/r4.pt',
        points=points,ids=ids,train_queries=queries,output_path=output,
        context_seed=1729,beta_leaf=1.2779084295340111e-09,
        beta_point=3.428255707467659,
        build_config=QWBuildConfig(max_depth=0,min_leaf_size=32,max_leaves=1),
    )
    assert metadata['point_count']==len(points)
    assert output.is_file() and output.stat().st_size>0


def test_qmf_memory_trace_covers_formal_build_stages(qmf_fixture):
    phases={phase for phase,_ in qmf_fixture['trace']}
    assert {'root_initialization','before_h3_candidate_generation',
            'after_h3_candidate_generation','during_candidate_evaluation',
            'after_candidate_evaluation','after_split_decision','before_layout',
            'layout_permutation_ready','layout_reordered_storage_ready',
            'layout_suffix_milestone','before_serialization','after_serialization'} <= phases


def test_pass_results_unchanged():
    manifest = s.read_json(s.OUT/'debug/preserved_five_pass_methods.json')
    assert len(manifest) == 111
    for entry in manifest:
        path = Path(entry['path'])
        assert path.stat().st_size == entry['bytes']
        assert file_sha(path) == entry['sha256']


def test_audited_archive_allows_only_registered_memory_delta():
    assert orchestrate.verify_baseline_archive() == "AUDITED_MEMORY_IMPLEMENTATION"
