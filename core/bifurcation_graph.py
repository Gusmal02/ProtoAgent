"""
core/bifurcation_graph.py  —  Memoria de bifurcaciones (Experience Graph)

El campo recuerda dónde y por qué bifurcó, qué ramas ganaron y cuáles
fallaron. Esto convierte la retrospectiva en un proceso que aprende con
cada ciclo — no solo repite la misma estrategia ante la misma tensión.

Estructura:
  Nodo    : posición ω (dirección normalizada), etiqueta opcional
  Arista  : bifurcación registrada con tension, outcome, branch_type, t

Uso típico:
  bg = BifurcationGraph()
  bg.add_bifurcation(omega_from, omega_to, tension=0.008,
                     outcome="winner", branch_type="organic_Z")
  bg.add_bifurcation(omega_from, omega_alt, tension=0.008,
                     outcome="dead_end", branch_type="antiphase")

  # Antes de generar nuevas ramas, filtrar candidatos por experiencia
  good, dead = bg.classify_candidates(candidates, sim_threshold=0.90)
"""

from __future__ import annotations
import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

import torch


# ── Tipos de arista ────────────────────────────────────────────────────────────

OUTCOMES = {"winner", "dead_end", "unexplored"}


@dataclass
class BifNode:
    """Nodo: posición ω normalizada + metadatos."""
    omega: torch.Tensor      # (3,) unitario
    label: str = ""
    visits: int = 0


@dataclass
class BifEdge:
    """Arista dirigida: bifurcación registrada."""
    from_idx: int
    to_idx:   int
    tension:  float
    outcome:  str            # "winner" | "dead_end" | "unexplored"
    branch_type: str         # "organic_Z", "antiphase", "superposition", "geodesic", …
    interest_Z:  float = 0.0
    gap_to_Z:    float = 0.0
    timestamp:   float = field(default_factory=time.time)
    round_idx:   int   = 0
    strength:    float = 1.0   # decae con gamma_bifgraph; 0 = ignorar
    # Registro causal compacto.  No convierte correlación en causa: conserva la
    # predicción anterior y la consecuencia de la intervención ejecutada.
    action: int | None = None
    predicted_reward: float | None = None
    observed_reward: float | None = None
    prediction_error: float | None = None
    duration: int = 1
    context: float = -1.0


