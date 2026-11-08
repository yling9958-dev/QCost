"""QMF index construction and range-query support."""

from __future__ import annotations

from pathlib import Path

import time

from typing import Sequence

import numpy as np

import torch

from ..scorer import score_groups

from ..scorer import create_final_model

from ..workload_action_interaction.actions import SplitAction

from .cached_features import node_action_features

class FrozenR4Prior:
    """Read-only R4 scorer; its public score direction is audited here."""

    direction = "higher_is_better"

    def __init__(self, checkpoint: Path):
        payload = torch.load(Path(checkpoint), map_location="cpu", weights_only=False)
        self.model = create_final_model("R4", len(payload["scalar_mean"]), 0)
        self.model.load_state_dict(payload["model"], strict=True)
        self.model.eval()
        self.scalar_mean = np.asarray(payload["scalar_mean"], dtype=np.float32)
        self.scalar_scale = np.asarray(payload["scalar_scale"], dtype=np.float32)
        self.score_calls = 0
        self.score_seconds = 0.0

    def score_actions(
        self,
        points: np.ndarray,
        context_queries: np.ndarray,
        actions: Sequence[SplitAction],
    ) -> np.ndarray:
        started = time.perf_counter()
        points = np.asarray(points, dtype=np.float64)
        scalar, spatial = node_action_features(points, context_queries, actions)
        standardized = (scalar - self.scalar_mean) / self.scalar_scale
        valid = np.ones((1, len(actions)), dtype=bool)
        with torch.no_grad():
            output = score_groups(
                self.model,
                torch.from_numpy(standardized[None, ...]),
                torch.from_numpy(spatial[None, ...]),
                torch.from_numpy(valid),
            )["scores"][0]
        self.score_calls += 1
        self.score_seconds += time.perf_counter() - started
        return output.cpu().numpy().astype(np.float64)
