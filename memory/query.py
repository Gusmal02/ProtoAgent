"""
Protocolo de consulta por interferencia (Idea 2).

Tres modos:
  query()            — consulta única, propaga dentro del campo de memoria.
  query_concurrent() — dos consultas simultáneas; la interferencia entre sus ondas
                       revela la similitud entre los patrones consultados.
  query_in_field()   — propaga en el campo de percepción (N=50). Mide τ_i real.
"""

import torch
from memory.insert import encode, resonance_scores as resonance
from core.oscillator import quat_normalize


def query(field,
          c: torch.Tensor,
          omega_scale: float = 1.0,
          eps_amp: float = 0.4,
          T_query: int = 100,
          theta_amp: float = 0.05) -> dict:
    """
    Emite la consulta c como onda en el campo y recoge la respuesta.

    Devuelve:
      resonators      : nodos con A_i > θ_amp
      A               : amplitud máxima por nodo  (N,)
      tau             : tiempo de pico por nodo   (N,)
      phi             : fase relativa al momento del pico (N,)
      novelty         : 1 − max_i resonancia(i, c)
      signature       : distribución compacta de (A_i, τ_i) para los resonadores
    """
    q_save = field.q.clone()   # guardar estado para restaurar después

    _, omega_c = encode(c, omega_scale)
    res_vec = resonance(field.omega, omega_c)   # (N,)
    novelty = float(1.0 - res_vec.clamp(min=-1).max().item())

    # Emisión inicial: cada nodo recibe una perturbación proporcional a su resonancia
    xi_init = torch.zeros(field.N, 4)
    for i in range(field.N):
        r = float(res_vec[i])
        if r > 0:
            xi_init[i] = torch.tensor([0., *omega_c.tolist()]) * r * eps_amp

    # Registrar trayectoria de |δq_i|
    A   = torch.zeros(field.N)
    tau = torch.zeros(field.N, dtype=torch.long)
    phi = torch.zeros(field.N)

    field.step(xi=xi_init)

    for t in range(1, T_query):
        field.step()
        # δq_i = desviación del nodo respecto a su vecindario (mismo que en m_i)
        q_nb = field._neighbor_mean_q()
        dev = (field.q - q_nb).norm(dim=-1)   # (N,)

        for i in range(field.N):
            if dev[i] > A[i]:
                A[i] = dev[i]
                tau[i] = t
                # fase: ángulo del cuaternión q_i respecto a q_c (dot en ℝ⁴)
                phi[i] = float((field.q[i] * xi_init[i]).sum() /
                               (field.q[i].norm() * xi_init[i].norm()).clamp(min=1e-12))

    resonators = torch.where(A > theta_amp)[0].tolist()

    # Actualizar f_activation de los resonadores
    if hasattr(field, 'f_activation'):
        for idx in resonators:
            field.f_activation[idx] += float(A[idx])

    # Restaurar estado del campo (la consulta no debe modificarlo)
    field.q = q_save

    # H3: incluir t_insert de cada resonador — cuándo fue escrita esa memoria
    signature = {
        str(i): {
            "A":        float(A[i]),
            "tau":      int(tau[i]),
            "phi":      float(phi[i]),
            "t_insert": float(field.t_insert[i]),
        }
        for i in resonators
    }

    return {
        "resonators": resonators,
        "A": A.tolist(),
        "tau": tau.tolist(),
        "phi": phi.tolist(),
        "novelty": novelty,
        "max_resonance_node": int(res_vec.argmax().item()),
        "signature": signature,
    }