class BifurcationGraph:
    """
    Grafo liviano de experiencia de bifurcaciones.

    Los nodos se comparan por similitud coseno — dos ωs a menos de
    `merge_threshold` ángulo (en grados) se tratan como el mismo punto.
    """

    def __init__(self, merge_threshold_deg: float = 15.0,
                 gamma_bifgraph: float = 0.0):
        """
        Args:
            merge_threshold_deg: ángulo máximo para fusionar nodos (grados).
            gamma_bifgraph: tasa de olvido por paso (0 = sin olvido).
                            Análogo a gamma_m del campo resonante.
                            Con γ=0.005, una arista pierde 50% de fuerza en ~140 pasos.
        """
        self.merge_threshold  = merge_threshold_deg
        self.gamma_bifgraph   = gamma_bifgraph
        self.nodes: list[BifNode] = []
        self.edges: list[BifEdge] = []

    # ── Construcción ──────────────────────────────────────────────────────────

    def _find_or_add(self, omega: torch.Tensor, label: str = "") -> int:
        """Devuelve el índice del nodo más cercano si está dentro del umbral,
        o crea un nuevo nodo y devuelve su índice."""
        omega_n = omega / (omega.norm() + 1e-8)
        for i, node in enumerate(self.nodes):
            cos = float(torch.dot(omega_n, node.omega).clamp(-1, 1))
            deg = math.degrees(math.acos(max(-1, min(1, cos))))
            if deg < self.merge_threshold:
                if label and not node.label:
                    node.label = label
                node.visits += 1
                return i
        self.nodes.append(BifNode(omega=omega_n, label=label, visits=1))
        return len(self.nodes) - 1

    def add_bifurcation(
        self,
        omega_from: torch.Tensor,
        omega_to:   torch.Tensor,
        tension:    float,
        outcome:    str,
        branch_type: str,
        interest_Z:  float = 0.0,
        gap_to_Z:    float = 0.0,
        label_from:  str = "",
        label_to:    str = "",
        round_idx:   int = 0,
        action: int | None = None,
        predicted_reward: float | None = None,
        observed_reward: float | None = None,
        prediction_error: float | None = None,
        duration: int = 1,
        context: float = -1.0,
    ) -> None:
        assert outcome in OUTCOMES, f"outcome debe ser uno de {OUTCOMES}"
        fi = self._find_or_add(omega_from, label_from)
        ti = self._find_or_add(omega_to,   label_to)
        self.edges.append(BifEdge(
            from_idx=fi, to_idx=ti,
            tension=tension, outcome=outcome, branch_type=branch_type,
            interest_Z=interest_Z, gap_to_Z=gap_to_Z,
            round_idx=round_idx,
            action=action, predicted_reward=predicted_reward,
            observed_reward=observed_reward, prediction_error=prediction_error,
            duration=max(1, int(duration)), context=float(context),
        ))

    # ── Olvido ────────────────────────────────────────────────────────────────

    def decay_step(self, n_steps: int = 1) -> None:
        """
        Decae la fuerza de todas las aristas: strength *= (1 - gamma)^n.
        Equivale a gamma_m en el campo resonante.
        Las aristas con strength < 0.05 se eliminan (ya no influyen).
        """
        if self.gamma_bifgraph <= 0.0:
            return
        factor = (1.0 - self.gamma_bifgraph) ** n_steps
        for e in self.edges:
            e.strength *= factor
        self.edges = [e for e in self.edges if e.strength >= 0.05]

    def recalibrate(self, notes_forecast: float,
                    forecast_threshold: float = 0.4) -> int:
        """
        Recalibración contextual: descuenta dead-ends que se registraron
        cuando el pronóstico era diferente al actual.

        Si el pronóstico actual es ALTO (>threshold) y un dead-end se
        registró en contexto de pronóstico BAJO, su penalización ya no aplica
        — se reduce su strength a la mitad.

        Devuelve el número de aristas recalibradas.
        """
        n_recal = 0
        for e in self.edges:
            if e.outcome != "dead_end":
                continue
            # interest_Z reutilizado como proxy del forecast en el momento del registro
            edge_forecast = e.interest_Z   # guardamos forecast_axis() en interest_Z
            mismatch = (notes_forecast > forecast_threshold
                        and edge_forecast < forecast_threshold)
            if mismatch:
                e.strength *= 0.5
                n_recal += 1
        return n_recal

    # ── Consulta ──────────────────────────────────────────────────────────────

    def dead_end_omegas(self) -> list[torch.Tensor]:
        """Devuelve los ωs de destino marcados como dead_end."""
        dead_idxs = {e.to_idx for e in self.edges if e.outcome == "dead_end"}
        return [self.nodes[i].omega for i in dead_idxs]

    def winner_omegas(self) -> list[torch.Tensor]:
        """Devuelve los ωs de destino marcados como winner."""
        win_idxs = {e.to_idx for e in self.edges if e.outcome == "winner"}
        return [self.nodes[i].omega for i in win_idxs]

    def classify_candidates(
        self,
        candidates: list[torch.Tensor],
        sim_threshold_deg: float = 20.0,
    ) -> tuple[list[torch.Tensor], list[torch.Tensor]]:
        """
        Clasifica candidatos en (prometedores, muertos) según la experiencia.

        Un candidato es "muerto" si está a menos de sim_threshold_deg
        de algún dead_end conocido. Los demás son prometedores.
        """
        dead_omegas = self.dead_end_omegas()
        good, dead = [], []
        for c in candidates:
            c_n = c / (c.norm() + 1e-8)
            is_dead = False
            for d in dead_omegas:
                cos = float(torch.dot(c_n, d).clamp(-1, 1))
                deg = math.degrees(math.acos(max(-1, min(1, cos))))
                if deg < sim_threshold_deg:
                    is_dead = True
                    break
            (dead if is_dead else good).append(c)
        return good, dead

    def intuition_from_graph(
        self,
        omega: torch.Tensor,
        top_k: int = 3,
        sim_threshold_deg: float = 60.0,
    ) -> dict:
        """
        Intuición basada en experiencia del grafo — complemento a TwoLayerMind.

        Calcula mean_res_winners × (1 − mean_res_dead_ends):
          - alta resonancia con winners  → el campo ya sabe que esa zona funciona
          - baja resonancia con dead-ends → no está cerca de lo que falló
          - el producto = "reconocimiento de camino prometedor sin certeza explícita"

        Equivale a: top_intuition_bridges() pero usando el historial del grafo
        en lugar del campo subconsciente de un TwoLayerMind.

        Returns:
          score        : float ∈ [0,1]
          res_winners  : resonancia media con los top-k winners cercanos
          res_dead     : resonancia media con los top-k dead-ends cercanos
          active       : bool — score > 0.15
        """
        omega_n = omega / (omega.norm() + 1e-8)

        def _mean_cosine(reference_omegas: list[torch.Tensor]) -> float:
            if not reference_omegas:
                return 0.0
            sims = []
            for ref in reference_omegas:
                cos = float(torch.dot(omega_n, ref).clamp(-1, 1))
                deg = math.degrees(math.acos(max(-1, min(1, cos))))
                if deg < sim_threshold_deg:
                    sims.append(max(0.0, cos))
            if not sims:
                return 0.0
            sims.sort(reverse=True)
            return float(sum(sims[:top_k]) / min(top_k, len(sims)))

        win_res  = _mean_cosine(self.winner_omegas())
        dead_res = _mean_cosine(self.dead_end_omegas())
        score    = win_res * (1.0 - dead_res)

        return {
            "score":       round(score,    4),
            "res_winners": round(win_res,  4),
            "res_dead":    round(dead_res, 4),
            "active":      score > 0.15,
        }

    def prior_interest_boost(
        self,
        omega: torch.Tensor,
        base_interest: float,
        boost: float = 0.30,
        penalty: float = 0.50,
        sim_threshold_deg: float = 20.0,
        forecast_context: float = -1.0,
        forecast_tolerance: float = 0.20,
    ) -> float:
        """
        Ajusta el interest de un candidato según la experiencia del grafo.

        +boost  si hay un winner cercano
        -penalty si hay un dead_end cercano — SOLO si el contexto de pronóstico
                 es similar al del momento en que se registró (|forecast_actual −
                 forecast_del_edge| < forecast_tolerance). Si el pronóstico cambió,
                 el dead-end se ignora: la misma acción puede ser correcta ahora.

        Args:
            forecast_context:  forecast_axis() actual. -1.0 = desactivar filtro
                               contextual (comportamiento clásico para dominios
                               deterministas donde el forecast no aplica).
            forecast_tolerance: diferencia máxima de forecast para aplicar penalty.
        """
        omega_n = omega / (omega.norm() + 1e-8)
        adj = 0.0
        use_ctx = forecast_context >= 0.0   # filtro contextual activo
        for e in self.edges:
            if e.strength < 0.05:
                continue
            node_to = self.nodes[e.to_idx]
            cos = float(torch.dot(omega_n, node_to.omega).clamp(-1, 1))
            deg = math.degrees(math.acos(max(-1, min(1, cos))))
            if deg >= sim_threshold_deg:
                continue
            if e.outcome == "winner":
                adj += boost * base_interest * e.strength
            elif e.outcome == "dead_end":
                if use_ctx:
                    # Penalizar solo si el contexto de pronóstico coincide
                    forecast_match = abs(e.interest_Z - forecast_context) < forecast_tolerance
                    if not forecast_match:
                        continue   # forecast cambió — ignorar este dead-end
                adj -= penalty * base_interest * e.strength
        return max(0.0, base_interest + adj)

    # ── Memoria relacional ────────────────────────────────────────────────────

    def compare_memories(
        self,
        sim_threshold_deg: float = 30.0,
    ) -> list[dict]:
        """
        Agrupa aristas en prototipos por similitud angular y detecta contradicciones.

        Un prototipo agrupa nodos destino (to_idx) que están a < sim_threshold_deg
        entre sí. Por cada prototipo calcula si fue winner y/o dead-end en distintos
        contextos de pronóstico (interest_Z guardado en el registro).

        Contradicción: el mismo prototipo tiene aristas winner Y dead-end cuyo
        contexto de pronóstico se solapa (|fc_winner - fc_dead| < 0.25).
        Si el contexto NO se solapa, es una regla: "funciona en demanda alta/baja".

        Returns lista de prototipos, cada uno con:
          omega        : centroide normalizado (promedio de omegas del grupo)
          n_winners    : número de aristas winner en el prototipo
          n_dead_ends  : número de aristas dead-end en el prototipo
          winner_fcs   : lista de forecast_contexts de winners
          dead_fcs     : lista de forecast_contexts de dead-ends
          is_contradictory : True si los contextos se solapan
          rule         : "reliable" | "avoid" | "context_dependent" | "contradictory"
          mean_strength: fuerza media de las aristas del prototipo
        """
        if not self.edges:
            return []

        # Agrupar nodos destino en clusters por similitud angular
        to_indices = list({e.to_idx for e in self.edges})
        clusters: list[list[int]] = []   # cada cluster = lista de to_idx

        for idx in to_indices:
            omega_i = self.nodes[idx].omega
            placed = False
            for cluster in clusters:
                rep = self.nodes[cluster[0]].omega
                cos = float(torch.dot(omega_i, rep).clamp(-1, 1))
                deg = math.degrees(math.acos(max(-1, min(1, cos))))
                if deg < sim_threshold_deg:
                    cluster.append(idx)
                    placed = True
                    break
            if not placed:
                clusters.append([idx])

        prototypes = []
        for cluster in clusters:
            # Centroide del prototipo
            stack = torch.stack([self.nodes[i].omega for i in cluster])
            centroid = stack.mean(dim=0)
            centroid = centroid / (centroid.norm() + 1e-8)

            # Recopilar aristas que apuntan a nodos de este cluster
            winner_edges = [e for e in self.edges
                            if e.to_idx in cluster and e.outcome == "winner"]
            dead_edges   = [e for e in self.edges
                            if e.to_idx in cluster and e.outcome == "dead_end"]

            winner_fcs = [e.interest_Z for e in winner_edges]
            dead_fcs   = [e.interest_Z for e in dead_edges]
            all_strengths = [e.strength for e in winner_edges + dead_edges]

            # Detección de contradicción: ¿los contextos se solapan?
            contradictory = False
            if winner_fcs and dead_fcs:
                mean_wfc = sum(winner_fcs) / len(winner_fcs)
                mean_dfc = sum(dead_fcs)   / len(dead_fcs)
                contradictory = abs(mean_wfc - mean_dfc) < 0.25

            if not winner_edges and not dead_edges:
                continue

            if winner_edges and not dead_edges:
                rule = "reliable"
            elif dead_edges and not winner_edges:
                rule = "avoid"
            elif contradictory:
                rule = "contradictory"
            else:
                rule = "context_dependent"

            # ── Métricas temporales ────────────────────────────────────────────
            dead_rounds   = [e.round_idx for e in dead_edges]
            winner_rounds = [e.round_idx for e in winner_edges]
            temporal_spread = (
                statistics.stdev(dead_rounds) if len(dead_rounds) >= 2 else 0.0
            )
            # Reactivación: winner cuyo round_idx supera al menos un dead-end previo
            n_reactivations = 0
            if dead_rounds and winner_rounds:
                max_dead = max(dead_rounds)
                min_dead = min(dead_rounds)
                for wr in winner_rounds:
                    if wr > min_dead:   # winner llegó DESPUÉS de un dead-end
                        n_reactivations += 1

            proto = {
                "omega":              centroid,
                "n_winners":          len(winner_edges),
                "n_dead_ends":        len(dead_edges),
                "winner_fcs":         winner_fcs,
                "dead_fcs":           dead_fcs,
                "is_contradictory":   contradictory,
                "rule":               rule,
                "mean_strength":      sum(all_strengths) / max(1, len(all_strengths)),
                # temporales
                "dead_round_indices":   dead_rounds,
                "winner_round_indices": winner_rounds,
                "temporal_spread":    temporal_spread,
                "n_reactivations":    n_reactivations,
            }
            proto["inferred_obsolescence"] = self._infer_obsolescence(proto)
            prototypes.append(proto)

        return prototypes

    @staticmethod
    def _infer_obsolescence(
        proto: dict,
        spread_threshold: float = 15.0,
        react_min: int = 1,
    ) -> str:
        """
        Infiere el tipo de obsolescencia de un prototipo a partir de su
        historia temporal, sin usar etiquetas de branch_type.

        Reglas (en orden de prioridad):

          "permanent"  — avoid + temporal_spread bajo (<threshold) + 0 reactivaciones:
                          los dead-ends están agrupados en el tiempo → es una barrera
                          que no desaparece (pared, zona bloqueada definitivamente).

          "ephemeral"  — tiene reactivaciones (≥ react_min winners posteriores a dead-ends):
                          el recurso desapareció y luego volvió → se renueva con el tiempo.

          "periodic"   — context_dependent + temporal_spread alto (≥ threshold):
                          los dead-ends están distribuidos en el tiempo de forma consistente
                          con una alternancia regular (ciclo de enemigo, clima, etc.).

          "stable"     — reliable sin dead-ends: zona que funciona consistentemente.

          "unknown"    — no hay suficiente información para inferir.
        """
        rule    = proto["rule"]
        spread  = proto["temporal_spread"]
        n_react = proto["n_reactivations"]
        n_dead  = proto["n_dead_ends"]
        n_win   = proto["n_winners"]

        # Stable: zona que funciona sin dead-ends en los registros
        if n_dead == 0 and n_win > 0:
            return "stable"

        # Ephemeral: dead-end seguido de winner posterior (el recurso se re-activó)
        if n_react >= react_min:
            return "ephemeral"

        # Permanent: avoid + dead-ends agrupados en tiempo (una sola ráfaga) + sin reactivación
        if rule == "avoid" and spread < spread_threshold and n_react == 0:
            return "permanent"

        # Periodic: dead-ends distribuidos en el tiempo (spread alto) → riesgo cíclico
        # Aplica tanto a "avoid" puro (enemigo patrullero) como a contextos mixtos (clima)
        if spread >= spread_threshold and n_react == 0:
            return "periodic"

        # Context-dependent con spread moderado: funciona en algún contexto pero no en otro
        if rule in ("context_dependent", "contradictory") and spread >= spread_threshold:
            return "periodic"

        return "unknown"

    def infer_obsolescence(
        self,
        sim_threshold_deg: float = 30.0,
        spread_threshold: float = 15.0,
        react_min: int = 1,
    ) -> list[dict]:
        """
        Versión enriquecida de compare_memories() que añade 'inferred_obsolescence'
        a cada prototipo.  Conveniente como API de alto nivel.
        """
        protos = self.compare_memories(sim_threshold_deg=sim_threshold_deg)
        for p in protos:
            p["inferred_obsolescence"] = self._infer_obsolescence(
                p, spread_threshold=spread_threshold, react_min=react_min
            )
        return protos

    def relational_boost(
        self,
        omega: torch.Tensor,
        base_interest: float,
        forecast_context: float = -1.0,
        boost: float = 0.30,
        penalty: float = 0.50,
        sim_threshold_deg: float = 30.0,
        proto_threshold_deg: float = 35.0,
    ) -> tuple[float, str]:
        """
        Versión relacional de prior_interest_boost() que usa compare_memories().

        En lugar de evaluar cada arista individual, evalúa PROTOTIPOS:
          - reliable  → boost completo
          - avoid     → penalty completa
          - context_dependent → boost/penalty según si el forecast actual
                                coincide con el contexto dominante
          - contradictory → señal ambigua → boost/penalty reducidos a 0.25×

        Returns (adjusted_interest, rule_applied).
        """
        protos = self.compare_memories(sim_threshold_deg=sim_threshold_deg)
        if not protos:
            return base_interest, "no_memory"

        omega_n = omega / (omega.norm() + 1e-8)
        adj = 0.0
        applied_rule = "no_match"

        for p in protos:
            cos = float(torch.dot(omega_n, p["omega"]).clamp(-1, 1))
            deg = math.degrees(math.acos(max(-1, min(1, cos))))
            if deg >= proto_threshold_deg:
                continue

            rule   = p["rule"]
            w      = p["mean_strength"]
            applied_rule = rule

            if rule == "reliable":
                adj += boost * base_interest * w

            elif rule == "avoid":
                adj -= penalty * base_interest * w

            elif rule == "context_dependent":
                # Determinar si el contexto actual es "demanda alta" o "baja"
                if forecast_context >= 0.0 and p["winner_fcs"] and p["dead_fcs"]:
                    mean_wfc = sum(p["winner_fcs"]) / len(p["winner_fcs"])
                    mean_dfc = sum(p["dead_fcs"])   / len(p["dead_fcs"])
                    # Si winner_fcs son más altos → funciona en alta demanda
                    if mean_wfc > mean_dfc:
                        if forecast_context >= mean_wfc - 0.1:
                            adj += boost * base_interest * w
                        else:
                            adj -= penalty * base_interest * w
                    else:
                        if forecast_context <= mean_dfc + 0.1:
                            adj += boost * base_interest * w
                        else:
                            adj -= penalty * base_interest * w
                # Sin forecast_context, ignorar
            elif rule == "contradictory":
                # Señal ambigua: reducir mucho el ajuste
                adj += 0.25 * boost * base_interest * w   # ligero boost (la red aprende más)
                adj -= 0.25 * penalty * base_interest * w  # ligera penalización → ≈ neutro

        return max(0.0, base_interest + adj), applied_rule

    # ── Resumen ───────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        n_win  = sum(1 for e in self.edges if e.outcome == "winner")
        n_dead = sum(1 for e in self.edges if e.outcome == "dead_end")
        return {
            "n_nodes":    len(self.nodes),
            "n_edges":    len(self.edges),
            "n_winners":  n_win,
            "n_dead_ends": n_dead,
            "branch_types": list({e.branch_type for e in self.edges}),
        }

    def print_history(self) -> None:
        print(f"  BifurcationGraph: {len(self.nodes)} nodos, {len(self.edges)} aristas")
        for e in self.edges:
            fn = self.nodes[e.from_idx].label or f"n{e.from_idx}"
            tn = self.nodes[e.to_idx].label   or f"n{e.to_idx}"
            icon = "✓" if e.outcome == "winner" else ("✗" if e.outcome == "dead_end" else "?")
            print(f"    R{e.round_idx:02d}  {fn} → {tn}  "
                  f"{icon} {e.branch_type:15s}  "
                  f"tension={e.tension:.4f}  intZ={e.interest_Z:.3f}  "
                  f"gap={e.gap_to_Z:.1f}°")
