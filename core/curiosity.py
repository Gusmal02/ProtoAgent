"""
Módulo de curiosidad autónoma.

  measure_interest(field, pool)         → termómetro de aburrimiento
  frontier_candidates(field, n)         → búsqueda dirigida por ignorancia
  uncertainty_score(field, c)           → varianza de resonance sobre todos los nodos
  question_candidates(field, n)         → preguntas dirigidas por incertidumbre epistémica
  evaluate_answer(field, c_ans, c_q)    → mide reducción de incertidumbre tras una respuesta
  AdaptiveThreshold                     → umbral que sigue al interest base del campo
  TrendThreshold                        → umbral basado en tendencia decreciente
  curiosity_step(field, pool, ...)      → ciclo autónomo con umbral fijo o adaptativo
  curiosity_loop(field, n_cycles, ...)  → bucle completo con estímulos externos opcionales
"""

import torch
import numpy as np
import copy
from memory.insert import insert, encode, resonance_scores
from core.generate import organic, slerp, interest_score


class AdaptiveThreshold:
    """
    Umbral de aburrimiento que se calibra automáticamente al interest del campo.

    Mantiene una media exponencial (EMA) del interest observado.
    El umbral es: threshold = beta × ema

    Cuando el interest cae por debajo de beta × (lo que normalmente ve),
    el campo se considera "aburrido" y dispara exploración.

    beta=0.7: el campo explora cuando tiene 30% menos interest del normal.
    beta=0.5: explora cuando tiene la mitad del interest normal (umbral laxo).

    Parámetros:
      alpha_ema : velocidad de actualización de la media (0.1–0.3)
      beta      : fracción del interés base que activa el trigger
      warmup    : ciclos iniciales sin trigger (para estabilizar la EMA)
    """
    def __init__(self, alpha_ema: float = 0.2, beta: float = 0.65,
                 warmup: int = 3):
        self.alpha_ema = alpha_ema
        self.beta      = beta
        self.warmup    = warmup
        self.ema       = None    # se inicializa con la primera observación
        self.cycle     = 0

    def update(self, interest: float) -> float:
        """Actualiza la EMA y devuelve el umbral actual."""
        self.cycle += 1
        if self.ema is None:
            self.ema = interest
        else:
            self.ema = (1 - self.alpha_ema) * self.ema + self.alpha_ema * interest
        return self.threshold

    def is_bored(self, interest: float) -> bool:
        """True si el interest actual está por debajo del umbral."""
        if self.cycle < self.warmup:
            return False
        return interest < self.threshold

    @property
    def threshold(self) -> float:
        return self.beta * (self.ema or 0.0)


class TrendThreshold:
    """
    Trigger basado en tendencia decreciente, no en nivel absoluto.

    El campo está "aburrido" cuando su interest ha bajado durante
    N ciclos consecutivos, independientemente del valor absoluto.

    Esto es más natural: el campo explora cuando nota que algo
    se está volviendo menos interesante, no cuando cruza un umbral.

    Parámetros:
      n_decline   : ciclos consecutivos de caída para disparar
      min_delta   : caída mínima por ciclo para contar como caída real
      cooldown    : ciclos de pausa después de explorar (para que las
                    nuevas inserciones eleven el interest antes de re-evaluar)
    """
    def __init__(self, n_decline: int = 3, min_delta: float = 0.002,
                 cooldown: int = 2):
        self.n_decline  = n_decline
        self.min_delta  = min_delta
        self.cooldown   = cooldown
        self._history   = []
        self._cd_left   = 0

    def update(self, interest: float) -> float:
        self._history.append(interest)
        if self._cd_left > 0:
            self._cd_left -= 1
        return interest   # el "threshold" es implícito

    def is_bored(self, interest: float) -> bool:
        if self._cd_left > 0:
            return False
        if len(self._history) < self.n_decline + 1:
            return False
        recent = self._history[-(self.n_decline + 1):]
        declines = sum(1 for i in range(len(recent) - 1)
                       if recent[i] - recent[i+1] >= self.min_delta)
        return declines >= self.n_decline

    def mark_explored(self):
        """Llamar después de explorar para activar el cooldown."""
        self._cd_left = self.cooldown

    @property
    def threshold(self) -> float:
        return self._history[-1] if self._history else 0.0


