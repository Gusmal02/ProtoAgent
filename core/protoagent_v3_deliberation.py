"""Deliberación interna temporal para ProtoAgent v3.

No son agentes independientes ni una afirmación de conciencia: son tres
lecturas auditables de los mismos candidatos. El explorador sólo existe cuando
la tensión indica que la política actual está atrapada en familiaridad.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InternalDeliberation:
    chosen_action: int
    explorer_spawned: bool
    reason: str
    planner_action: int
    explorer_action: int | None
    mediator_action: int
    dissent: bool
    scores: dict


class InternalRoleDeliberator:
    def __init__(self, hot_threshold: float = .45):
        self.hot_threshold = hot_threshold

    def decide(self, candidates: list[dict], thermometer: dict,
               previous_action: int | None, same_action_run: int) -> InternalDeliberation:
        planner = max(candidates, key=lambda c: c["base_score"] + .35*c["logic_score"])
        hot = thermometer["tension"] >= self.hot_threshold
        explorer = None
        if hot:
            explorer = max(candidates, key=lambda c: c["score"] + .65*c["tension_escape"])
        mediator_scores = {}
        for c in candidates:
            value = .65*c["score"] + .35*(c["base_score"] + .35*c["logic_score"])
            if explorer is not None:
                value += .45*c["tension_escape"]
            if hot and c["action"] == previous_action:
                value -= .70*same_action_run
            mediator_scores[c["action"]] = float(value)
        mediator_action = max(mediator_scores, key=mediator_scores.get)
        reason = ("escape_repetition" if hot and mediator_action != previous_action
                  else ("explore_frontier" if hot else "stable_plan"))
        return InternalDeliberation(
            chosen_action=int(mediator_action), explorer_spawned=hot, reason=reason,
            planner_action=int(planner["action"]),
            explorer_action=None if explorer is None else int(explorer["action"]),
            mediator_action=int(mediator_action),
            dissent=len({int(planner["action"]), int(mediator_action),
                         -1 if explorer is None else int(explorer["action"])}) > 1,
            scores=mediator_scores,
        )

    @staticmethod
    def audit(deliberation: InternalDeliberation, previous_action: int | None,
              evidence: dict, prediction_error: float) -> dict:
        """Comprueba una afirmación operacional, no una intención subjetiva."""
        repeated = deliberation.chosen_action == previous_action
        if deliberation.reason == "escape_repetition":
            consistent = not repeated
        elif deliberation.reason == "explore_frontier":
            consistent = deliberation.explorer_spawned
        else:
            consistent = True
        return {
            "claim": deliberation.reason,
            "action_consistent": consistent,
            "rationalization_mismatch": not consistent,
            "prediction_error": float(prediction_error),
            "observed_resource": evidence.get("resource"),
        }
