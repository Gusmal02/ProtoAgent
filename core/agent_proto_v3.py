"""ProtoAgent v3: núcleo mínimo, trazable y desacoplado del dominio.

No pretende reunir todas las capacidades del proyecto.  Su contrato es:

    observar -> simular acciones legales -> decidir -> ejecutar -> reflexionar

El entorno controla qué acciones existen y cómo se simulan.  El agente controla
la memoria de bifurcaciones, la novedad del campo y una traza JSON por decisión.
Las extensiones (subconsciente, curiosidad, WorldModel y crisis lateral) se
añadirán como políticas opcionales, no como dependencias del núcleo.
"""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol

import numpy as np
import torch

from core.bifurcation_graph import BifurcationGraph
from core.field import ResonantField
from core.protoagent_v3_cognition import CognitiveConfig, CognitiveSignals
from core.protoagent_v3_world import EmpiricalWorldModel
from core.protoagent_v3_governance import CausalMemory, ExecutionGate
from core.protoagent_v3_board import MetacognitiveBoard
from core.protoagent_v3_deliberation import InternalRoleDeliberator
from core.contextual_memory import ContextualMemory
from core.action_context_memory import ActionContextMemory, arbitrate_information_actions
from core.evidence_exploration import select_underexplored
from core.bounded_public_planner import select_primitive
from core.context_memory import BufferLimbo
from memory.insert import protect_pattern
from memory.insert import insert_multi, resonance_scores_mag


class ReversibleEnvironment(Protocol):
    """Contrato mínimo que debe exponer un dominio al ProtoAgent v3."""

    def reset(self) -> np.ndarray: ...
    def observe(self) -> np.ndarray: ...
    def legal_actions(self) -> list[int]: ...
    def snapshot(self) -> Any: ...
    def restore(self, state: Any) -> None: ...
    def step(self, action: int) -> tuple[np.ndarray, float, bool, dict]: ...
    def describe(self, observation: np.ndarray) -> dict: ...


@dataclass
class ProtoAgentV3Config:
    omega_scale: float = 1.5
    w_navigation: float = 2.0
    w_resonant_interest: float = 0.35
    wall_penalty: float = 2.0
    enemy_penalty: float = 1.0
    progress_bonus: float = 0.30
    memory_boost: float = 0.30
    memory_penalty: float = 0.50
    merge_deg: float = 12.0
    gamma_active: float = 0.001
    field_exposures: int = 1
    field_settle_steps: int = 1
    lookahead_horizon: int = 1
    lookahead_discount: float = 1.0
    enable_subconscious: bool = False
    enable_curiosity: bool = False
    intuition_weight: float = 0.10
    curiosity_weight: float = 0.05
    enable_lateral: bool = False
    lateral_after_stagnation: int = 3
    operating_mode: str = "laboratory"
    use_sandbox: bool = True
    exploration_bonus: float = 0.08
    logic_weight: float = 0.0
    visited_penalty: float = 2.0
    enable_contextual_memory: bool = True
    context_weight: float = 0.15
    enable_protected_memory: bool = True
    protection_level: float = 0.85
    block_on_review: bool = False
    # Planificación causal aprendida: sólo se activa fuera del sandbox y deja
    # explícita la incertidumbre de cada transición empírica.
    enable_learned_lookahead: bool = False
    learned_horizon: int = 1
    learned_discount: float = 0.96
    learned_uncertainty_penalty: float = 1.25
    protection_confirmations: int = 2
    enable_information_actions: bool = True
    # No es un freno de seguridad: mide comodidad/estancamiento y empuja hacia
    # la frontera epistémica. La compuerta de ejecución sigue separada.
    enable_tension_thermometer: bool = True
    tension_weight: float = 0.0
    repeat_action_penalty: float = 0.0
    enable_internal_roles: bool = False
    enable_action_context_memory: bool = False
    action_context_weight: float = 2.0
    enable_action_context_arbitration: bool = False
    enable_context_coverage_guard: bool = False
    reuse_contextual_evocation: bool = True
    enable_evidence_exploration: bool = False
    evidence_exploration_after: int = 8
    enable_public_model_planning: bool = False
    enable_verified_plan_following: bool = False
    enable_verified_completion: bool = True
    enable_verified_replanning: bool = True


