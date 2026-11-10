import random
import numpy as np
import torch
from torch import nn
class FixedInteractionController(nn.Module):
    """Frozen R4 action-scoring architecture."""

    def __init__(self, scalar_size: int, seed: int):
        super().__init__()
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(int(seed))
            self.cell_projection = nn.Conv2d(7, 4, kernel_size=1)
            self.spatial_mixing = nn.Conv2d(4, 4, kernel_size=3, padding=1)
            self.scalar_projection = nn.Linear(int(scalar_size), 8)
            self.fusion = nn.Linear(12, 8)
            self.output = nn.Linear(8, 1)

    def forward(self, scalar, spatial):
        shape = scalar.shape[:2]
        scalar_flat = scalar.reshape(-1, scalar.shape[-1])
        spatial_flat = spatial.reshape(-1, *spatial.shape[-3:])
        spatial_hidden = torch.tanh(self.cell_projection(spatial_flat))
        spatial_hidden = torch.tanh(self.spatial_mixing(spatial_hidden)).mean(dim=(-2, -1))
        scalar_hidden = torch.tanh(self.scalar_projection(scalar_flat))
        fused = torch.cat((scalar_hidden, spatial_hidden), dim=1)
        scores = self.output(torch.tanh(self.fusion(fused))).reshape(shape)
        return scores
CHANNEL_SCALES = torch.tensor((16.0, 16.0, 1.0, 1.0, 256.0, 16.0, 256.0))
class StrongSmallCNN(nn.Module):
    def __init__(self, scalar_size, seed):
        super().__init__()
        self.model = FixedInteractionController(scalar_size, seed)

    @property
    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    def forward(self, scalar, spatial):
        scaled = spatial * CHANNEL_SCALES.to(spatial.device).reshape(1, 7, 1, 1)
        return self.model(scalar[:, None, :], scaled[:, None, :, :, :]).flatten()
class ScoreOnlyAdapter(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def task_outputs(self, scalar, spatial):
        score = self.model(scalar, spatial)
        return torch.stack((score, score, score, score), dim=1)

    def forward(self, scalar, spatial):
        return self.model(scalar, spatial)
def _flat_task_scores(model, scalar, spatial):
    shape = scalar.shape[:2]
    flat_scalar = scalar.reshape(-1, scalar.shape[-1])
    flat_spatial = spatial.reshape(-1, *spatial.shape[-3:])
    if hasattr(model, "task_outputs"):
        scores = model.task_outputs(flat_scalar, flat_spatial)[:, 0]
    else:
        scores = model(flat_scalar, flat_spatial)
    return scores.reshape(shape)

def create_final_model(name,scalar_size,seed):
    if name != 'R4': raise ValueError('Only frozen R4 is packaged')
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    return ScoreOnlyAdapter(StrongSmallCNN(scalar_size,seed))

def score_groups(model,scalar,spatial,valid):
    return {'scores':_flat_task_scores(model,scalar,spatial)}