def query_concurrent(field,
                     c1: torch.Tensor,
                     c2: torch.Tensor,
                     omega_scale: float = 1.0,
                     eps_amp: float = 0.4,
                     T_query: int = 100,
                     theta_amp: float = 0.05) -> dict:
    """
    Consultas concurrentes (T5 Idea 2 — experimento).

    Emite dos patrones simultáneamente como perturbaciones independientes.
    Las ondas viajan por el campo y se superponen.

    Hipótesis: la interferencia entre las dos ondas contiene información
    sobre la similitud entre los patrones.

    - Si c1 y c2 son similares → excitan los mismos nodos → interferencia
      constructiva → amplitud_total > suma individual.
    - Si c1 y c2 son distintos → excitan nodos distintos → interferencia
      destructiva o nula → amplitud_total ≈ suma individual.

    Devuelve:
      result_c1     : resultado de query individual c1 (campo limpio)
      result_c2     : resultado de query individual c2 (campo limpio)
      result_joint  : resultado de la consulta conjunta
      interference  : amplitud_joint − (amplitud_c1 + amplitud_c2) por nodo
      interference_score : media de |interference| — métrica escalar de interferencia
      similarity_from_interference : cos_sim(omega_c1, omega_c2) — referencia directa
    """
    q_save = field.q.clone()

    _, omega_c1 = encode(c1, omega_scale)
    _, omega_c2 = encode(c2, omega_scale)

    res1 = resonance(field.omega, omega_c1)   # (N,)
    res2 = resonance(field.omega, omega_c2)   # (N,)
    novelty_c1 = float(1.0 - res1.clamp(min=-1).max().item())
    novelty_c2 = float(1.0 - res2.clamp(min=-1).max().item())

    # ── Consulta individual c1 ────────────────────────────────────────────
    xi1 = torch.zeros(field.N, 4)
    for i in range(field.N):
        r = float(res1[i])
        if r > 0:
            xi1[i] = torch.tensor([0., *omega_c1.tolist()]) * r * eps_amp

    A1 = torch.zeros(field.N)
    field.step(xi=xi1)
    for _ in range(1, T_query):
        field.step()
        q_nb = field._neighbor_mean_q()
        dev = (field.q - q_nb).norm(dim=-1)
        A1 = torch.maximum(A1, dev)
    field.q = q_save.clone()

    # ── Consulta individual c2 ────────────────────────────────────────────
    xi2 = torch.zeros(field.N, 4)
    for i in range(field.N):
        r = float(res2[i])
        if r > 0:
            xi2[i] = torch.tensor([0., *omega_c2.tolist()]) * r * eps_amp

    A2 = torch.zeros(field.N)
    field.step(xi=xi2)
    for _ in range(1, T_query):
        field.step()
        q_nb = field._neighbor_mean_q()
        dev = (field.q - q_nb).norm(dim=-1)
        A2 = torch.maximum(A2, dev)
    field.q = q_save.clone()

    # ── Consulta conjunta (ambas simultáneas) ─────────────────────────────
    xi_joint = xi1 + xi2   # superposición lineal de perturbaciones
    A_joint = torch.zeros(field.N)
    field.step(xi=xi_joint)
    for _ in range(1, T_query):
        field.step()
        q_nb = field._neighbor_mean_q()
        dev = (field.q - q_nb).norm(dim=-1)
        A_joint = torch.maximum(A_joint, dev)
    field.q = q_save

    # ── Interferencia ─────────────────────────────────────────────────────
    interference = A_joint - (A1 + A2)  # (N,) positivo=constructiva, negativo=destructiva
    interference_score = float(interference.abs().mean().item())

    # Similitud directa entre los dos patrones como referencia
    n1 = omega_c1 / omega_c1.norm().clamp(min=1e-12)
    n2 = omega_c2 / omega_c2.norm().clamp(min=1e-12)
    sim_direct = float((n1 * n2).sum().item())

    return {
        "novelty_c1":     novelty_c1,
        "novelty_c2":     novelty_c2,
        "A_c1":           A1.tolist(),
        "A_c2":           A2.tolist(),
        "A_joint":        A_joint.tolist(),
        "interference":   interference.tolist(),
        "interference_score": interference_score,
        "similarity_direct":  sim_direct,
        "A_c1_mean":     float(A1.mean()),
        "A_c2_mean":     float(A2.mean()),
        "A_joint_mean":  float(A_joint.mean()),
    }


def query_in_field(prop_field,
                   source_nodes: list,
                   amplitude: float = 1.0,
                   T_query: int = 200,
                   theta_amp: float = 0.03,
                   alpha_damp: float = 0.05) -> dict:
    """
    Emite el "eco de memoria" como onda escalar (WaveField) desde source_nodes
    sobre la topología del campo de percepción, y mide τ_i = primer arribo.

    Usa la ecuación de onda discreta (∂²ε/∂t² = Lap(ε) − α·∂ε/∂t) en vez de
    la dinámica de Lohe. Esto garantiza propagación con velocidad finita:
    la onda viaja ~0.31 nodos/paso, así τ_i crece linealmente con la distancia.

    La dinámica de Lohe (ResonantField) sincroniza el campo en el instante t —
    toda la información de un kick llega a los vecinos en el mismo paso.
    La ecuación de onda tiene retardo causal real.
    """
    from core.wave import WaveField

    wave = WaveField(prop_field.N, prop_field.edge_index,
                     edge_weight=prop_field.edge_weight,
                     alpha_damp=alpha_damp, dt=prop_field.dt,
                     device=prop_field.device)

    for node in source_nodes:
        wave.perturb(node, amplitude)

    A         = torch.zeros(prop_field.N, device=prop_field.device)
    tau       = torch.full((prop_field.N,), T_query, dtype=torch.long, device=prop_field.device)
    first_hit = torch.zeros(prop_field.N, dtype=torch.bool, device=prop_field.device)
    phi       = torch.zeros(prop_field.N, device=prop_field.device)

    for t in range(T_query):
        wave.step()
        eps = wave.eps.abs()

        new_peak   = eps > A
        A          = torch.where(new_peak, eps, A)

        new_arrival = (~first_hit) & (eps > theta_amp)
        tau         = torch.where(new_arrival, torch.full_like(tau, t + 1), tau)
        phi         = torch.where(new_arrival, wave.eps, phi)
        first_hit   = first_hit | new_arrival

    resonators = torch.where(first_hit)[0].tolist()

    return {
        "resonators": resonators,
        "A":          A.tolist(),
        "tau":        tau.tolist(),       # τ_i = primer arribo (pasos)
        "phi":        phi.tolist(),       # signo de ε al momento del arribo
        "first_hit":  first_hit.tolist(),
        "n_reached":  int(first_hit.sum().item()),
    }


