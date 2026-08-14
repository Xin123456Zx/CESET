"""
Evidential INR-FG surrogate for NYX (256^3 ensemble).

Self-contained copy of the model needed for inference. The complete training
implementation lives in ../explorable-inr (INR_FG_Evidential + DecompGrid +
SnakeAlt and the evidential uncertainty utilities).

Input  : row = [x, y, z, p1, p2, p3]  (coords in [-1,1], params normalized to [0,1])
Output : per-point NIG (gamma, v, alpha, beta), concat on dim=1.

The `from utils import *` in the original models.py is intentionally dropped
here: this backend already has a `utils/` package that would shadow the
Evidential_INR `utils.py`, so the model is kept dependency-free instead.
"""
import numpy as np
import torch
from itertools import combinations


class SnakeAlt(torch.nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, input):
        return (input + 1. - torch.cos(2. * input)) / 2.


class DecompGrid(torch.nn.Module):
    '''
    grid_shape: [x_3d, y_3d, z_3d, x_2d, y_2d, z_2d, ..._2d]
    '''
    def __init__(self, grid_shape, num_feat_3d, num_feat_2d, num_feat_1d) -> None:
        super().__init__()
        assert num_feat_2d == num_feat_3d

        self.grid_shape = grid_shape
        self.num_feat_3d = num_feat_3d
        self.num_feat_2d = num_feat_2d
        self.num_feat_1d = num_feat_1d
        self.feature_grid_3d = torch.nn.Parameter(
            torch.Tensor(1, num_feat_3d, *reversed(grid_shape[:3])),
            requires_grad=True
        )
        torch.nn.init.uniform_(self.feature_grid_3d, a=-0.001, b=0.001)

        self.plane_dimid = list(combinations(range(len(grid_shape[3:6])), 2))
        self.plane_dims = list(combinations(grid_shape[3:6], 2))
        self.line_dimid = list(range(3, 3 + len(grid_shape[6:])))
        self.line_dims = grid_shape[6:]
        self.planes = []
        self.lines = []
        for i, dims in enumerate(self.plane_dims):
            plane = torch.nn.Parameter(
                torch.Tensor(1, num_feat_2d, *reversed(dims)),
                requires_grad=True
            )
            torch.nn.init.uniform_(plane, a=0.999, b=1.001)
            self.planes.append(plane)
        self.planes = torch.nn.ParameterList(self.planes)

        for i, dim in enumerate(self.line_dims):
            line = torch.nn.Parameter(
                torch.Tensor(num_feat_1d, dim),
                requires_grad=True
            )
            torch.nn.init.uniform_(line, a=0.01, b=0.25)
            self.lines.append(line)
        self.lines = torch.nn.ParameterList(self.lines)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        '''
        input: (Batch, Ndim)
        output: (Batch, num_feat_3d/2d)
        '''
        coords = x[..., :3]
        spatial_feats = torch.nn.functional.grid_sample(
            self.feature_grid_3d,
            coords.reshape(([1] * coords.shape[-1]) + list(coords.shape)),
            mode='bilinear', align_corners=True)
        spatial_feats = spatial_feats.squeeze()
        for i, dimids in enumerate(self.plane_dimid):
            x2d = x[:, dimids]
            x2d = x2d.reshape(([1] * x2d.shape[-1]) + list(x2d.shape))
            f2d = torch.nn.functional.grid_sample(
                self.planes[i], x2d, mode='bilinear', align_corners=True)
            f2d = f2d.squeeze()
            spatial_feats = spatial_feats * f2d
        param_feats = 1.
        for i, dimids in enumerate(self.line_dimid):
            p1d = x[:, dimids]
            p1dn = p1d * (self.line_dims[i] - 1)
            p1d_f = torch.floor(p1dn)
            weights = p1dn - p1d_f
            f1d = torch.lerp(
                self.lines[i][:, p1d_f.type(torch.int)],
                self.lines[i][:, torch.clamp(p1d_f + 1.0, min=0.0, max=self.line_dims[i] - 1).type(torch.int)],
                weights)
            f1d = f1d.squeeze()
            param_feats = param_feats * f1d
        if len(spatial_feats.shape) == 1:
            feats = torch.cat((spatial_feats, param_feats))
            return feats
        feats = torch.cat((spatial_feats.T, param_feats.T), 1)
        return feats


class INR_FG_Evidential(torch.nn.Module):
    def __init__(self, grid_shape, num_feat_3d, num_feat_2d, num_feat_1d, out_features: int,
                 dropout_layer: bool = False, gamma_sigmoid: bool = False) -> None:
        super().__init__()
        self.dg = DecompGrid(grid_shape=grid_shape, num_feat_3d=num_feat_3d,
                             num_feat_2d=num_feat_2d, num_feat_1d=num_feat_1d)

        self.hidden_nodes = 128
        self.out_features = out_features
        self.hasDP = dropout_layer
        self.gamma_sigmoid = gamma_sigmoid
        self.epsilon = 1e-6
        self.fc1 = torch.nn.Linear(num_feat_3d + num_feat_1d, self.hidden_nodes)
        self.fc2 = torch.nn.Linear(self.hidden_nodes, self.hidden_nodes)
        self.fc3 = torch.nn.Linear(self.hidden_nodes, self.hidden_nodes)
        self.fc4 = torch.nn.Linear(self.hidden_nodes, out_features * 4)
        self.relu = torch.nn.ReLU()
        self.sigmoid = torch.nn.Sigmoid()
        if self.hasDP:
            self.dp = torch.nn.Dropout(p=0.125)

    def _forward_features(self, x):
        x = self.dg(x)
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.relu(self.fc3(x))
        if self.hasDP:
            x = self.dp(x)
        return x

    def _activate_evidence(self, raw_output):
        gamma_raw, v_raw, alpha_raw, beta_raw = torch.chunk(raw_output, 4, dim=1)
        gamma = self.sigmoid(gamma_raw) if self.gamma_sigmoid else gamma_raw
        v = torch.nn.functional.softplus(v_raw) + self.epsilon
        alpha = torch.nn.functional.softplus(alpha_raw) + 1.0 + self.epsilon
        beta = torch.nn.functional.softplus(beta_raw) + self.epsilon
        return torch.cat((gamma, v, alpha, beta), dim=1)

    def forward(self, x):
        x = self._forward_features(x)
        x = self.fc4(x)
        return self._activate_evidence(x)


def nig_uncertainties(output):
    """Return (gamma, aleatoric_var, epistemic_var, predictive_var) from NIG output."""
    gamma, v, alpha, beta = torch.chunk(output, 4, dim=1)
    eps = 1e-10
    aleatoric_var = beta / (alpha - 1.0 + eps)
    epistemic_var = beta / (v * (alpha - 1.0) + eps)
    predictive_var = aleatoric_var + epistemic_var
    return gamma, aleatoric_var, epistemic_var, predictive_var