def uncertainty_score(field, c: torch.Tensor,
                      omega_scale: float = 1.5) -> dict:
    """
    Mide la incertidumbre epistémica del campo sobre la dirección c.

    uncertainty = Var_i[ resonance(omega_i, omega_c) ]

    Alta varianza significa que los nodos no se ponen de acuerdo sobre c:
    algunos resuenan fuerte (dicen "sé algo de esto"), otros resuenan débil
    o negativo (dicen "no conozco esto"). El campo tiene conocimiento contradictorio.

    La incertidumbre normalizada divide por la varianza baseline del campo
    (varianza de resonance con una dirección aleatoria fija) para separar
    la heterogeneidad estructural del conflicto semántico real.

    Devuelve:
      uncertainty_raw    : varianza bruta de resonance_scores
      uncertainty_norm   : varianza normalizada por baseline
      interest           : novelty × max_resonance (como en interest_score)
      valor_epistemico   : uncertainty_norm × interest
    """
    _, omega_c = encode(c, omega_scale)
    res_vec = resonance_scores(field.omega, omega_c)

    var_raw = float(res_vec.var())
    max_res = float(res_vec.clamp(min=0).max())
    novelty = 1.0 - max_res
    interest = novelty * max_res

    # Baseline: varianza del campo ante una dirección fija de referencia
    # Usamos el polo norte de S² como referencia estable
    ref = torch.zeros(3); ref[0] = omega_scale
    _, omega_ref = encode(ref, omega_scale)
    res_ref = resonance_scores(field.omega, omega_ref)
    var_baseline = float(res_ref.var().clamp(min=1e-8))

    uncertainty_norm = var_raw / var_baseline

    return {
        "uncertainty_raw":  round(var_raw, 5),
        "uncertainty_norm": round(uncertainty_norm, 4),
        "interest":         round(interest, 4),
        "novelty":          round(novelty, 4),
        "max_resonance":    round(max_res, 4),
        "valor_epistemico": round(uncertainty_norm * interest, 5),
    }


