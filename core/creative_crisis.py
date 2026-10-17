"""
Crisis creativa inducida — síntesis de contradicciones.

El campo convive con una contradicción (E8), pero ni continuous_resolve
ni la resolución espontánea producen un tercer concepto. El campo elige
un ganador y borra al perdedor, o queda atrapado en el atractor contradictorio.

creative_crisis() no elige ganador. Aplica presión simultánea de ambos
patrones sobre los nodos que están "entre los dos" (nodos de tensión),
y deja que el acoplamiento del campo los lleve a su equilibrio natural.

E11 mostró que creative_crisis siempre produce evitación estructural:
los nodos de tensión (no alineados con ninguno) nunca apuntan al invariante
compartido (+X en el caso c_pos=(+X+Z), c_neg=(+X-Z)).

Para encontrar el invariante se propusieron tres mecanismos alternativos:

  C — two_phase_crisis: resolver hacia c_pos, resolver hacia c_neg,
      buscar nodos estables en ambas resoluciones.
  A — find_convergence_nodes: nodos con resonancia moderada con AMBOS.
      intersection_crisis: crisis usando esos nodos en lugar de los de tensión.
  B — intersection_invariant: calcular normalize(c_pos+c_neg) directamente.

API:
  creative_crisis(field, c_pos, c_neg, **kwargs) → dict
  find_tension_nodes(field, c_pos, c_neg, omega_scale, theta_tension) → list
  find_convergence_nodes(field, c_pos, c_neg, omega_scale, theta_low, theta_high) → list
  intersection_crisis(field, c_pos, c_neg, **kwargs) → dict
  two_phase_crisis(field, c_pos, c_neg, **kwargs) → dict
  intersection_invariant(c_pos, c_neg, omega_scale) → Tensor
"""

import copy
import torch
import numpy as np
from memory.insert import insert, encode, resonance_scores
from memory.insert import protect_pattern, unprotect_pattern


def find_tension_nodes(field,
                       c_pos: torch.Tensor,
                       c_neg: torch.Tensor,
                       omega_scale: float = 1.5,
                       theta_tension: float = 0.50) -> list[int]:
    """
    Nodos en zona de tensión entre c_pos y c_neg.

    Un nodo está en tensión si:
      |cos(ω_i, c_pos)| < theta_tension  (no alineado fuertemente con c_pos)
      |cos(ω_i, c_neg)| < theta_tension  (no alineado fuertemente con c_neg)
      |ω_i| > 0.05 × omega_scale         (tiene alguna orientación propia)

    Son los nodos que "sienten" los dos estímulos sin saber a cuál adherirse.
    """
    _, omega_pos = encode(c_pos, omega_scale)
    _, omega_neg = encode(c_neg, omega_scale)

    ni = field.omega / field.omega.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    np_pos = omega_pos / omega_pos.norm().clamp(min=1e-12)
    np_neg = omega_neg / omega_neg.norm().clamp(min=1e-12)

    cos_pos = (ni * np_pos).sum(dim=-1).abs()   # (N,)
    cos_neg = (ni * np_neg).sum(dim=-1).abs()   # (N,)
    mag     = field.omega.norm(dim=-1)           # (N,)

    in_tension = (cos_pos < theta_tension) & (cos_neg < theta_tension) & (mag > 0.05 * omega_scale)
    return in_tension.nonzero(as_tuple=True)[0].tolist()