def bimodality_score(field) -> float:
    """
    Mide la bimodalidad del campo: qué tan dividido está en dos grupos opuestos.

    Proyecta omega_i en el eje de máxima varianza (primer componente SVD),
    luego mide el gap entre el cuartil superior y el inferior de la proyección.
    Un campo bimodal (dos hemisferios claramente separados) da score > 0.25.
    Un campo cohesivo (todos los nodos alineados) da score ≈ 0.
    """
    omega = field.omega  # (N, 3)
    # Eje de máxima varianza
    omega_c = omega - omega.mean(dim=0, keepdim=True)
    _, _, Vt = torch.linalg.svd(omega_c, full_matrices=False)
    axis = Vt[0]  # (3,) primer componente principal
    proj = (omega * axis).sum(dim=-1)  # (N,) proyección escalar
    N = proj.shape[0]
    q1 = float(proj.kthvalue(max(1, N // 4)).values.item())
    q3 = float(proj.kthvalue(min(N, 3 * N // 4)).values.item())
    return max(0.0, q3 - q1)


def find_bimodal_poles(field, k: int = 5):
    """
    Encuentra los dos polos de la bimodalidad del campo.

    Proyecta omega_i en el eje de máxima varianza, toma los top-k nodos
    con mayor proyección (hemisferio +) y los k con menor proyección
    (hemisferio -), y devuelve las medias de cada grupo normalizadas.

    Returns:
      (c_pos_est, c_neg_est) — tensores (3,) normalizados
    """
    omega = field.omega  # (N, 3)
    omega_c = omega - omega.mean(dim=0, keepdim=True)
    _, _, Vt = torch.linalg.svd(omega_c, full_matrices=False)
    axis = Vt[0]
    proj = (omega * axis).sum(dim=-1)  # (N,)
    k = min(k, field.N // 2)
    top_idx = proj.topk(k).indices
    bot_idx = proj.topk(k, largest=False).indices
    c_pos = omega[top_idx].mean(dim=0)
    c_neg = omega[bot_idx].mean(dim=0)
    c_pos = c_pos / c_pos.norm().clamp(min=1e-12)
    c_neg = c_neg / c_neg.norm().clamp(min=1e-12)
    return c_pos, c_neg


def collective_resonance(field, omega_vec,
                          omega_scale: float = 1.5) -> dict:
    """
    Termómetro Colectivo: mide cómo el CAMPO EN CONJUNTO (no un nodo individual)
    resuena con un patrón.

    Métricas:
      max_res    : resonancia del nodo más cercano (métrica clásica, engañosa)
      mean_res   : resonancia media del campo — el termómetro colectivo
      std_res    : dispersión — alta = campo dividido (bimodal o isótropo)
      pct_pos    : fracción de nodos con resonancia positiva
      bimodality : gap entre cuartil superior e inferior — detecta campo partido
      state      : PROFUNDO / SUPERFICIAL / DIVISIVO / ISOTROPO

    Estado:
      PROFUNDO    mean_res > 0.20 y std_res < 0.35  → el campo entero se alinea
      SUPERFICIAL max_res > 0.70 y mean_res < 0.05  → solo un nodo resuena (engaño)
      DIVISIVO    std_res > 0.45                    → campo partido en dos hemisferios
      ISOTROPO    |mean_res| < 0.05 y std_res < 0.35 → sin dirección colectiva
    """
    if not torch.is_tensor(omega_vec):
        omega_vec = torch.tensor(omega_vec, dtype=torch.float32)

    from memory.insert import encode, resonance_scores
    _, omega_c = encode(omega_vec, omega_scale)
    res_vec    = resonance_scores(field.omega, omega_c)   # (N,)

    max_res  = float(res_vec.max().item())
    mean_res = float(res_vec.mean().item())
    std_res  = float(res_vec.std().item())
    pct_pos  = float((res_vec > 0).float().mean().item())

    q1 = float(res_vec.kthvalue(max(1, field.N // 4)).values.item())
    q3 = float(res_vec.kthvalue(min(field.N, 3 * field.N // 4)).values.item())
    bimodality = q3 - q1

    if mean_res > 0.20 and std_res < 0.35:
        state = "PROFUNDO"
    elif max_res > 0.70 and mean_res < 0.05:
        state = "SUPERFICIAL"
    elif std_res > 0.45:
        state = "DIVISIVO"
    elif abs(mean_res) < 0.05 and std_res < 0.35:
        state = "ISOTROPO"
    else:
        state = "AMBIGUO"

    return {
        "max_res":    round(max_res,   4),
        "mean_res":   round(mean_res,  4),
        "std_res":    round(std_res,   4),
        "pct_pos":    round(pct_pos,   3),
        "bimodality": round(bimodality,4),
        "novelty_max":        round(1.0 - max_res,  4),
        "novelty_collective": round(1.0 - mean_res, 4),
        "state": state,
    }
