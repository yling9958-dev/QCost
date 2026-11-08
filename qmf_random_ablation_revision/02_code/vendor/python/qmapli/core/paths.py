"""Dependency-sliced frozen production source; see source_inventory.md."""

from __future__ import annotations

import os

from pathlib import Path

def project_root():
    return Path(os.environ['REPRO_ROOT']).resolve()