def _safe_float(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _safe_float(value.tolist())
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, dict):
        return {str(k): _safe_float(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_float(v) for v in value]
    return value


class ProtoAgentV3:
    """Unidad mínima de decisión resonante con auditoría por paso.

    ``encoder`` debe transformar una observación numérica en un vector omega de
    tres dimensiones.  Puede ser PCA, un encoder determinista o una capa futura
    de representación; v3 no le atribuye inteligencia al encoder.
    """

    def __init__(
        self,
        field: ResonantField,
        encoder: Callable[[np.ndarray], torch.Tensor],
        config: ProtoAgentV3Config | None = None,
    ):
        self.field = field
        self.encoder = encoder
        self.cfg = config or ProtoAgentV3Config()
        # Las barreras permanentes no decaen; la experiencia contextual sí.
        self.bg_passive = BifurcationGraph(
            merge_threshold_deg=self.cfg.merge_deg, gamma_bifgraph=0.0
        )
        self.bg_active = BifurcationGraph(
            merge_threshold_deg=self.cfg.merge_deg, gamma_bifgraph=self.cfg.gamma_active
        )
        self.trace: list[dict] = []
        self._previous_omega: torch.Tensor | None = None
        self._stagnation = 0
        self.world_model = EmpiricalWorldModel()
        self.causal_memory = CausalMemory()
        self.execution_gate = ExecutionGate(mode=self.cfg.operating_mode)
        self.board = MetacognitiveBoard()
        # La memoria activa necesita su contexto: "vacío ahora" no equivale a
        # "imposible siempre". La pasiva conserva únicamente restricciones.
        self.contextual_memory = ContextualMemory(theta_ctx=0.82, gamma_decay=self.cfg.gamma_active)
        self.action_context_memory = ActionContextMemory()
        self.limbo = BufferLimbo(ctx_threshold_deg=25.0, compat_threshold=-0.10)
        self.protected_patterns: list[list[float]] = []
        self._structural_confirmations: dict[str, int] = {}
        self._comfort_run = 0
        self._previous_action: int | None = None
        self._same_action_run = 0
        self.internal_deliberator = InternalRoleDeliberator()
        self.resonant_memory = None
        self.cognition = CognitiveSignals(field.N, self.cfg.omega_scale, CognitiveConfig(
            intuition_weight=self.cfg.intuition_weight,
            curiosity_weight=self.cfg.curiosity_weight,
            enable_subconscious=self.cfg.enable_subconscious,
            enable_curiosity=self.cfg.enable_curiosity,
        ))

    def encode(self, observation: np.ndarray) -> torch.Tensor:
        omega = self.encoder(np.asarray(observation, dtype=np.float32))
        if not isinstance(omega, torch.Tensor):
            omega = torch.tensor(omega, dtype=torch.float32)
        omega = omega.detach().float().flatten()
        if omega.numel() != 3:
            raise ValueError("ProtoAgentV3 necesita un encoder que produzca omega de 3 dimensiones.")
        return omega / (omega.norm() + 1e-8) * self.cfg.omega_scale

    def _novelty(self, omega: torch.Tensor) -> float:
        # Usar la variante sensible a magnitud: el olvido del campo debe poder
        # elevar novelty aunque una dirección residual siga coincidiendo.
        scores = resonance_scores_mag(
            self.field.omega, omega, omega_scale=self.cfg.omega_scale
        )
        return float((1.0 - scores.clamp(min=-1.0, max=1.0).max()).clamp(min=0.0))

    @staticmethod
    def _context(env: ReversibleEnvironment) -> tuple[torch.Tensor, float]:
        """Obtiene contexto observable; nunca consulta resultados futuros."""
        if hasattr(env, "context_vector"):
            vector = torch.as_tensor(env.context_vector(), dtype=torch.float32).flatten()
            if vector.numel() >= 3:
                vector = vector[:3]
            else:
                vector = torch.cat([vector, torch.zeros(3 - vector.numel())])
        else:
            vector = torch.tensor([0.0, 0.0, 1.0])
        vector = vector / (vector.norm() + 1e-8)
        scalar = float(env.forecast_context()) if hasattr(env, "forecast_context") else -1.0
        return vector, scalar

    def _contextual_adjustment(self, omega: torch.Tensor, context: torch.Tensor, evoked=None) -> float:
        """Prior local: mismo contexto y misma consecuencia, no una regla global."""
        if not self.cfg.enable_contextual_memory:
            return 0.0
        adjustment = 0.0
        for trace, ctx_sim in (self.contextual_memory.evoke(context) if evoked is None else evoked):
            similarity = float(torch.dot(
                omega / (omega.norm() + 1e-8),
                trace.omega / (trace.omega.norm() + 1e-8),
            ).clamp(-1, 1))
            direction = 1.0 if trace.label == "winner" else -1.0
            adjustment += direction * max(0.0, similarity) * ctx_sim * trace.strength
        return self.cfg.context_weight * adjustment

    @staticmethod
    def _outcome(evidence: dict, reward: float) -> tuple[str, str]:
        if evidence.get("hit_wall"):
            return "dead_end", "wall"
        if evidence.get("hit_enemy"):
            return "dead_end", "enemy"
        if evidence.get("resource") == "empty":
            return "dead_end", "resource_empty"
        if evidence.get("at_goal"):
            return "winner", "goal"
        if evidence.get("resource") == "full" or reward > 0:
            return "winner", "progress"
        return "unresolved", "neutral"

    def _simulate(self, env: ReversibleEnvironment, action: int) -> dict:
        state = env.snapshot()
        try:
            observation, reward, terminal, evidence = env.step(action)
            return {
                "observation": np.asarray(observation, dtype=np.float32).copy(),
                "reward": float(reward),
                "terminal": bool(terminal),
                "evidence": copy.deepcopy(evidence),
            }
        finally:
            env.restore(state)

    def _best_future_return(self, env: ReversibleEnvironment, remaining: int) -> float:
        """Retorno óptimo de un árbol pequeño, sin contaminar el entorno real.

        No es un planificador general ni un WorldModel aprendido: explora el
        sandbox reversible que el dominio entregó. Su única función en v3 es
        impedir que el valor del primer paso oculte una consecuencia inmediata.
        """
        if remaining <= 0:
            # Valor terminal transparente: distancia visible a la meta. No es
            # una respuesta futura del entorno; sólo evita que el horizonte
            # corto premie quedarse inmóvil para no pagar ningún movimiento.
            state = env.observe()
            return float(env.model_terminal_value(state)) if hasattr(env, "model_terminal_value") else 0.0
        actions = env.legal_actions()
        if not actions:
            return 0.0
        root = env.snapshot()
        values: list[float] = []
        try:
            for action in actions:
                _, reward, terminal, _ = env.step(action)
                future = 0.0 if terminal else self._best_future_return(env, remaining - 1)
                values.append(float(reward) + self.cfg.lookahead_discount * future)
                env.restore(root)
        finally:
            env.restore(root)
        return max(values)

    def _simulate_horizon(self, env: ReversibleEnvironment, action: int) -> dict:
        """Predice una acción y el mejor desenlace alcanzable en su horizonte."""
        state = env.snapshot()
        try:
            observation, reward, terminal, evidence = env.step(action)
            state_key = env.state_key() if hasattr(env, "state_key") else None
            future = 0.0 if terminal else self._best_future_return(
                env, max(0, self.cfg.lookahead_horizon - 1)
            )
            return {
                "observation": np.asarray(observation, dtype=np.float32).copy(),
                "reward": float(reward),
                "terminal": bool(terminal),
                "evidence": copy.deepcopy(evidence),
                "rollout_return": float(reward) + self.cfg.lookahead_discount * future,
                "horizon": int(self.cfg.lookahead_horizon),
                "state_key": state_key,
            }
        finally:
            env.restore(state)

    def _learned_future_return(
        self, env: ReversibleEnvironment, state: np.ndarray, remaining: int,
        memo: dict[tuple[tuple[float, ...], int], float] | None = None,
    ) -> float:
        """Busca sobre transiciones observadas, nunca sobre el entorno real.

        Cada rama paga por incertidumbre. Por diseño, una secuencia no puede
        parecer atractiva sólo porque el modelo no tiene evidencia de ella.
        """
        if remaining <= 0:
            return 0.0
        memo = {} if memo is None else memo
        key = (tuple(np.round(np.asarray(state, dtype=np.float32), 3).tolist()), remaining)
        if key in memo:
            return memo[key]
        actions = (env.model_legal_actions(state) if hasattr(env, "model_legal_actions")
                   else env.legal_actions())
        proposals: list[tuple[float, dict]] = []
        current_value = float(env.model_terminal_value(state)) if hasattr(env, "model_terminal_value") else 0.0
        for action in actions:
            p = self.world_model.predict(state, int(action))
            if not p["known"]:
                continue
            immediate = p["reward"] - self.cfg.learned_uncertainty_penalty * p["uncertainty"]
            next_value = float(env.model_terminal_value(p["raw_next_state"])) if hasattr(env, "model_terminal_value") else 0.0
            # Haz de planificación: mantiene la alternativa que progresa y la
            # alternativa temporal (p.ej. esperar). No expande todo el árbol.
            info_value = (float(env.model_action_priority(state, int(action)))
                          if self.cfg.enable_information_actions and hasattr(env, "model_action_priority") else 0.0)
            proposals.append((immediate + 0.5 * (next_value - current_value) + info_value, p))
        values: list[float] = []
        for immediate_rank, p in sorted(proposals, key=lambda pair: pair[0], reverse=True)[:2]:
            immediate = p["reward"] - self.cfg.learned_uncertainty_penalty * p["uncertainty"]
            terminal = p.get("terminal_probability", 0.0) >= 0.5
            future = 0.0 if terminal else self._learned_future_return(
                env, p["raw_next_state"], remaining - 1, memo
            )
            values.append(immediate + self.cfg.learned_discount * future)
        memo[key] = max(values) if values else 0.0
        return memo[key]

    def _learned_prediction(self, env: ReversibleEnvironment, action: int) -> dict:
        state = np.asarray(env.observe(), dtype=np.float32)
        p = self.world_model.predict(state, action)
        if not p["known"]:
            return {
                "observation": state.copy(), "reward": 0.0, "terminal": False,
                "evidence": {"model_only": True, "known": False}, "rollout_return": 0.0,
                "horizon": 0, "state_key": None, "uncertainty": 1.0,
            }
        terminal = p.get("terminal_probability", 0.0) >= 0.5
        future = 0.0 if terminal else self._learned_future_return(
            env, p["raw_next_state"], max(0, self.cfg.learned_horizon - 1), {}
        )
        return {
            "observation": p["raw_next_state"].copy(), "reward": float(p["reward"]),
            "terminal": terminal,
            "evidence": {"model_only": True, "known": True,
                         "support": p["support"], "transition_uncertainty": p["uncertainty"],
                         "terminal_probability": p.get("terminal_probability", 0.0)},
            "rollout_return": float(p["reward"] + self.cfg.learned_discount * future),
            "horizon": int(self.cfg.learned_horizon), "state_key": None,
            "uncertainty": float(p["uncertainty"]),
        }

    def _candidate(self, env: ReversibleEnvironment, action: int, current_omega: torch.Tensor,
                   contextual_cache=None) -> dict:
        context, forecast_context = self._context(env)
        if self.cfg.use_sandbox:
            prediction = self._simulate_horizon(env, action)
        else:
            prediction = (self._learned_prediction(env, action)
                          if self.cfg.enable_learned_lookahead else None)
            if prediction is None:
                empirical = self.world_model.predict(env.observe(), action)
                prediction = {
                    "observation": np.asarray(env.observe(), dtype=np.float32).copy(),
                    "reward": empirical["reward"], "terminal": False,
                    "evidence": {"model_only": True}, "rollout_return": empirical["reward"],
                    "horizon": 0, "state_key": None,
                }
        omega = self.encode(prediction["observation"])
        novelty = self._novelty(omega)
        # La novedad extrema y el conocimiento total tienen poco interest:
        # la zona útil es la frontera parcialmente reconocida.
        interest = novelty * (1.0 - novelty)
        evidence = prediction["evidence"]
        reward = prediction["reward"]
        base = self.cfg.w_navigation * prediction["rollout_return"] + self.cfg.w_resonant_interest * interest
        logic_score = float(env.deterministic_score(action)) if hasattr(env, "deterministic_score") else 0.0
        base += self.cfg.logic_weight * logic_score
        if prediction.get("state_key") is not None and repr(prediction["state_key"]) in self.board.visited:
            base -= self.cfg.visited_penalty
        if not self.cfg.use_sandbox:
            support = self.world_model.predict(env.observe(), action)["support"]
            base += self.cfg.exploration_bonus / (1 + support)
        if evidence.get("hit_wall"):
            base -= self.cfg.wall_penalty
        if evidence.get("hit_enemy"):
            base -= self.cfg.enemy_penalty

        cognitive = self.cognition.candidate_signals(self.field, omega)
        base += cognitive["adjustment"]

        # El grafo permanente es una prohibición duradera; el activo admite
        # reactivación y contexto en versiones posteriores.
        passive = self.bg_passive.prior_interest_boost(
            omega, max(base, 0.0), boost=self.cfg.memory_boost,
            penalty=self.cfg.memory_penalty,
        )
        active = self.bg_active.prior_interest_boost(
            omega, max(passive, 0.0), boost=self.cfg.memory_boost,
            penalty=self.cfg.memory_penalty,
            forecast_context=forecast_context,
        )
        score = active if base >= 0 else base
        if contextual_cache is None:
            contextual_adjustment = self._contextual_adjustment(omega, context)
        else:
            context_key=tuple(context.tolist())
            key=(tuple(omega.tolist()),context_key)
            if key in contextual_cache["adjustments"]:
                contextual_adjustment=contextual_cache["adjustments"][key]
                contextual_cache["hits"]+=1
            else:
                if context_key not in contextual_cache["evoked"]:
                    contextual_cache["evoked"][context_key]=self.contextual_memory.evoke(context)
                contextual_adjustment=self._contextual_adjustment(
                    omega,context,contextual_cache["evoked"][context_key])
                contextual_cache["adjustments"][key]=contextual_adjustment
                contextual_cache["computations"]+=1
        score += contextual_adjustment
        action_context = (self.action_context_memory.predict(context.tolist(), action)
                          if self.cfg.enable_action_context_memory else
                          {"support": 0, "value": 0.0, "abstained": True, "evidence_ids": []})
        action_context_adjustment = self.cfg.action_context_weight * action_context["value"]
        score += action_context_adjustment
        outcome, reason = self._outcome(evidence, reward)
        return {
            "action": int(action),
            "omega": omega,
            "prediction": prediction,
            "novelty": novelty,
            "interest": interest,
            "base_score": base,
            "score": score,
            "predicted_outcome": outcome,
            "predicted_reason": reason,
            "cognitive": cognitive,
            "logic_score": logic_score,
            "contextual_adjustment": contextual_adjustment,
            "action_context": action_context,
            "action_context_adjustment": action_context_adjustment,
        }

    def _remember(
        self,
        omega_from: torch.Tensor,
        omega_to: torch.Tensor,
        outcome: str,
        reason: str,
        reward: float,
        step_idx: int,
        forecast_context: float = -1.0,
        action: int | None = None,
        predicted_reward: float | None = None,
        prediction_error: float | None = None,
        duration: int = 1,
    ) -> str:
        graph = self.bg_passive if reason == "wall" else self.bg_active
        graph_outcome = "unexplored" if outcome == "unresolved" else outcome
        graph.add_bifurcation(
            omega_from=omega_from,
            omega_to=omega_to,
            tension=float(abs(reward)),
            outcome=graph_outcome,
            branch_type=reason,
            interest_Z=float(forecast_context if forecast_context >= 0.0 else reward),
            gap_to_Z=0.0,
            round_idx=step_idx,
            action=action, predicted_reward=predicted_reward,
            observed_reward=reward, prediction_error=prediction_error,
            duration=duration, context=forecast_context,
        )
        return "passive" if graph is self.bg_passive else "active"

    def _learn_field(self, omega: torch.Tensor) -> None:
        direction = omega / (omega.norm() + 1e-8)
        insert_multi(
            self.field, direction, n_expose=self.cfg.field_exposures,
            omega_scale=self.cfg.omega_scale, alpha_learn=0.05, top_k=3,
        )
        for _ in range(self.cfg.field_settle_steps):
            self.field.step()

    def step(self, env: ReversibleEnvironment, step_idx: int) -> dict:
        raw_observation = np.asarray(env.observe(), dtype=np.float32)
        context_before, forecast_context = self._context(env)
        observation = env.describe(raw_observation)
        current_state = env.state_key() if hasattr(env, "state_key") else tuple(np.round(raw_observation, 4))
        repeated_current = self.board.enter(current_state)
        omega_before = self.encode(raw_observation)
        legal = env.legal_actions()
        if not legal:
            raise RuntimeError("El entorno no ofreció acciones legales.")
        # Cache exists only during candidate evaluation, before learning/forgetting.
        # No state survives into another decision or across a memory update.
        contextual_cache=({"evoked":{},"adjustments":{},"hits":0,"computations":0}
                          if self.cfg.reuse_contextual_evocation else None)
        candidates = [self._candidate(env, action, omega_before, contextual_cache) for action in legal]
        for candidate in candidates:
            candidate["empirical_world"] = self.world_model.predict(raw_observation, candidate["action"])
            candidate["raw_empirical_world"] = candidate["empirical_world"].copy()
            if (self.cfg.enable_context_coverage_guard and self.cfg.enable_action_context_memory
                    and candidate["action_context"]["abstained"]):
                candidate["empirical_world"] = dict(candidate["empirical_world"],
                                                    support=0, uncertainty=1.0, reward=0.0)
            empirical = candidate["empirical_world"]
        mean_novelty = float(np.mean([c["novelty"] for c in candidates]))
        mean_support = float(np.mean([c["empirical_world"]["support"] for c in candidates]))
        comfort_event = repeated_current or (mean_novelty < .12 and mean_support >= 3.0)
        self._comfort_run = self._comfort_run + 1 if comfort_event else 0
        tension = min(1.0, .18 * self._comfort_run + (.25 if repeated_current else 0.0)
                      + (.20 if mean_novelty < .12 else 0.0))
        thermometer = {
            "comfort_run": self._comfort_run, "mean_novelty": mean_novelty,
            "mean_support": mean_support, "tension": tension,
            "zone": "hot" if tension >= .65 else ("warming" if tension >= .35 else "cool"),
            "cause": "repetition_or_overfamiliarity" if comfort_event else "frontier_or_change",
        }
        for candidate in candidates:
            empirical = candidate["empirical_world"]
            # La salida de confort privilegia frontera, escasez de evidencia e
            # interés epistémico. No altera permisos ni vuelve segura una acción.
            escape = min(1.0, candidate["novelty"] + 1.0 / (1.0 + empirical["support"])
                         + float(candidate["cognitive"]["epistemic"]["valor_epistemico"]))
            candidate["tension_escape"] = escape
            candidate["score"] += (self.cfg.tension_weight * tension * escape
                                   if self.cfg.enable_tension_thermometer else 0.0)
            if candidate["action"] == self._previous_action:
                candidate["score"] -= self.cfg.repeat_action_penalty * tension * self._same_action_run
        deliberation = None
        if self.cfg.enable_internal_roles:
            deliberation = self.internal_deliberator.decide(
                candidates, thermometer, self._previous_action, self._same_action_run
            )
        candidates.sort(key=lambda c: c["score"], reverse=True)
        chosen = (next(c for c in candidates if c["action"] == deliberation.chosen_action)
                  if deliberation is not None else candidates[0])
        evidence_arbitration = None
        if (self.cfg.enable_action_context_arbitration and self.cfg.enable_action_context_memory
                and hasattr(env, "is_information_action")
                and all(env.is_information_action(c["action"]) for c in candidates)):
            chosen, evidence_arbitration = arbitrate_information_actions(
                candidates, systematic_unknown=self.cfg.enable_context_coverage_guard)
        exploration_audit = {"triggered": False, "cause": "disabled"}
        if getattr(self.cfg, "enable_evidence_exploration", False):
            attempts = getattr(self, "_actual_action_attempts", {})
            alternative, exploration_audit = select_underexplored(
                candidates, attempts, self._stagnation,
                after=self.cfg.evidence_exploration_after,
                choose_index=lambda n: int(np.random.randint(n)),
                no_change_evidence=getattr(self,"_no_change_evidence",{}),
            )
            if alternative is not None:
                chosen = alternative
        planning_audit = {"enabled":False}
        if getattr(self.cfg,"enable_public_model_planning",False):
            if not hasattr(env,"planning_problem") or not hasattr(env,"planning_transition"):
                planning_audit={"enabled":True,"capability_missing":True}
            else:
                try:
                    problem=env.planning_problem()
                    if problem is None:raise ValueError("planning capability missing")
                    action, cache, planning_audit = select_primitive(
                        problem, env.planning_transition,
                        getattr(self,"_public_plan",None))
                    self._public_plan=cache
                    if action is not None:
                        chosen=next(c for c in candidates if c["action"]==action)
                except (RuntimeError,ValueError) as exc:
                    self._public_plan=None
                    planning_audit={"enabled":True,"planning_failed":str(exc)}
        if getattr(self.cfg,'enable_verified_plan_following',False) and hasattr(env,'following_plan'):
            advice=env.following_plan()
            if advice and advice.get('action') in legal:
                chosen=next(c for c in candidates if c['action']==advice['action'])
                planning_audit={'source':'verified_public_probe','proof_receipt':advice['proof_receipt'],'goal_scope':advice['goal_scope']}
        replan_audit={'offered':0,'selected':False}
        if getattr(self.cfg,'enable_verified_replanning',False) and hasattr(env,'verified_replans'):
            valid=[]
            for offer in env.verified_replans():
                import hashlib,json
                action=offer.get('action')
                if action not in legal:continue
                request=env.request_binding(action)
                digest=hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
                if offer.get('request_hash')==digest and offer.get('entity')==request.get('entity') and offer.get('revision')==request.get('revision') and offer.get('artifact_hash') and offer.get('evidence_hashes') and offer.get('goal_scope'):valid.append(offer)
            if valid:
                eligible={offer['action']:offer for offer in valid}
                chosen=next(c for c in candidates if c['action'] in eligible)
                replan_audit={'offered':len(valid),'selected':True,'source':'trusted_provider_evidence_obligation_policy','proof':eligible[chosen['action']],'execution_authority':False}
        completion_audit = {'offered':0,'selected':False}
        if getattr(self.cfg,'enable_verified_completion',False) and hasattr(env,'verified_completions'):
            offers=env.verified_completions()
            valid=[]
            for offer in offers:
                # Public trusted-provider offers, bound to the frozen request.
                # They never bypass the CURRENT native gate or prove an effect.
                import hashlib,json
                action=offer.get('action')
                if action not in legal:continue
                request=env.request_binding(action)
                digest=hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
                if (offer.get('request_hash')==digest and offer.get('entity')==request.get('entity')
                        and offer.get('revision')==request.get('revision')
                        and offer.get('goal_scope') and offer.get('evidence_hashes')):
                    valid.append(offer)
            completion_audit['offered']=len(valid)
            if valid:
                eligible={offer['action']:offer for offer in valid}
                chosen=next(c for c in candidates if c['action'] in eligible)
                completion_audit={'offered':len(valid),'selected':True,'source':'trusted_provider_completion',
                                  'proof':eligible[chosen['action']],'execution_authority':False}
        authorization = self.execution_gate.assess(
            chosen["empirical_world"],
            harmful=chosen["predicted_outcome"] == "dead_end",
        )

        # El modo seguro convierte una recomendación incierta en abstención
        # real. Por compatibilidad, el laboratorio exploratorio conserva el
        # comportamiento anterior salvo que lo solicite explícitamente.
        if self.cfg.block_on_review and authorization["decision"] != "allow":
            record = {
                "verified_completion": completion_audit,
                "verified_replanning": replan_audit,
                "episode_step": step_idx,
                "evidence_arbitration": evidence_arbitration,
                "observation": _safe_float(observation),
                "omega_before": _safe_float(omega_before),
                "legal_actions": list(legal),
                "candidates": [{
                    "action": c["action"], "score": round(c["score"], 6),
                    "base_score": round(c["base_score"], 6),
                    "novelty": round(c["novelty"], 6),
                    "empirical_world": _safe_float(c["empirical_world"]),
                    "tension_escape": round(float(c["tension_escape"]), 6),
                } for c in candidates],
                "chosen_action": chosen["action"],
                "actual_reward": None, "actual_terminal": False,
                "outcome": "abstained", "reason": authorization["reason"],
                "authorization": authorization, "board_diagnosis": "ignorance",
                "forecast_context": forecast_context, "execution_abstained": True,
                "thermometer": thermometer,
                "internal_deliberation": None if deliberation is None else {
                    "explorer_spawned": deliberation.explorer_spawned,
                    "reason": deliberation.reason, "dissent": deliberation.dissent,
                },
            }
            self.trace.append(record)
            return record

        actual_obs, reward, terminal, evidence = env.step(chosen["action"])
        omega_after = self.encode(actual_obs)
        outcome, reason = self._outcome(evidence, reward)
        preliminary_error = abs(float(chosen["prediction"]["reward"]) - float(reward))
        memory_graph = self._remember(
            omega_before, omega_after, outcome, reason, reward, step_idx, forecast_context,
            action=chosen["action"], predicted_reward=float(chosen["prediction"]["reward"]),
            prediction_error=preliminary_error, duration=int(evidence.get("duration", 1)),
        )
        self._learn_field(omega_after)
        if self.cfg.enable_contextual_memory and reason != "wall":
            label = "winner" if outcome == "winner" else "dead_end"
            self.contextual_memory.add(omega_after, context_before, step_idx, label=label)
        if outcome == "dead_end" and reason != "wall":
            self.limbo.add_dead(omega_after, context_before, label=reason, domain=type(env).__name__)
        revivable = self.limbo.check_revival(context_before) if self.cfg.enable_contextual_memory else []
        # La protección es para conocimiento estructural ya confirmado: meta
        # alcanzada, no para una estación que podría estar vacía mañana.
        protected = []
        structural_key = reason if reason in {"goal", "wall"} else None
        if structural_key:
            self._structural_confirmations[structural_key] = self._structural_confirmations.get(structural_key, 0) + 1
        if (self.cfg.enable_protected_memory and outcome == "winner" and reason == "goal"
                and self._structural_confirmations.get("goal", 0) >= self.cfg.protection_confirmations):
            protected = protect_pattern(self.field, omega_after, self.cfg.omega_scale,
                                        protection=self.cfg.protection_level)
            self.protected_patterns.append(_safe_float(omega_after))
        self.cognition.learn(omega_after)
        prediction_error = self.cognition.calibrate(chosen["prediction"]["reward"], reward)
        deliberation_audit = (self.internal_deliberator.audit(
            deliberation, self._previous_action, evidence, prediction_error
        ) if deliberation is not None else None)
        self.world_model.observe(raw_observation, chosen["action"], reward, actual_obs, terminal)
        if self.cfg.enable_action_context_memory:
            self.action_context_memory.observe(
                context_before.tolist(), chosen["action"], reward,
                evidence.get("evidence_id", ""), step_idx,
                verified=evidence.get("verified_probe") is True,
            )
        self.causal_memory.add(
            condition=observation, action=chosen["action"],
            consequence={"reward": float(reward), "outcome": outcome, "reason": reason,
                         "duration": int(evidence.get("duration", 1)), "forecast_context": forecast_context,
                         "predicted_reward": float(chosen["prediction"]["reward"]),
                         "prediction_error": prediction_error},
            confidence=max(0.0, 1.0 - float(chosen["empirical_world"]["uncertainty"])),
            evidence=_safe_float(evidence), step=step_idx,
        )
        confidence = max(0.0, 1.0 - float(chosen["empirical_world"]["uncertainty"]))
        diagnosis = self.board.record(current_state, chosen["action"], outcome, reward,
                                      confidence, prediction_error, repeated_current, step_idx)
        self._stagnation = self._stagnation + 1 if reward <= 0 else 0
        self._same_action_run = self._same_action_run + 1 if chosen["action"] == self._previous_action else 1
        self._previous_action = chosen["action"]
        if getattr(self.cfg, "enable_evidence_exploration", False):
            attempts = getattr(self, "_actual_action_attempts", {})
            attempts[chosen["action"]] = attempts.get(chosen["action"], 0) + 1
            self._actual_action_attempts = attempts
            no_change=getattr(self,"_no_change_evidence",{})
            if np.array_equal(raw_observation,actual_obs):
                no_change[chosen["action"]]=no_change.get(chosen["action"],0)+1
            else:
                no_change[chosen["action"]]=0
            self._no_change_evidence=no_change
        lateral = None
        if (self.cfg.enable_lateral
                and self._stagnation >= self.cfg.lateral_after_stagnation
                and len(candidates) >= 2):
            # La crisis produce una hipótesis geométrica; no ejecuta una acción.
            # Es un mecanismo de salida de atractor, no un permiso de autonomía.
            try:
                from core.creative_crisis import creative_crisis
                proposal = creative_crisis(
                    self.field, candidates[0]["omega"], candidates[1]["omega"],
                    omega_scale=self.cfg.omega_scale, n_tension_steps=4,
                    steps_between=2, T_settle=1,
                )
                lateral = {
                    "triggered": True,
                    "accepted": bool(proposal["accepted"]),
                    "n_tension_nodes": int(proposal["n_tension_nodes"]),
                    "proposal_omega": _safe_float(proposal["c_emergent"]),
                }
            except (RuntimeError, ValueError) as exc:
                lateral = {"triggered": True, "error": type(exc).__name__}
            self._stagnation = 0
        self.bg_active.decay_step()

        record = {
            "public_model_planning": planning_audit,
            "verified_completion": completion_audit,
            "verified_replanning": replan_audit,
            "evidence_exploration": exploration_audit,
            "episode_step": step_idx,
            "contextual_cache": None if contextual_cache is None else {
                "hits":contextual_cache["hits"],"computations":contextual_cache["computations"]},
            "evidence_arbitration": evidence_arbitration,
            "observation": _safe_float(observation),
            "omega_before": _safe_float(omega_before),
            "legal_actions": list(legal),
            "candidates": [{
                "action": c["action"], "score": round(c["score"], 6),
                "base_score": round(c["base_score"], 6), "novelty": round(c["novelty"], 6),
                "interest": round(c["interest"], 6),
                "predicted_reward": round(c["prediction"]["reward"], 6),
                "predicted_rollout_return": round(c["prediction"]["rollout_return"], 6),
                "lookahead_horizon": c["prediction"]["horizon"],
                "predicted_terminal": c["prediction"]["terminal"],
                "predicted_evidence": _safe_float(c["prediction"]["evidence"]),
                "predicted_outcome": c["predicted_outcome"],
                "intuition_score": round(float(c["cognitive"]["intuition"]["intuition_score"]), 6),
                "epistemic_value": round(float(c["cognitive"]["epistemic"]["valor_epistemico"]), 6),
                "empirical_world": _safe_float(c["empirical_world"]),
                "raw_empirical_world": _safe_float(c["raw_empirical_world"]),
                "tension_escape": round(float(c["tension_escape"]), 6),
                "logic_score": round(float(c["logic_score"]), 6),
                "contextual_adjustment": round(float(c["contextual_adjustment"]), 6),
                "action_context": c["action_context"],
                "action_context_adjustment": round(float(c["action_context_adjustment"]), 6),
            } for c in candidates],
            "chosen_action": chosen["action"],
            "actual_reward": float(reward),
            "actual_terminal": bool(terminal),
            "actual_evidence": _safe_float(evidence),
            "outcome": outcome,
            "reason": reason,
            "memory_graph": memory_graph,
            "omega_after": _safe_float(omega_after),
            "world_prediction_error": prediction_error,
            "lateral_proposal": lateral,
            "authorization": authorization,
            "board_diagnosis": diagnosis,
            "forecast_context": forecast_context,
            "limbo_revivable": len(revivable),
            "protected_nodes": protected,
            "thermometer": thermometer,
            "internal_deliberation": None if deliberation is None else {
                "explorer_spawned": deliberation.explorer_spawned,
                "reason": deliberation.reason, "planner_action": deliberation.planner_action,
                "explorer_action": deliberation.explorer_action,
                "mediator_action": deliberation.mediator_action, "dissent": deliberation.dissent,
                "audit": deliberation_audit,
            },
        }
        self.trace.append(record)
        self._previous_omega = omega_after
        return record

    def export_trace(self) -> list[dict]:
        """Devuelve una copia serializable para JSON; no oculta decisiones descartadas."""
        return copy.deepcopy(self.trace)

    def attach_resonant_memory(self, memory: Any) -> None:
        """Attach the optional D74 evidence/bridge extension without changing policy.

        The extension is intentionally queried by a domain contract rather than
        silently changing action scores from lexical similarity.
        """
        self.resonant_memory = memory

    def resonant_query(self, question: str, k: int = 5) -> dict:
        if self.resonant_memory is None:
            return {"decision": "abstain", "reason": "resonant_memory_not_attached", "hits": []}
        return self.resonant_memory.query(question, k=k)

    def export_memory_capsules(self, include_contextual: bool = False) -> list[dict]:
        """Exporta experiencia con su alcance, no sólo con su valencia.

        Una pared es una restricción estructural y puede acompañar al agente a
        un entorno análogo. Un recurso agotado o una patrulla sólo describen el
        estado de un episodio: por defecto se conservan locales. Esta frontera
        evita convertir un ``dead_end`` contextual en una prohibición global.
        """
        capsules: list[dict] = []
        sources = (("passive", self.bg_passive),)
        if include_contextual:
            sources += (("active", self.bg_active),)
        for scope, graph in sources:
            for edge in graph.edges:
                capsules.append({
                    "scope": scope,
                    "omega_from": _safe_float(graph.nodes[edge.from_idx].omega),
                    "omega_to": _safe_float(graph.nodes[edge.to_idx].omega),
                    "tension": float(edge.tension),
                    "outcome": edge.outcome,
                    "branch_type": edge.branch_type,
                    "interest_Z": float(edge.interest_Z),
                    "gap_to_Z": float(edge.gap_to_Z),
                    "round_idx": int(edge.round_idx),
                    "strength": float(edge.strength),
                    "action": edge.action,
                    "predicted_reward": edge.predicted_reward,
                    "observed_reward": edge.observed_reward,
                    "prediction_error": edge.prediction_error,
                    "duration": int(edge.duration),
                    "context": float(edge.context),
                })
        return capsules

    def import_memory_capsules(self, capsules: list[dict], include_contextual: bool = False) -> dict:
        """Importa cápsulas compatibles y devuelve una auditoría de lo rechazado.

        La política conservadora es deliberada: ``scope=active`` se rechaza a
        menos que el llamador lo autorice explícitamente tras verificar el
        contexto del dominio destino.
        """
        imported, rejected = [], []
        for capsule in capsules:
            scope = capsule.get("scope")
            if scope not in ("passive", "active"):
                rejected.append({"reason": "unknown_scope", "capsule": capsule})
                continue
            if scope == "active" and not include_contextual:
                rejected.append({"reason": "contextual_by_default", "capsule": capsule})
                continue
            try:
                graph = self.bg_passive if scope == "passive" else self.bg_active
                graph.add_bifurcation(
                    omega_from=torch.tensor(capsule["omega_from"], dtype=torch.float32),
                    omega_to=torch.tensor(capsule["omega_to"], dtype=torch.float32),
                    tension=float(capsule["tension"]),
                    outcome=str(capsule["outcome"]),
                    branch_type=str(capsule["branch_type"]),
                    interest_Z=float(capsule.get("interest_Z", 0.0)),
                    gap_to_Z=float(capsule.get("gap_to_Z", 0.0)),
                    round_idx=int(capsule.get("round_idx", 0)),
                    action=capsule.get("action"),
                    predicted_reward=capsule.get("predicted_reward"),
                    observed_reward=capsule.get("observed_reward"),
                    prediction_error=capsule.get("prediction_error"),
                    duration=int(capsule.get("duration", 1)),
                    context=float(capsule.get("context", -1.0)),
                )
                graph.edges[-1].strength = float(capsule.get("strength", 1.0))
                imported.append({"scope": scope, "branch_type": capsule["branch_type"]})
            except (KeyError, TypeError, ValueError, AssertionError) as exc:
                rejected.append({"reason": f"invalid_capsule:{type(exc).__name__}", "capsule": capsule})
        return {"imported": imported, "rejected": rejected}

    def memory_summary(self) -> dict:
        return {
            "passive": self.bg_passive.summary(),
            "active": self.bg_active.summary(),
            "cognition": self.cognition.summary(),
            "world_model": self.world_model.summary(),
            "causal_records": len(self.causal_memory.records),
            "board": self.board.summary(),
            "contextual_memory": self.contextual_memory.summary(),
            "limbo": self.limbo.summary(),
            "protected_patterns": len(self.protected_patterns),
        }