def creative_crisis(field,
                    c_pos: torch.Tensor,
                    c_neg: torch.Tensor,
                    omega_scale: float = 1.5,
                    alpha_tension: float = 0.06,
                    n_tension_steps: int = 30,
                    steps_between: int = 15,
                    theta_tension: float = 0.50,
                    protect_level: float = 0.85,
                    alpha_insert_emergent: float = 0.20,
                    top_k: int = 5,
                    T_settle: int = 20,
                    gap_reduction_min: float = 0.05) -> dict:
    """
    Induce una crisis creativa y extrae el patrón emergente.

    Pasos:
    1. Identificar nodos de tensión (entre c_pos y c_neg).
    2. Protegerlos para que la presión dual no los borre.
    3. Ciclos alternados: insert(c_pos) → steps → insert(c_neg) → steps.
       No se elige ganador: ambas presiones actúan sobre los mismos nodos.
    4. Después de n_tension_steps ciclos, leer la dirección emergente de
       los nodos de tensión (promedio ponderado por |ω_i| — los más activados
       por la presión llevan más peso).
    5. Insertar c_new en el campo con alpha normal.
    6. Desproteger los nodos de tensión.
    7. Devolver c_new + métricas comparativas.

    Devuelve:
      c_emergent           : tensor 3D — el nuevo concepto
      tension_nodes        : lista de índices de nodos de tensión
      n_tension_nodes      : cuántos nodos estaban en tensión
      angle_pos            : ángulo entre c_new y c_pos (°)
      angle_neg            : ángulo entre c_new y c_neg (°)
      angle_midpoint_lin   : ángulo entre c_new y el midpoint lineal (°)
      novelty_emergent     : novelty de c_new en el campo antes de insertarlo
      gap_pre              : bimodalidad de la zona c_pos antes de la crisis
      gap_post             : bimodalidad de la zona c_pos después de insertar c_new
      omega_trajectory     : dirección media de los nodos de tensión cada 5 ciclos
      accepted             : True si gap_reduction >= gap_reduction_min (síntesis genuina)
                             False si el campo no redujo la tensión (evitación)
    """
    from core.curiosity import bimodality_score

    # ── 1. Medir estado pre-crisis ────────────────────────────────────────────
    bsc_pre = bimodality_score(field, c_pos, omega_scale)
    gap_pre = bsc_pre["gap"]

    # ── 2. Nodos de tensión ───────────────────────────────────────────────────
    tension_idx = find_tension_nodes(field, c_pos, c_neg, omega_scale, theta_tension)

    if len(tension_idx) < 2:
        # Si no hay nodos en tensión, usar los más cercanos al midpoint lineal
        mid = c_pos + c_neg
        mid_n = mid / mid.norm().clamp(min=1e-12)
        ni = field.omega / field.omega.norm(dim=-1, keepdim=True).clamp(min=1e-12)
        sims = (ni * mid_n).sum(dim=-1)
        _, tension_idx = sims.topk(min(5, field.N))
        tension_idx = tension_idx.tolist()

    # ── 3. Proteger nodos de tensión ──────────────────────────────────────────
    for idx in tension_idx:
        field.protection_factor[idx] = max(float(field.protection_factor[idx]), protect_level)

    # ── 4. Ciclos alternados de presión dual ──────────────────────────────────
    omega_trajectory = []

    for cycle in range(n_tension_steps):
        # Presión del lado positivo
        insert(field, c_pos, omega_scale=omega_scale, theta_res=0.20,
               alpha_learn=alpha_tension, top_k=top_k, T_settle=1)
        for _ in range(steps_between // 2):
            field.step()

        # Presión del lado negativo — misma intensidad, no hay ganador
        insert(field, c_neg, omega_scale=omega_scale, theta_res=0.20,
               alpha_learn=alpha_tension, top_k=top_k, T_settle=1)
        for _ in range(steps_between // 2):
            field.step()

        # Registrar dirección emergente de los nodos de tensión
        if (cycle + 1) % 5 == 0:
            idx_t = torch.tensor(tension_idx, dtype=torch.long)
            omegas = field.omega[idx_t]              # (k, 3)
            mags   = omegas.norm(dim=-1, keepdim=True)  # (k, 1)
            weighted = (omegas * mags).sum(dim=0)
            if weighted.norm() > 1e-8:
                direction = weighted / weighted.norm() * omega_scale
                omega_trajectory.append(direction.tolist())

    # ── 5. Patrón emergente = media ponderada de los nodos de tensión ─────────
    idx_t  = torch.tensor(tension_idx, dtype=torch.long)
    omegas = field.omega[idx_t]                      # (k, 3)
    mags   = omegas.norm(dim=-1, keepdim=True)       # (k, 1)
    weighted_sum = (omegas * mags).sum(dim=0)        # (3,)

    if weighted_sum.norm() < 1e-8:
        c_emergent = (c_pos + c_neg) / 2
        c_emergent = c_emergent / c_emergent.norm().clamp(min=1e-12) * omega_scale
    else:
        c_emergent = weighted_sum / weighted_sum.norm() * omega_scale

    # ── 6. Novelty antes de insertar ─────────────────────────────────────────
    res_e = resonance_scores(field.omega, c_emergent / c_emergent.norm() * omega_scale)
    novelty_emergent = float(1 - res_e.clamp(min=-1).max())

    # ── 7. Medir gap ANTES de insertar (para decidir si aceptar) ─────────────
    bsc_post_preview = bimodality_score(field, c_pos, omega_scale)

    # Inserción provisional en una copia para ver cuánto reduce el gap
    import copy as _copy
    field_copy = _copy.deepcopy(field)
    insert(field_copy, c_emergent, omega_scale=omega_scale, theta_res=0.15,
           alpha_learn=alpha_insert_emergent, top_k=top_k, T_settle=T_settle)
    bsc_if_inserted = bimodality_score(field_copy, c_pos, omega_scale)
    gap_reduction_preview = gap_pre - bsc_if_inserted["gap"]

    accepted = gap_reduction_preview >= gap_reduction_min

    # Solo insertar si el criterio de síntesis genuina se cumple
    if accepted:
        insert(field, c_emergent, omega_scale=omega_scale, theta_res=0.15,
               alpha_learn=alpha_insert_emergent, top_k=top_k, T_settle=T_settle)

    # ── 8. Desproteger nodos de tensión ───────────────────────────────────────
    for idx in tension_idx:
        field.protection_factor[idx] = 0.0

    # ── 9. Medir estado post-crisis (con o sin inserción) ────────────────────
    bsc_post = bimodality_score(field, c_pos, omega_scale)
    gap_post = bsc_post["gap"]

    # ── 10. Ángulos entre c_new y los originales ──────────────────────────────
    def angle_deg(a, b):
        na = a / a.norm().clamp(min=1e-12)
        nb = b / b.norm().clamp(min=1e-12)
        cos = float((na * nb).sum().clamp(-1, 1))
        return float(np.degrees(np.arccos(abs(cos))))

    midpoint_lin = c_pos + c_neg
    midpoint_lin = midpoint_lin / midpoint_lin.norm().clamp(min=1e-12) * omega_scale

    return {
        "c_emergent":          c_emergent,
        "tension_nodes":       tension_idx,
        "n_tension_nodes":     len(tension_idx),
        "angle_pos":           round(angle_deg(c_emergent, c_pos), 2),
        "angle_neg":           round(angle_deg(c_emergent, c_neg), 2),
        "angle_midpoint_lin":  round(angle_deg(c_emergent, midpoint_lin), 2),
        "novelty_emergent":    round(novelty_emergent, 4),
        "gap_pre":             round(gap_pre, 4),
        "gap_post":            round(gap_post, 4),
        "gap_reduction":       round(gap_pre - gap_post, 4),
        "accepted":            accepted,
        "verdict":             "síntesis" if accepted else "evitación",
        "omega_trajectory":    omega_trajectory,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Opción C — Crisis en dos fases (two_phase_crisis)
# ═══════════════════════════════════════════════════════════════════════════════

def two_phase_crisis(field,
                     c_pos: torch.Tensor,
                     c_neg: torch.Tensor,
                     omega_scale: float = 1.5,
                     n_resolve_cycles: int = 15,
                     alpha_per_step: float = 0.04,
                     steps_between: int = 15,
                     stability_threshold: float = 0.80,
                     top_k_stable: int = 5,
                     alpha_insert: float = 0.15,
                     T_settle: int = 20,
                     gap_reduction_min: float = 0.05) -> dict:
    """
    Encuentra el invariante resolviendo el conflicto en ambas direcciones.

    Protocolo:
      1. Clonar el campo dos veces (field_a, field_b).
      2. field_a: resolver continuous_resolve(c_pos, c_neg) — c_pos gana.
      3. field_b: resolver continuous_resolve(c_neg, c_pos) — c_neg gana.
      4. Para cada nodo i, medir cos(omega_a_i, omega_b_i).
         Nodos estables: cos alto — terminaron en la misma dirección
         independientemente de qué lado ganó. Esos apuntan al invariante.
      5. c_invariant = promedio ponderado de omega_a[estables] (por estabilidad).
      6. Insertar si gap_reduction >= gap_reduction_min.
    """
    from core.curiosity import continuous_resolve, bimodality_score

    bsc_pre = bimodality_score(field, c_pos, omega_scale)
    gap_pre = bsc_pre["gap"]

    field_a = copy.deepcopy(field)
    field_b = copy.deepcopy(field)

    # Fase A: c_pos gana
    continuous_resolve(field_a, c_pos, c_neg,
                       omega_scale=omega_scale,
                       alpha_per_step=alpha_per_step,
                       n_steps=n_resolve_cycles,
                       steps_between=steps_between,
                       gap_target=0.02)

    # Fase B: c_neg gana
    continuous_resolve(field_b, c_neg, c_pos,
                       omega_scale=omega_scale,
                       alpha_per_step=alpha_per_step,
                       n_steps=n_resolve_cycles,
                       steps_between=steps_between,
                       gap_target=0.02)

    omega_a = field_a.omega  # (N, 3)
    omega_b = field_b.omega  # (N, 3)

    # Estabilidad por nodo: cos entre los estados finales de ambas resoluciones
    na = omega_a / omega_a.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    nb = omega_b / omega_b.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    stability = (na * nb).sum(dim=-1)  # (N,) — cos entre destinos

    stable_mask = stability >= stability_threshold
    n_stable = int(stable_mask.sum())

    def _angle_deg(a, b):
        na_ = a / a.norm().clamp(min=1e-12)
        nb_ = b / b.norm().clamp(min=1e-12)
        return float(np.degrees(np.arccos(float((na_ * nb_).sum().clamp(-1, 1)))))

    if n_stable < 2:
        # Sin nodos estables: usar los top-k más estables
        _, top_idx = stability.topk(min(top_k_stable, field.N))
        stable_mask = torch.zeros(field.N, dtype=torch.bool)
        stable_mask[top_idx] = True
        n_stable = int(stable_mask.sum())

    # c_invariant = promedio de omega_a de los nodos estables (ponderado por estabilidad)
    weights = stability[stable_mask].clamp(min=0).unsqueeze(-1)   # (k, 1)
    stable_omegas = omega_a[stable_mask]                           # (k, 3)
    c_invariant_raw = (stable_omegas * weights).sum(dim=0)
    if c_invariant_raw.norm() < 1e-8:
        c_invariant_raw = stable_omegas.mean(dim=0)
    c_invariant = c_invariant_raw / c_invariant_raw.norm() * omega_scale

    # Novedad antes de insertar
    res_e = resonance_scores(field.omega, c_invariant / c_invariant.norm() * omega_scale)
    novelty_inv = float(1 - res_e.clamp(min=-1).max())

    # Probar en copia si reduce el gap
    field_copy = copy.deepcopy(field)
    insert(field_copy, c_invariant, omega_scale=omega_scale, theta_res=0.15,
           alpha_learn=alpha_insert, top_k=top_k_stable, T_settle=T_settle)
    from core.curiosity import bimodality_score as _bms
    gap_if_inserted = _bms(field_copy, c_pos, omega_scale)["gap"]
    gap_reduction = gap_pre - gap_if_inserted

    accepted = gap_reduction >= gap_reduction_min
    if accepted:
        insert(field, c_invariant, omega_scale=omega_scale, theta_res=0.15,
               alpha_learn=alpha_insert, top_k=top_k_stable, T_settle=T_settle)

    bsc_post = bimodality_score(field, c_pos, omega_scale)
    gap_post = bsc_post["gap"]

    return {
        "c_invariant":      c_invariant,
        "n_stable_nodes":   n_stable,
        "stability_scores": stability.tolist(),
        "novelty":          round(novelty_inv, 4),
        "gap_pre":          round(gap_pre, 4),
        "gap_post":         round(gap_post, 4),
        "gap_reduction":    round(gap_pre - gap_post, 4),
        "accepted":         accepted,
        "verdict":          "síntesis" if accepted else "evitación",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Opción A — Nodos de convergencia (intersection_crisis)
# ═══════════════════════════════════════════════════════════════════════════════

def find_convergence_nodes(field,
                           c_pos: torch.Tensor,
                           c_neg: torch.Tensor,
                           omega_scale: float = 1.5,
                           theta_low: float = 0.30,
                           theta_high: float = 0.75) -> list[int]:
    """
    Nodos que resuenan moderadamente con AMBOS patrones.

    Un nodo en zona de convergencia tiene:
      theta_low < cos(ω_i, c_pos) < theta_high
      theta_low < cos(ω_i, c_neg) < theta_high

    Estos nodos ya apuntan en la dirección compartida por c_pos y c_neg.
    A diferencia de los nodos de tensión (que no resuenan con ninguno),
    los de convergencia resuenan con ambos — están en la intersección.
    """
    _, omega_p = encode(c_pos, omega_scale)
    _, omega_n = encode(c_neg, omega_scale)

    ni = field.omega / field.omega.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    np_ = omega_p / omega_p.norm().clamp(min=1e-12)
    nn_ = omega_n / omega_n.norm().clamp(min=1e-12)

    cos_p = (ni * np_).sum(dim=-1)   # (N,)
    cos_n = (ni * nn_).sum(dim=-1)   # (N,)
    mag   = field.omega.norm(dim=-1)

    in_convergence = (
        (cos_p > theta_low) & (cos_p < theta_high) &
        (cos_n > theta_low) & (cos_n < theta_high) &
        (mag > 0.05 * omega_scale)
    )
    return in_convergence.nonzero(as_tuple=True)[0].tolist()


def intersection_crisis(field,
                        c_pos: torch.Tensor,
                        c_neg: torch.Tensor,
                        omega_scale: float = 1.5,
                        theta_low: float = 0.30,
                        theta_high: float = 0.75,
                        alpha_tension: float = 0.06,
                        n_tension_steps: int = 30,
                        steps_between: int = 15,
                        protect_level: float = 0.85,
                        alpha_insert: float = 0.20,
                        top_k: int = 5,
                        T_settle: int = 20,
                        gap_reduction_min: float = 0.05) -> dict:
    """
    Crisis usando nodos de convergencia en lugar de nodos de tensión.

    Mismo protocolo que creative_crisis pero el conjunto de nodos es el
    complementario: los que ya resuenan con ambos. La presión dual sobre
    ellos debería reforzar la dirección compartida, no escapar a un neutral.
    """
    from core.curiosity import bimodality_score

    bsc_pre = bimodality_score(field, c_pos, omega_scale)
    gap_pre = bsc_pre["gap"]

    conv_idx = find_convergence_nodes(field, c_pos, c_neg, omega_scale, theta_low, theta_high)

    if len(conv_idx) < 2:
        # Fallback: usar los top-5 nodos con mayor suma de resonancia con ambos
        _, omega_p = encode(c_pos, omega_scale)
        _, omega_n = encode(c_neg, omega_scale)
        res_p = resonance_scores(field.omega, omega_p)
        res_n = resonance_scores(field.omega, omega_n)
        combined = (res_p + res_n)
        _, top_idx = combined.topk(min(5, field.N))
        conv_idx = top_idx.tolist()

    # Proteger nodos de convergencia durante la presión dual
    for idx in conv_idx:
        field.protection_factor[idx] = max(float(field.protection_factor[idx]), protect_level)

    # Ciclos alternados de presión (igual que creative_crisis)
    for _ in range(n_tension_steps):
        insert(field, c_pos, omega_scale=omega_scale, theta_res=0.20,
               alpha_learn=alpha_tension, top_k=top_k, T_settle=1)
        for _ in range(steps_between // 2):
            field.step()
        insert(field, c_neg, omega_scale=omega_scale, theta_res=0.20,
               alpha_learn=alpha_tension, top_k=top_k, T_settle=1)
        for _ in range(steps_between // 2):
            field.step()

    # Leer dirección de los nodos de convergencia
    idx_t = torch.tensor(conv_idx, dtype=torch.long)
    omegas = field.omega[idx_t]
    mags   = omegas.norm(dim=-1, keepdim=True)
    weighted_sum = (omegas * mags).sum(dim=0)

    if weighted_sum.norm() < 1e-8:
        c_emergent = (c_pos + c_neg) / 2
        c_emergent = c_emergent / c_emergent.norm().clamp(min=1e-12) * omega_scale
    else:
        c_emergent = weighted_sum / weighted_sum.norm() * omega_scale

    res_e = resonance_scores(field.omega, c_emergent)
    novelty_e = float(1 - res_e.clamp(min=-1).max())

    # Evaluar en copia
    field_copy = copy.deepcopy(field)
    insert(field_copy, c_emergent, omega_scale=omega_scale, theta_res=0.15,
           alpha_learn=alpha_insert, top_k=top_k, T_settle=T_settle)
    gap_if_inserted = bimodality_score(field_copy, c_pos, omega_scale)["gap"]
    gap_reduction_preview = gap_pre - gap_if_inserted

    accepted = gap_reduction_preview >= gap_reduction_min
    if accepted:
        insert(field, c_emergent, omega_scale=omega_scale, theta_res=0.15,
               alpha_learn=alpha_insert, top_k=top_k, T_settle=T_settle)

    for idx in conv_idx:
        field.protection_factor[idx] = 0.0

    bsc_post = bimodality_score(field, c_pos, omega_scale)
    gap_post = bsc_post["gap"]

    def _angle_deg(a, b):
        na = a / a.norm().clamp(min=1e-12)
        nb = b / b.norm().clamp(min=1e-12)
        return float(np.degrees(np.arccos(float((na * nb).sum().clamp(-1, 1)))))

    return {
        "c_emergent":         c_emergent,
        "n_convergence_nodes": len(conv_idx),
        "novelty":            round(novelty_e, 4),
        "gap_pre":            round(gap_pre, 4),
        "gap_post":           round(gap_post, 4),
        "gap_reduction":      round(gap_pre - gap_post, 4),
        "accepted":           accepted,
        "verdict":            "síntesis" if accepted else "evitación",
        "angle_pos":          round(_angle_deg(c_emergent, c_pos), 2),
        "angle_neg":          round(_angle_deg(c_emergent, c_neg), 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Opción B — Operador de intersección explícito
# ═══════════════════════════════════════════════════════════════════════════════

def intersection_invariant(c_pos: torch.Tensor,
                           c_neg: torch.Tensor,
                           omega_scale: float = 1.5) -> torch.Tensor:
    """
    Calcula el invariante algebraico de c_pos y c_neg.

    La suma vectorial c_pos + c_neg captura la componente compartida:
    las componentes opuestas se cancelan, la componente común se refuerza.

    Es el único mecanismo que puede garantizar encontrar +X en el caso
    c_pos=(+X+Z), c_neg=(+X-Z), porque es algebraica, no dinámica.

    Esto rompe la pureza del sistema: el campo obtiene acceso a operaciones
    sobre sus propios contenidos que la dinámica de osciladores no puede hacer.
    """
    raw = c_pos + c_neg
    if raw.norm() < 1e-8:
        # c_pos y c_neg son exactamente opuestos — no hay invariante
        return None
    return raw / raw.norm() * omega_scale


def algebraic_synthesis(field,
                        c_pos: torch.Tensor,
                        c_neg: torch.Tensor,
                        omega_scale: float = 1.5,
                        alpha_insert: float = 0.15,
                        top_k: int = 5,
                        T_settle: int = 20,
                        gap_reduction_min: float = 0.05) -> dict:
    """
    Inserta el invariante algebraico normalize(c_pos+c_neg) en el campo.

    Sirve como control: si la dinámica (opciones C y A) no encuentra +X
    pero la álgebra sí puede insertarlo y reducir el gap, entonces el
    mecanismo dinámico tiene un límite fundamental demostrado empíricamente.
    """
    from core.curiosity import bimodality_score

    bsc_pre = bimodality_score(field, c_pos, omega_scale)
    gap_pre = bsc_pre["gap"]

    c_inv = intersection_invariant(c_pos, c_neg, omega_scale)
    if c_inv is None:
        return {"error": "c_pos y c_neg son antipodales — no hay invariante"}

    res_e = resonance_scores(field.omega, c_inv)
    novelty_inv = float(1 - res_e.clamp(min=-1).max())

    # Evaluar en copia
    field_copy = copy.deepcopy(field)
    insert(field_copy, c_inv, omega_scale=omega_scale, theta_res=0.15,
           alpha_learn=alpha_insert, top_k=top_k, T_settle=T_settle)
    gap_if_inserted = bimodality_score(field_copy, c_pos, omega_scale)["gap"]
    gap_reduction = gap_pre - gap_if_inserted

    accepted = gap_reduction >= gap_reduction_min
    if accepted:
        insert(field, c_inv, omega_scale=omega_scale, theta_res=0.15,
               alpha_learn=alpha_insert, top_k=top_k, T_settle=T_settle)

    bsc_post = bimodality_score(field, c_pos, omega_scale)
    gap_post = bsc_post["gap"]

    def _angle_deg(a, b):
        na = a / a.norm().clamp(min=1e-12)
        nb = b / b.norm().clamp(min=1e-12)
        return float(np.degrees(np.arccos(float((na * nb).sum().clamp(-1, 1)))))

    c_x = torch.tensor([1.0, 0.0, 0.0]) * omega_scale
    return {
        "c_invariant":   c_inv,
        "angle_to_x":   round(_angle_deg(c_inv, c_x), 2),
        "angle_pos":    round(_angle_deg(c_inv, c_pos), 2),
        "angle_neg":    round(_angle_deg(c_inv, c_neg), 2),
        "novelty":      round(novelty_inv, 4),
        "gap_pre":      round(gap_pre, 4),
        "gap_post":     round(gap_post, 4),
        "gap_reduction": round(gap_pre - gap_post, 4),
        "accepted":     accepted,
        "verdict":      "síntesis" if accepted else "evitación",
    }
