from pathlib import Path
import os
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"


@pytest.fixture(scope="session", autouse=True)
def single_threaded_torch():
    import torch

    torch.set_num_threads(1)


@pytest.fixture(scope="session")
def native_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("qmf_native")
    subprocess.run(
        ["cmake", "-S", str(ROOT / "src/cpp"), "-B", str(build)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build), "--parallel", "2"],
        check=True, capture_output=True, text=True,
    )
    return build