def question_candidates(field,
                        n: int = 10,
                        omega_scale: float = 1.5,
                        magnitude: float = 1.5,
                        oversample: int = 8) -> list:
    """
    Encuentra las mejores preguntas epistémicas del campo.

    Una buena pregunta es una región de ω-space donde el campo:
      (a) tiene conocimiento contradictorio (uncertainty_norm alta)
      (b) aún tiene algo con qué conectar (interest > 0)

    Ordena por valor_epistémico = uncertainty_norm × interest.

    Devuelve lista de (valor_epistemico, c, scores) ordenada descendente.
    """
    n_sample = n * oversample
    torch.manual_seed(field.t_step % 10000 + 3)
    dirs = torch.randn(n_sample, 3)
    dirs = dirs / dirs.norm(dim=-1, keepdim=True).clamp(min=1e-12) * magnitude

    scored = []
    for i in range(n_sample):
        c = dirs[i]
        sc = uncertainty_score(field, c, omega_scale)
        scored.append((sc["valor_epistemico"], c, sc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:n]


def evaluate_answer(field,
                    c_answer: torch.Tensor,
                    c_question: torch.Tensor,
                    omega_scale: float = 1.5) -> dict:
    """
    Evalúa cuánto reduce la incertidumbre una respuesta a una pregunta.

    Mide uncertainty_score en la región de la pregunta ANTES de insertar la
    respuesta (sin modificar el campo). La reducción real requeriría comparar
    pre/post inserción, pero aquí usamos un proxy: si la respuesta tiene
    alta resonancia con los nodos que discrepaban en la pregunta, la resolverá.

    Proxy de reducción:
      - Si c_answer está cerca de c_question (ángulo pequeño): responde directamente
      - Si c_answer tiene resonance cercana a la media del campo: no resuelve el conflicto
      - La reducción esperada = dot(omega_answer, omega_question) × uncertainty_q

    Devuelve:
      useful          : bool — vale la pena consolidar
      delta_unc_est   : reducción estimada de incertidumbre
      alignment       : similitud angular entre pregunta y respuesta
      novelty_answer  : novedad de la respuesta en el campo actual
    """
    sc_q = uncertainty_score(field, c_question, omega_scale)
    sc_a = uncertainty_score(field, c_answer,   omega_scale)

    _, omega_q = encode(c_question, omega_scale)
    _, omega_a = encode(c_answer,   omega_scale)

    nq = omega_q / omega_q.norm().clamp(min=1e-12)
    na = omega_a / omega_a.norm().clamp(min=1e-12)
    alignment = float((nq * na).sum().clamp(-1, 1))

    # Reducción estimada: respuesta alineada + incertidumbre previa alta = útil
    delta_unc_est = sc_q["uncertainty_norm"] * max(alignment, 0.0)

    # Útil si: reduce incertidumbre Y la respuesta es algo nuevo para el campo
    useful = (delta_unc_est > 0.05) and (sc_a["novelty"] > 0.1)

    return {
        "useful":           useful,
        "delta_unc_est":    round(delta_unc_est, 4),
        "alignment":        round(alignment, 4),
        "novelty_answer":   round(sc_a["novelty"], 4),
        "uncertainty_q":    sc_q["uncertainty_norm"],
        "valor_epistemico": sc_q["valor_epistemico"],
    }


def bimodality_score(field, c: torch.Tensor,
                     omega_scale: float = 1.5) -> dict:
    """
    Detecta si la incertidumbre del campo sobre c es por contradicción (bimodal)
    o por ignorancia distribuida (uniforme).

    Ignorancia:    resonance_scores ~ Uniform → var alta, gap ≈ 0
    Contradicción: resonance_scores tiene dos clusters separados → gap > 0

    El 'gap' es la brecha entre el mínimo del cluster positivo y el máximo
    del cluster negativo. Gap > 0 significa que hay una separación limpia:
    algunos nodos dicen fuertemente 'sí' y otros dicen fuertemente 'no'.

    Devuelve:
      gap          : brecha entre clusters (> 0 → bimodal)
      separation   : distancia entre medias de los dos clusters
      bimodal      : True si gap > 0
      n_pos        : nodos en el cluster positivo
      n_neg        : nodos en el cluster negativo
      cause        : "contradicción" | "ignorancia" | "conocido"
    """
    _, omega_c = encode(c, omega_scale)
    res_vec = resonance_scores(field.omega, omega_c)

    med = float(res_vec.median())
    margin = 0.1
    pos = res_vec[res_vec > med + margin]
    neg = res_vec[res_vec < med - margin]

    if len(pos) >= 2 and len(neg) >= 2:
        gap = float(pos.min() - neg.max())
        separation = float(pos.mean() - neg.mean())
        bimodal = gap > 0.0
    else:
        gap, separation, bimodal = 0.0, 0.0, False

    max_res = float(res_vec.clamp(min=0).max())
    # Un campo bien entrenado siempre tiene max_res > 0.7 en cualquier dirección
    # porque algunos nodos con omega_init cercano resuenan alto.
    # La distinción real viene del gap: cuán separados están los dos clusters.
    #   gap > 0.40 → dos clusters claramente separados (uno muy positivo, uno muy negativo)
    #   gap > 0 pero < 0.40 → bimodalidad suave, puede ser estructural
    #   gap ≤ 0 → distribución unimodal o sin clusters claros
    if bimodal and gap > 0.40:
        cause = "contradicción"
    elif max_res > 0.85 and gap < 0.25:
        cause = "conocido"
    elif not bimodal or gap < 0.05:
        cause = "ignorancia"
    else:
        cause = "ambiguo"

    return {
        "gap":        round(gap, 4),
        "separation": round(separation, 4),
        "bimodal":    bimodal,
        "n_pos":      int(len(pos)),
        "n_neg":      int(len(neg)),
        "max_res":    round(max_res, 4),
        "cause":      cause,
    }


def classification_question(field, c_zone: torch.Tensor,
                            omega_scale: float = 1.5):
    """
    Identifica los dos clusters de una zona contradictoria.

    Devuelve (c_pos, c_neg, n_pos, n_neg):
      c_pos : dirección media ponderada del cluster positivo (nodos que dicen 'sí')
      c_neg : dirección media ponderada del cluster negativo (nodos que dicen 'no')
      n_pos, n_neg : tamaños de cada cluster
    Si no hay clusters suficientes, devuelve (None, None, 0, 0).
    """
    _, omega_c = encode(c_zone, omega_scale)
    res_vec = resonance_scores(field.omega, omega_c)

    med    = float(res_vec.median())
    margin = 0.1
    pos_mask = res_vec > med + margin
    neg_mask = res_vec < med - margin

    if pos_mask.sum() < 2 or neg_mask.sum() < 2:
        return None, None, 0, 0

    weights_pos = res_vec[pos_mask].clamp(min=0).unsqueeze(-1)
    omega_pos   = (field.omega[pos_mask] * weights_pos).sum(dim=0)
    c_pos = omega_pos / omega_pos.norm().clamp(min=1e-12) * omega_scale

    weights_neg = (-res_vec[neg_mask]).clamp(min=0).unsqueeze(-1)
    omega_neg   = (field.omega[neg_mask] * weights_neg).sum(dim=0)
    c_neg = omega_neg / omega_neg.norm().clamp(min=1e-12) * omega_scale

    return c_pos, c_neg, int(pos_mask.sum()), int(neg_mask.sum())


def resolve_contradiction(field,
                          c_winner: torch.Tensor,
                          c_loser:  torch.Tensor,
                          omega_scale:     float = 1.5,
                          alpha_reinforce: float = 0.15,
                          alpha_forget:    float = 0.05) -> tuple:
    """
    Consolida el patrón ganador y aplica olvido activo al perdedor.

    Refuerza nodos afines al ganador y empuja nodos afines al perdedor
    suavemente hacia el ganador. No borra — reorienta.

    Devuelve (n_reforzados, n_olvidados).
    """
    _, omega_w = encode(c_winner, omega_scale)
    _, omega_l = encode(c_loser,  omega_scale)

    res_w = resonance_scores(field.omega, omega_w)
    res_l = resonance_scores(field.omega, omega_l)

    winner_mask = res_w > 0.3
    if winner_mask.any():
        field.omega[winner_mask] = (
            field.omega[winner_mask] * (1 - alpha_reinforce) +
            omega_w.unsqueeze(0) * alpha_reinforce
        )

    loser_mask = res_l > 0.3
    if loser_mask.any():
        field.omega[loser_mask] = (
            field.omega[loser_mask] * (1 - alpha_forget) +
            omega_w.unsqueeze(0) * alpha_forget
        )

    return int(winner_mask.sum()), int(loser_mask.sum())


def continuous_resolve(field,
                       c_winner: torch.Tensor,
                       c_loser:  torch.Tensor,
                       omega_scale:      float = 1.5,
                       alpha_per_step:   float = 0.04,
                       n_steps:          int   = 20,
                       steps_between:    int   = 15,
                       gap_target:       float = 0.10,
                       measure_every:    int   = 5) -> dict:
    """
    Resolución continua de contradicción: reinforcement repetido del ganador.

    E9-follow mostró que resolve_contradiction (impulso único) no desplaza el
    atractor: el campo absorbe la corrección y se recupera. La resolución real
    requiere presión sostenida.

    Protocolo:
      Repetir n_steps veces:
        1. resolve_contradiction(alpha=alpha_per_step) — impulso suave
        2. Correr steps_between pasos de dinámica libre (el campo integra)
        3. Medir gap cada measure_every ciclos
      Parar antes si gap < gap_target (contradicción resuelta)

    Parámetros:
      alpha_per_step  : alpha de refuerzo por ciclo (pequeño — presión suave)
      n_steps         : número máximo de ciclos
      steps_between   : pasos de campo libre entre ciclos (integración)
      gap_target      : gap objetivo — detener si se alcanza
      measure_every   : con qué frecuencia registrar el gap

    Devuelve:
      gap_trajectory  : lista de (ciclo, gap, cause) medidos
      resolved        : bool — ¿se alcanzó gap_target?
      n_cycles_used   : ciclos efectivamente ejecutados
      gap_final       : gap al terminar
    """
    from core.curiosity import bimodality_score  # evitar circular (mismo módulo)

    gap_trajectory = []
    resolved = False
    cycle = 0

    for cycle in range(n_steps):
        # Impulso suave de reinforcement
        resolve_contradiction(field, c_winner, c_loser,
                              omega_scale=omega_scale,
                              alpha_reinforce=alpha_per_step,
                              alpha_forget=alpha_per_step * 0.4)

        # Dinámica libre — el campo integra la corrección
        for _ in range(steps_between):
            field.step()

        # Medir
        if (cycle + 1) % measure_every == 0 or cycle == 0:
            bsc = bimodality_score(field, c_winner, omega_scale)
            gap_trajectory.append({
                "cycle": cycle + 1,
                "gap":   round(bsc["gap"], 4),
                "cause": bsc["cause"],
            })
            if bsc["gap"] < gap_target:
                resolved = True
                break

    # Medición final si no se midió en el último ciclo
    bsc_final = bimodality_score(field, c_winner, omega_scale)
    if not gap_trajectory or gap_trajectory[-1]["cycle"] != cycle + 1:
        gap_trajectory.append({
            "cycle": cycle + 1,
            "gap":   round(bsc_final["gap"], 4),
            "cause": bsc_final["cause"],
        })

    return {
        "gap_trajectory":  gap_trajectory,
        "resolved":        resolved,
        "n_cycles_used":   cycle + 1,
        "gap_final":       round(bsc_final["gap"], 4),
        "cause_final":     bsc_final["cause"],
    }


def measure_interest(field, pool: list,
                     omega_scale: float = 1.5,
                     n_sample: int = 20) -> dict:
    """
    Mide el interest_medio del campo evaluando combinaciones del pool.
    Si el pool es grande, muestrea n_sample pares al azar.
    """
    if len(pool) < 2:
        return {"interest_medio": 0.0, "novelty_medio": 0.0, "n_eval": 0}

    torch.manual_seed(field.t_step % 10000)
    pairs = []
    for _ in range(n_sample):
        i, j = torch.randint(0, len(pool), (2,)).tolist()
        if i == j:
            j = (j + 1) % len(pool)
        alpha = float(torch.rand(1)) * 0.8 + 0.1
        c = slerp(pool[i], pool[j], alpha)
        pairs.append(c)

    interests  = []
    novelties  = []
    for c in pairs:
        sc = interest_score(field, c, omega_scale)
        interests.append(sc["interest"])
        novelties.append(sc["novelty"])

    return {
        "interest_medio": round(float(np.mean(interests)), 4),
        "novelty_medio":  round(float(np.mean(novelties)), 4),
        "interest_max":   round(float(np.max(interests)), 4),
        "n_eval":         len(pairs),
    }


def frontier_candidates(field,
                        n: int = 20,
                        omega_scale: float = 1.5,
                        magnitude: float = 1.5,
                        oversample: int = 5) -> list:
    """
    Política de exploración dirigida por la ignorancia.

    Muestrea n×oversample direcciones aleatorias en ω-space.
    Para cada una calcula interest = novelty × max_resonance.
    Devuelve las n de mayor interest.

    Esto es búsqueda de la frontera del conocimiento:
    regiones donde el campo sabe poco (novedad alta) pero puede
    conectar con algo (resonancia no cero).
    """
    n_sample = n * oversample
    torch.manual_seed(field.t_step % 10000 + 1)
    dirs = torch.randn(n_sample, 3)
    dirs = dirs / dirs.norm(dim=-1, keepdim=True).clamp(min=1e-12) * magnitude

    scored = []
    for i in range(n_sample):
        c = dirs[i]
        sc = interest_score(field, c, omega_scale)
        scored.append((sc["interest"], c, sc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:n]   # [(interest, c, scores), ...]


def curiosity_step(field,
                   pool: list,
                   threshold=0.015,
                   n_candidates: int = 10,
                   top_k_insert: int = 2,
                   alpha_base: float = 0.10,
                   gamma_forget: float = 0.0003,
                   omega_scale: float = 1.5,
                   use_organic: bool = True) -> dict:
    """
    Un paso del ciclo autónomo.

    threshold: float fijo  OR  AdaptiveThreshold — ambos funcionan.
    Si interest_medio >= threshold: satisfecho, no actúa.
    Si interest_medio <  threshold: aburrido, dispara exploración.
    """
    state_pre = measure_interest(field, pool, omega_scale)
    interest_pre = state_pre["interest_medio"]

    # Soporte para umbral adaptativo
    if isinstance(threshold, AdaptiveThreshold):
        threshold.update(interest_pre)
        bored = threshold.is_bored(interest_pre)
        threshold_val = threshold.threshold
    else:
        bored = interest_pre < threshold
        threshold_val = threshold

    if not bored:
        return {
            "triggered":     False,
            "interest_pre":  interest_pre,
            "interest_post": interest_pre,
            "threshold_val": round(threshold_val, 4),
            "candidates":    [],
            "inserted":      [],
        }

    # ── Exploración autónoma ────────────────────────────────────────────────

    # 1. Candidatos por búsqueda de frontera
    frontier = frontier_candidates(field, n=n_candidates, omega_scale=omega_scale)

    # 2. Candidatos orgánicos (si hay pool suficiente)
    organic_candidates = []
    if use_organic and len(pool) >= 2:
        torch.manual_seed(field.t_step % 10000 + 2)
        for _ in range(n_candidates // 2):
            i, j = torch.randint(0, len(pool), (2,)).tolist()
            if i == j:
                j = (j + 1) % len(pool)
            res = organic(field, pool[i], pool[j],
                          omega_scale=omega_scale, eps_amp=0.25,
                          T_query=20, theta_amp=0.01, top_k=4)
            c = res["c_emergent"]
            sc = interest_score(field, c, omega_scale)
            organic_candidates.append((sc["interest"], c, sc))

    all_candidates = frontier + organic_candidates
    all_candidates.sort(key=lambda x: x[0], reverse=True)

    # 3. Consolidar top_k_insert
    inserted = []
    for sc_val, c, scores in all_candidates[:top_k_insert]:
        alpha_learn = min(alpha_base * (1 + sc_val * 4), 0.35)
        res = insert(field, c, omega_scale=omega_scale,
                     theta_res=0.15, alpha_learn=alpha_learn,
                     top_k=3, T_settle=12)
        pool.append(c.clone())
        inserted.append({
            "interest": scores["interest"],
            "novelty":  scores["novelty"],
            "nodes": res["neighbors"],
        })

        # Registrar exploración en f_activation de los nodos involucrados
        # (memoria de la curiosidad: el campo recuerda haber explorado aquí)
        if hasattr(field, 'f_activation') and res["neighbors"]:
            idx = torch.tensor(res["neighbors"], dtype=torch.long)
            field.f_activation[idx] += scores["interest"]

    # 4. Evolucionar con olvido
    for _ in range(15):
        field.step()
        field.forget_step(gamma_base=gamma_forget)

    state_post = measure_interest(field, pool, omega_scale)
    interest_post = state_post["interest_medio"]

    return {
        "triggered":      True,
        "interest_pre":   interest_pre,
        "interest_post":  interest_post,
        "delta_interest": round(interest_post - interest_pre, 4),
        "threshold_val":  round(threshold_val, 4),
        "candidates":     [(round(s, 4), sc) for s, c, sc in all_candidates[:6]],
        "inserted":       inserted,
        "n_frontier":     len(frontier),
        "n_organic":      len(organic_candidates),
    }


def curiosity_loop(field,
                   n_cycles: int,
                   pool: list,
                   external_fn=None,
                   threshold: float = 0.015,
                   n_candidates: int = 10,
                   top_k_insert: int = 2,
                   alpha_base: float = 0.10,
                   gamma_forget: float = 0.0003,
                   verbose: bool = True) -> list:
    """
    Bucle de curiosidad autónoma.

    En cada ciclo:
      1. Si external_fn devuelve un patrón: insertarlo (estímulo externo)
      2. curiosity_step: mide interest, explora si es bajo
      3. Registrar todo en el historial

    external_fn: callable(cycle) → torch.Tensor | None
                 Devuelve un patrón en el ciclo indicado o None.
                 None = sin estímulo externo en ese ciclo.
    """
    history = []

    for cycle in range(1, n_cycles + 1):
        external_inserted = False
        ext_novelty = None

        # Estímulo externo (si hay)
        if external_fn is not None:
            ext_pat = external_fn(cycle)
            if ext_pat is not None:
                res_ext = insert(field, ext_pat, omega_scale=1.5,
                                 theta_res=0.2, alpha_learn=0.15,
                                 top_k=3, T_settle=15)
                pool.append(ext_pat.clone())
                ext_sc = interest_score(field, ext_pat)
                ext_novelty = ext_sc["novelty"]
                external_inserted = True

        # Ciclo autónomo
        step = curiosity_step(field, pool,
                              threshold=threshold,
                              n_candidates=n_candidates,
                              top_k_insert=top_k_insert,
                              alpha_base=alpha_base,
                              gamma_forget=gamma_forget)

        record = {
            "cycle":              cycle,
            "triggered":          step["triggered"],
            "interest_pre":       step["interest_pre"],
            "interest_post":      step["interest_post"],
            "external_stimulus":  external_inserted,
            "ext_novelty":        ext_novelty,
            "pool_size":          len(pool),
            "inserted":           step.get("inserted", []),
        }
        history.append(record)

        if verbose:
            trig  = "EXPLORA" if step["triggered"] else "idle"
            ext   = "EXT" if external_inserted else "   "
            thr   = step.get("threshold_val", "—")
            print(f"  {cycle:>4}  {step['interest_pre']:>10.4f}  {step['interest_post']:>11.4f}  "
                  f"{thr:>8}  {trig:>8}  {ext}  pool={len(pool)}")

    return history
