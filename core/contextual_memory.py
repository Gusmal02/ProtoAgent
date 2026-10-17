"""
Memoria contextual: cada experiencia es una huella h_i = (ω_i, c_i).

La evocación ocurre cuando el contexto actual es similar al contexto de inserción.
La huella evocada actúa como prior sobre la consulta: orienta el reconocimiento
hacia lo que ya se vio en situaciones parecidas.

API:
  ContextualTrace   — dataclass: omega, context_vec, t_insert, strength
  ContextualMemory  — almacén de huellas con evoke() y reinforce() / decay()
"""

import math
import torch
import torch.nn.functional as F
from dataclasses import dataclass, field as dc_field


@dataclass
class ContextualTrace:
    omega:       torch.Tensor   # vector ω de la experiencia (3D)
    context_vec: torch.Tensor   # vector de contexto en el momento de inserción (3D)
    t_insert:    int            # paso de inserción
    strength:    float = 1.0   # fuerza de la huella (decae sin revisita, sube con evocación)
    label:       str = ""


def _cos(a: torch.Tensor, b: torch.Tensor) -> float:
    return F.cosine_similarity(a.unsqueeze(0), b.unsqueeze(0)).clamp(-1, 1).item()


def _angle_deg(a: torch.Tensor, b: torch.Tensor) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, _cos(a, b)))))


def _h6(trace: ContextualTrace, scale_c: float = 1.0) -> torch.Tensor:
    """Huella 6D concatenando ω normalizado y c normalizado."""
    on = F.normalize(trace.omega.float(), dim=0)
    cn = F.normalize(trace.context_vec.float(), dim=0) * scale_c
    return torch.cat([on, cn])


class ContextualMemory:
    """
    Almacén de huellas contextuales.

    evoke(c_actual, theta) → lista de ContextualTrace cuyo contexto es similar a c_actual.
    La similitud se mide como cos(c_actual, c_i) > theta.

    prior(traces, omega_query, alpha) → omega_primed
    Mezcla el query con la media de las huellas evocadas:
      omega_primed = alpha * omega_query + (1-alpha) * mean(omega_evocadas)
    normalizado a la misma magnitud.

    decay(gamma) / reinforce(trace, delta) — gestión de fuerza.
    """

    def __init__(self, theta_ctx: float = 0.5, gamma_decay: float = 0.01):
        self.traces: list[ContextualTrace] = []
        self.theta_ctx  = theta_ctx
        self.gamma_decay = gamma_decay

    def add(self, omega: torch.Tensor, context_vec: torch.Tensor,
            t_insert: int, label: str = "") -> ContextualTrace:
        tr = ContextualTrace(
            omega=omega.clone().float(),
            context_vec=context_vec.clone().float(),
            t_insert=t_insert,
            strength=1.0,
            label=label,
        )
        self.traces.append(tr)
        return tr

    def evoke(self, c_actual: torch.Tensor,
              theta: float | None = None) -> list[tuple[ContextualTrace, float]]:
        """Devuelve (trace, cos_ctx) para huellas cuyo contexto es similar a c_actual."""
        thr = theta if theta is not None else self.theta_ctx
        result = []
        c = c_actual.float()
        for tr in self.traces:
            sim = _cos(c, tr.context_vec)
            if sim > thr:
                result.append((tr, sim))
        result.sort(key=lambda x: -x[1])
        return result

    def prior(self, evoked: list[tuple[ContextualTrace, float]],
              omega_query: torch.Tensor, alpha: float = 0.7) -> torch.Tensor:
        """
        Mezcla omega_query con la media ponderada de huellas evocadas.
        alpha controla cuánto pesa el query vs el prior evocado.
        """
        if not evoked:
            return omega_query.float()
        weights = torch.tensor([sim for _, sim in evoked])
        weights = weights / weights.sum()
        omegas  = torch.stack([tr.omega for tr, _ in evoked])
        mean_ev = (weights.unsqueeze(1) * omegas).sum(dim=0)
        q  = omega_query.float()
        mag = q.norm().clamp(min=1e-8)
        primed = alpha * q + (1 - alpha) * mean_ev
        return primed / primed.norm().clamp(min=1e-8) * mag

    def decay(self) -> None:
        for tr in self.traces:
            tr.strength = max(0.0, tr.strength - self.gamma_decay)

    def reinforce(self, trace: ContextualTrace, delta: float = 0.1) -> None:
        trace.strength = min(1.0, trace.strength + delta)

    def h6_separation(self, tr_a: ContextualTrace, tr_b: ContextualTrace,
                      scale_c: float = 1.0) -> float:
        """Ángulo en espacio 6D entre dos huellas."""
        ha = _h6(tr_a, scale_c)
        hb = _h6(tr_b, scale_c)
        return _angle_deg(ha, hb)

    def novelty_primed(self, omega_primed: torch.Tensor,
                       field_omega: torch.Tensor) -> float:
        """
        Novelty de omega_primed respecto al campo (tensor [N,3]).
        novelty = 1 - max_cos_sobre_nodos.
        """
        norms = field_omega.norm(dim=1, keepdim=True).clamp(min=1e-8)
        q_n   = omega_primed / omega_primed.norm().clamp(min=1e-8)
        cos   = (field_omega / norms @ q_n).clamp(-1, 1)
        return float(1.0 - cos.max().item())

    def summary(self) -> dict:
        return {
            "n_traces": len(self.traces),
            "mean_strength": float(sum(t.strength for t in self.traces) / len(self.traces))
            if self.traces else 0.0,
        }
