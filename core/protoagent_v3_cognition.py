"""Extensiones cognitivas opcionales y auditables para ProtoAgent v3.

No deciden ni ejecutan por sí mismas. Devuelven señales pequeñas que el núcleo
puede registrar y ponderar explícitamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch

from core.curiosity import uncertainty_score
from core.subconscious import TwoLayerMind


@dataclass
class CognitiveConfig:
    intuition_weight: float = 0.10
    curiosity_weight: float = 0.05
    enable_subconscious: bool = False
    enable_curiosity: bool = False


class CognitiveSignals:
    """Capa deliberadamente pequeña: familiaridad, pregunta y calibración."""

    def __init__(self, field_size: int, omega_scale: float, config: CognitiveConfig):
        self.cfg = config
        self.omega_scale = omega_scale
        self.subconscious = None
        if config.enable_subconscious:
            # Campo lento: no sustituye la memoria consciente del agente.
            self.subconscious = TwoLayerMind(N=max(12, field_size), omega_scale=omega_scale)
            self.subconscious.warmup(8)
        self.prediction_errors: list[float] = []

    def candidate_signals(self, field: Any, omega: torch.Tensor) -> dict:
        intuition = {"intuition_score": 0.0, "active": False}
        if self.subconscious is not None:
            intuition = self.subconscious.intuition_score(omega)
        epistemic = {"valor_epistemico": 0.0, "uncertainty_norm": 0.0}
        if self.cfg.enable_curiosity:
            epistemic = uncertainty_score(field, omega, self.omega_scale)
        return {
            "intuition": intuition,
            "epistemic": epistemic,
            "adjustment": (
                self.cfg.intuition_weight * float(intuition["intuition_score"])
                + self.cfg.curiosity_weight * float(epistemic["valor_epistemico"])
            ),
        }

    def learn(self, omega: torch.Tensor) -> None:
        if self.subconscious is not None:
            self.subconscious.insert(omega, alpha_learn=0.05, top_k=3, T_settle=1)

    def calibrate(self, predicted_reward: float, actual_reward: float) -> float:
        error = abs(float(predicted_reward) - float(actual_reward))
        self.prediction_errors.append(error)
        return error

    def summary(self) -> dict:
        return {
            "subconscious_enabled": self.subconscious is not None,
            "curiosity_enabled": self.cfg.enable_curiosity,
            "mean_prediction_error": (
                sum(self.prediction_errors) / len(self.prediction_errors)
                if self.prediction_errors else None
            ),
        }
