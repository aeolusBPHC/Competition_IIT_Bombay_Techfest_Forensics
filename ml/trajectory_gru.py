from __future__ import annotations

import torch
from torch import nn


class TrajectoryGRU(nn.Module):
    """
    Platform-independent GRU for short-horizon 3D trajectory prediction.

    Input:
        [batch, history_steps, feature_count]

    Output:
        [batch, prediction_steps, 3]
        representing future x, y, z positions.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        prediction_steps: int = 10,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()

        self.prediction_steps = prediction_steps

        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.output = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, prediction_steps * 3),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [batch, history_steps, input_size]

        Returns:
            [batch, prediction_steps, 3]
        """
        _, hidden = self.gru(x)

        # Last GRU layer's hidden state.
        last_hidden = hidden[-1]

        prediction = self.output(last_hidden)

        return prediction.reshape(
            x.shape[0],
            self.prediction_steps,
            3,
        )
