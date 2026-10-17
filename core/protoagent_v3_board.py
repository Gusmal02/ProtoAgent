"""Pizarra metacognitiva reutilizable para ProtoAgent v3."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class BoardEntry:
    state: str
    action: int
    outcome: str
    reward: float
    confidence: float
    diagnosis: str
    step: int

class MetacognitiveBoard:
    """Memoria de trabajo: estados, ciclos, meta, hipótesis y causa de duda."""
    def __init__(self, goal: Any = None):
        self.goal = goal
        self.visited: set[str] = set()
        self.entries: list[BoardEntry] = []
        self.variables: dict[str, Any] = {}
        self.hypotheses: list[dict] = []

    def enter(self, state: Any) -> bool:
        key = repr(state)
        repeated = key in self.visited
        self.visited.add(key)
        return repeated

    def diagnose(self, confidence: float, prediction_error: float, repeated: bool) -> str:
        if repeated and prediction_error < 0.15: return "known_cycle"
        if confidence < 0.20: return "ignorance"
        if prediction_error > 0.50: return "contradiction"
        if confidence < 0.55: return "ambiguous"
        return "known"

    def record(self, state: Any, action: int, outcome: str, reward: float,
               confidence: float, prediction_error: float, repeated: bool, step: int) -> str:
        diagnosis = self.diagnose(confidence, prediction_error, repeated)
        self.entries.append(BoardEntry(repr(state), int(action), outcome, float(reward),
                                       float(confidence), diagnosis, int(step)))
        return diagnosis

    def summary(self) -> dict:
        causes = {name: 0 for name in ("known", "ignorance", "contradiction", "ambiguous", "known_cycle")}
        for entry in self.entries: causes[entry.diagnosis] = causes.get(entry.diagnosis, 0) + 1
        return {"visited_states": len(self.visited), "entries": len(self.entries), "diagnoses": causes,
                "variables": self.variables.copy(), "hypotheses": len(self.hypotheses)}

    def export(self) -> list[dict]: return [asdict(entry) for entry in self.entries]
