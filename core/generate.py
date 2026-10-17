"""
Módulo de generación creativa — tres mecanismos.

  linear(p1, p2, alpha)        → interpolación lineal en ω-space
  slerp(p1, p2, alpha)         → geodésica en S² (respeta geometría esférica)
  organic(field, p1, p2, ...)  → patrón emergente de interferencia de consultas
"""

import torch
import numpy as np
from memory.insert import encode, resonance_scores
from memory.query import query_concurrent


def linear(p1: torch.Tensor, p2: torch.Tensor,
           alpha: float, magnitude: float = 1.5) -> torch.Tensor:
    """
    Interpolación lineal en ω-space. Ignora la curvatura de S².
    Introduce sesgos cuando la separación angular es grande (>90°).
    """
    c = (1.0 - alpha) * p1 + alpha * p2
    n = c.norm()
    return c / n.clamp(min=1e-12) * magnitude


def slerp(p1: torch.Tensor, p2: torch.Tensor,
          alpha: float, magnitude: float = 1.5) -> torch.Tensor:
    """
    Interpolación geodésica en S² (Spherical Linear intERPolation).

    Fórmula: slerp(p1, p2, α) = sin((1−α)θ)/sin(θ)·n1 + sin(αθ)/sin(θ)·n2
    donde θ = ángulo entre n1 y n2 en la esfera unitaria.

    Propiedades:
      - Velocidad constante sobre la geodésica (equidistante en ángulo)
      - En α=0.5 el punto está exactamente a θ/2 de cada extremo
      - En α→0 o α→1 converge a p1 o p2 respectivamente
      - No introduce sesgo por la curvatura
    """
    n1 = p1 / p1.norm().clamp(min=1e-12)
    n2 = p2 / p2.norm().clamp(min=1e-12)

    dot = float((n1 * n2).sum().clamp(-1.0, 1.0))
    theta = np.arccos(abs(dot))   # ángulo en [0, π/2] (trabajamos con dirección, no antipodal)

    if theta < 1e-6:
        # Casi paralelos: interpolación lineal es igual de buena
        return linear(p1, p2, alpha, magnitude)

    sin_theta = np.sin(theta)
    w1 = np.sin((1.0 - alpha) * theta) / sin_theta
    w2 = np.sin(alpha * theta) / sin_theta

    c = w1 * n1 + w2 * n2
    return c / c.norm().clamp(min=1e-12) * magnitude


def organic(field,
            p1: torch.Tensor,
            p2: torch.Tensor,
            omega_scale: float = 1.5,
            eps_amp: float = 0.3,
            T_query: int = 25,
            theta_amp: float = 0.01,
            top_k: int = 5,
            magnitude: float = 1.5) -> dict:
    """
    Generación orgánica por interferencia de consultas concurrentes.

    En lugar de calcular un punto medio en ω-space, emite p1 y p2 como
    ondas simultáneas en el campo. Los nodos más activados por la interferencia
    constructiva apuntan hacia el "concepto emergente" — el patrón que el campo
    produce cuando dos ideas coexisten en él.

    Devuelve:
      omega_emergent  : dirección media de omega en los top_k nodos más activados
      c_emergent      : tensor de patrón (directamente insertable)
      top_nodes       : nodos que más resonaron con la interferencia
      A_joint_mean    : amplitud media de la interferencia
    """
    import copy

    f_copy = copy.deepcopy(field)
    res = query_concurrent(f_copy, p1, p2,
                           omega_scale=omega_scale,
                           eps_amp=eps_amp,
                           T_query=T_query,
                           theta_amp=theta_amp)

    A_joint = torch.tensor(res['A_joint'])   # (N,)

    # Top-k nodos más activados por la interferencia
    topk_vals, topk_idx = A_joint.topk(min(top_k, field.N))
    active_nodes = topk_idx[topk_vals > theta_amp].tolist()

    if not active_nodes:
        # Fallback: usar el nodo más activado
        active_nodes = [int(A_joint.argmax())]

    idx = torch.tensor(active_nodes, dtype=torch.long)
    omega_active = field.omega[idx]   # (k, 3)

    # El patrón emergente es la dirección media ponderada por amplitud de activación
    weights = A_joint[idx].unsqueeze(-1)   # (k, 1)
    omega_mean = (weights * omega_active).sum(dim=0)
    c_emergent = omega_mean / omega_mean.norm().clamp(min=1e-12) * magnitude

    return {
        "c_emergent": c_emergent,
        "omega_emergent": omega_mean,
        "top_nodes": active_nodes,
        "A_joint_mean": float(A_joint[idx].mean()),
        "n_active": len(active_nodes),
    }


def interest_score(field, c_new: torch.Tensor,
                   omega_scale: float = 1.5) -> dict:
    """interest = novelty × max_resonance — métrica de valor creativo."""
    _, omega_c = encode(c_new, omega_scale)
    res_vec = resonance_scores(field.omega, omega_c)
    max_res = float(res_vec.clamp(min=0).max())
    novelty = 1.0 - max_res
    return {
        "interest":      round(novelty * max_res, 4),
        "novelty":       round(novelty, 4),
        "max_resonance": round(max_res, 4),
    }
