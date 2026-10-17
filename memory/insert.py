"""
Protocolo de inserción resonante (Idea 2).

La inserción no solo encuentra vecinos — deforma los ω_i de esos vecinos
hacia ω_x con tasa α_learn. Esa deformación ES la memoria del campo:
la próxima vez que llegue un patrón similar, encontrará mayor resonancia.
"""

import torch
from core.oscillator import quat_normalize


def encode(x: torch.Tensor, omega_scale: float = 1.0) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Codifica patrón x ∈ ℝᵈ → (q_x, ω_x).
    Usa todas las dimensiones disponibles proyectadas a ℝ³.
    """
    q_x = torch.tensor([1., 0., 0., 0.])

    x_f = x.float()
    if x_f.shape[0] >= 3:
        # Reducción: combina bloques de dimensiones para preservar más información
        d = x_f.shape[0]
        third = d // 3
        omega_raw = torch.stack([
            x_f[:third].mean(),
            x_f[third:2*third].mean(),
            x_f[2*third:].mean(),
        ])
    else:
        omega_raw = torch.cat([x_f, torch.zeros(3 - x_f.shape[0])])

    norm = omega_raw.norm()
    omega_x = (omega_raw / norm.clamp(min=1e-12)) * omega_scale

    return q_x, omega_x


def resonance_scores(omega_field: torch.Tensor, omega_x: torch.Tensor) -> torch.Tensor:
    """
    resonance(i, x) = ⟨ω_i/|ω_i|, ω_x/|ω_x|⟩ ∈ [−1, 1] para cada nodo i.
    Solo dirección — ciego a la magnitud. Usado para selección de vecinos en insert.
    """
    ni = omega_field / omega_field.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    nx = omega_x / omega_x.norm().clamp(min=1e-12)
    return (ni * nx).sum(dim=-1)


def resonance_scores_mag(omega_field: torch.Tensor, omega_x: torch.Tensor,
                          omega_scale: float = 1.5) -> torch.Tensor:
    """
    resonance_mag(i, x) = cos(ω_i, ω_x) × tanh(|ω_i| / ω_scale).

    Penaliza nodos cuya magnitud decayó por forget_step:
    un patrón olvidado tiene magnitud baja → resonancia efectiva baja
    aunque su dirección coincida. Usado para novelty y diagnóstico.
    """
    ni = omega_field / omega_field.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    nx = omega_x / omega_x.norm().clamp(min=1e-12)
    cos_sim = (ni * nx).sum(dim=-1)
    mag_factor = torch.tanh(omega_field.norm(dim=-1) / omega_scale)
    return cos_sim * mag_factor


def insert(field,
           x: torch.Tensor,
           omega_scale: float = 1.5,
           theta_res: float = 0.5,
           alpha_learn: float = 0.03,
           top_k: int = 3,
           T_settle: int = 60,
           r_threshold: float = 0.6) -> dict:
    """
    Inserta patrón x en el campo de memoria.

    Pasos:
      1. Codificar x → (q_x, ω_x)
      2. Encontrar vecinos: top_k nodos más resonantes con resonancia > θ_res
         (inserción localizada — solo los nodos más cercanos al patrón aprenden)
      3. Excitar vecinos con perturbación proporcional a resonancia
      4. Deformar ω_i de vecinos hacia ω_x con tasa α_learn  ← esto es la memoria
      5. Propagar T_settle pasos y medir r_local
    """
    _, omega_x = encode(x, omega_scale)
    res_vec = resonance_scores(field.omega, omega_x)   # (N,)

    # Restringir a top_k más resonantes que superen θ_res
    above = torch.where(res_vec > theta_res)[0]
    if len(above) > top_k:
        topk_among = res_vec[above].topk(top_k).indices
        neighbor_idx = above[topk_among]
    else:
        neighbor_idx = above
    novelty = float(1.0 - res_vec.max().clamp(min=-1).item())
    max_res_node = int(res_vec.argmax().item())

    if len(neighbor_idx) == 0:
        return {
            "neighbors": [],
            "novelty": novelty,
            "r_local_pre": None,
            "r_local_post": None,
            "anomaly": True,
            "resonances": res_vec.tolist(),
            "max_resonance_node": max_res_node,
        }

    r_local_pre = float(field.q[neighbor_idx].mean(dim=0).norm().item())

    # Excitar vecinos
    xi = torch.zeros(field.N, 4)
    for idx in neighbor_idx:
        amp = float(res_vec[idx]) * 0.4
        xi[idx, 1:] = omega_x * amp

    # Deformar ω_i de vecinos hacia ω_x — esto es lo que hace que el campo recuerde
    for idx in neighbor_idx:
        lr = alpha_learn * float(res_vec[idx])
        field.omega[idx] = (1 - lr) * field.omega[idx] + lr * omega_x

    # H3: registrar cuándo fue escrito cada nodo
    for idx in neighbor_idx:
        field.t_insert[int(idx)] = field.t

    field.step(xi=xi)
    for _ in range(T_settle - 1):
        field.step()

    r_local_post = float(field.q[neighbor_idx].mean(dim=0).norm().item())
    anomaly = r_local_post < r_threshold

    if hasattr(field, 'f_activation'):
        for idx in neighbor_idx:
            field.f_activation[int(idx)] += float(res_vec[idx])

    return {
        "neighbors": neighbor_idx.tolist(),
        "novelty": novelty,
        "r_local_pre": r_local_pre,
        "r_local_post": r_local_post,
        "anomaly": anomaly,
        "resonances": res_vec.tolist(),
        "max_resonance_node": max_res_node,
    }


def novelty_topk_mean(field_omega: torch.Tensor, omega_x: torch.Tensor,
                      k: int = 20, omega_scale: float = 1.5) -> float:
    """
    S1 — Novedad por media de top-k resonancias en lugar de max global.

    max_i es frágil en campos grandes: si solo k nodos tienen señal,
    la media de esos k captura la densidad de conocimiento, no el outlier
    más alto. Más robusto a dilución cuando top_k << N.
    """
    scores = resonance_scores_mag(field_omega, omega_x, omega_scale)
    k_actual = min(k, len(scores))
    topk_vals = scores.topk(k_actual).values
    return float(1.0 - topk_vals.mean().clamp(min=-1))


def insert_multi(field,
                 x: torch.Tensor,
                 n_expose: int = 3,
                 steps_between: int = 10,
                 omega_scale: float = 1.5,
                 theta_res: float = 0.5,
                 alpha_learn: float = 0.15,
                 top_k: int = 5,
                 T_settle: int = 20) -> dict:
    """
    S2 — Inserción múltiple con pasos de libre evolución entre exposiciones.

    n_expose inserciones consecutivas del mismo patrón concentran la deformación
    en los mismos nodos. Cada exposición refuerza a los vecinos que ya aprendieron
    y amplía el territorio de resonancia. Equivale a ver el mismo dato varias veces.

    Devuelve el resultado de la última inserción con novelty acumulada mínima.
    """
    result = None
    for i in range(n_expose):
        result = insert(field, x, omega_scale=omega_scale, theta_res=theta_res,
                        alpha_learn=alpha_learn, top_k=top_k, T_settle=T_settle)
        if i < n_expose - 1:
            for _ in range(steps_between):
                field.step()
    return result


def protect_pattern(field,
                    x: torch.Tensor,
                    omega_scale: float = 1.5,
                    protection: float = 0.90,
                    theta_res: float = 0.20) -> list[int]:
    """
    Marca los nodos resonantes con x como protegidos frente al olvido.

    protection : valor a asignar en protection_factor[i] ∈ [0, 1]
                 0.90 → el nodo olvida al 10% de su tasa normal
                 1.00 → no olvida en absoluto
    theta_res  : umbral mínimo de resonancia para considerar un nodo resonante

    Devuelve la lista de nodos protegidos.
    Si el campo no tiene protection_factor (versión antigua), no hace nada.
    """
    if not hasattr(field, 'protection_factor'):
        return []

    _, omega_x = encode(x, omega_scale)
    res_vec = resonance_scores(field.omega, omega_x)

    protected = []
    for i in range(field.N):
        if float(res_vec[i]) > theta_res:
            # Tomar el máximo entre la protección actual y la nueva
            current = float(field.protection_factor[i])
            field.protection_factor[i] = max(current, protection)
            protected.append(i)

    return protected


def unprotect_pattern(field,
                      x: torch.Tensor,
                      omega_scale: float = 1.5,
                      theta_res: float = 0.20) -> list[int]:
    """Elimina la protección de los nodos resonantes con x."""
    if not hasattr(field, 'protection_factor'):
        return []
    _, omega_x = encode(x, omega_scale)
    res_vec = resonance_scores(field.omega, omega_x)
    cleared = []
    for i in range(field.N):
        if float(res_vec[i]) > theta_res:
            field.protection_factor[i] = 0.0
            cleared.append(i)
    return cleared
