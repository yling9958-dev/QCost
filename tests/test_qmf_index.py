import csv
import ctypes
import hashlib
from pathlib import Path
import subprocess

import numpy as np
import pytest

from qmapli.wg_qmf.build_static_qw_index import main
from qmapli.wg_qmf.point_io import read_points
from qmapli.wg_qmf.search import uniform_qmf, workload_guided_qmf
from qmapli.wg_qmf.index import QWBuildConfig, _select_joint_root_action


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_r4_checkpoint_is_unchanged():
    checkpoint = ROOT / "models/r4.pt"
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == (
        "0d10709b1440549e2aec605b1b68754aff0e8fbb9d793e0f31a64df9da213b5d"
    )


def test_builder_help_does_not_depend_on_old_campaign_state(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    text = capsys.readouterr().out
    assert "uniform_qmf" in text
    assert "beam16" not in text


@pytest.mark.parametrize("mode", ["uniform_qmf", "wg_qmf"])
def test_python_build_and_cpp_query_match_exact_point_ids(mode, tmp_path, native_build):
    points = np.random.default_rng(21).uniform(size=(512, 2)).astype(np.float32).astype(np.float64)
    ids = np.arange(len(points)) + 1000
    points_file = tmp_path / "points.csv"
    with points_file.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y", "id"])
        writer.writerows((x, y, int(identifier)) for (x, y), identifier in zip(points, ids))
    rectangles = np.array([
        [0, 0, 1, 1], [0.2, 0.3, 0.8, 0.7], [2, 2, 3, 3],
        [points[0, 0], points[0, 1], points[0, 0], points[0, 1]],
    ])
    queries_file = tmp_path / "queries.csv"
    with queries_file.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["query_id", "selectivity_group", "split", "xmin", "ymin", "xmax", "ymax"])
        writer.writerows((i, "test", "train", *rectangle) for i, rectangle in enumerate(rectangles))
    index = tmp_path / "qmf.idx"
    assert main([
        "--mode", mode, "--r4-checkpoint", str(ROOT / "models/r4.pt"),
        "--points", str(points_file), "--point-count", str(len(points)),
        "--train-queries", str(queries_file), "--index", str(index),
        "--metadata", str(tmp_path / "metadata.json"), "--context-seed", "20260910",
        "--beta-leaf", "1.2779084295340111e-09", "--beta-point", "3.428255707467659",
        "--max-depth", "2", "--min-leaf-size", "64", "--max-leaves", "8",
    ]) == 0
    output = tmp_path / "ids.csv"
    runtime_method = "qmap_uniform_qmf" if mode == "uniform_qmf" else "qmap_qw"
    subprocess.run([
        str(native_build / "bin/qmf_query"), "--method", runtime_method,
        "--index", str(index), "--queries", str(queries_file), "--output", str(output),
    ], check=True, capture_output=True, text=True)
    with output.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(rectangles)
    for row, (xmin, ymin, xmax, ymax) in zip(rows, rectangles):
        expected = sorted(ids[
            (points[:, 0] >= xmin) & (points[:, 0] <= xmax)
            & (points[:, 1] >= ymin) & (points[:, 1] <= ymax)
        ].tolist())
        actual = sorted(int(value) for value in row["result_ids"].split(";") if value)
        assert actual == expected


def test_native_runtime_rejects_removed_comparison_methods(native_build):
    runtime = ctypes.CDLL(str(native_build / "lib/libqmap_runtime.so"))
    runtime.qmap_runtime_open.restype = ctypes.c_void_p
    runtime.qmap_runtime_open.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
    error = ctypes.create_string_buffer(512)
    assert runtime.qmap_runtime_open(b"flood", b"unused.idx", error, len(error)) is None
    assert b"only QMF" in error.value


def test_point_reader_validates_declared_count(tmp_path):
    points = tmp_path / "points.csv"
    points.write_text("x,y,id\n0.25,0.75,7\n")
    coordinates, identifiers = read_points(points, expected_count=1)
    assert coordinates.tolist() == [[0.25, 0.75]]
    assert identifiers.tolist() == [7]
    with pytest.raises(ValueError, match="row count differs"):
        read_points(points, expected_count=2)


def test_qmf_search_returns_valid_verified_candidates():
    costs = np.array([4.0, 1.0, 3.0, 2.0])
    for result in (
        uniform_qmf(costs, budget=32, seed=11),
        workload_guided_qmf(costs, np.full(4, 0.25), budget=32, seed=11),
    ):
        assert result.selected_cost == costs[result.selected_index]
        assert result.selected_cost == costs.min()


@pytest.mark.parametrize("mode", ["uniform_qmf", "wg_qmf"])
def test_joint_lookahead_retains_own_qmf_modes(mode):
    class ConstantScorer:
        score_seconds = 0.0

        def score_actions(self, points, queries, actions):
            return np.zeros(len(actions))

    points = np.random.default_rng(37).uniform(size=(1024, 2))
    queries = np.array([[0, 0, 1, 1], [0, 0, 0.5, 0.5], [0.2, 0.3, 0.9, 0.8]])
    action, metadata = _select_joint_root_action(
        mode=mode, points=points, train_queries=queries, scorer=ConstantScorer(),
        beta_leaf=1.2779084295340111e-09, beta_point=3.428255707467659,
        node_id=0, context_seed=20260910,
        config=QWBuildConfig(lookahead_depth=2, min_leaf_size=64),
    )
    assert action is not None and action.valid
    assert metadata["configuration_count"] > 1
    assert metadata["committed_actions"] == 1
    assert metadata["selected_cost"] >= metadata["exact_cost"]
