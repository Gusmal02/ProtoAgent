"""Memoria causal y guardián de ejecución para ProtoAgent v3."""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class CausalRecord:
    condition: dict
    action: int
    consequence: dict
    confidence: float
    evidence: dict
    step: int


class CausalMemory:
    def __init__(self): self.records: list[CausalRecord] = []
    def add(self, **kwargs) -> None: self.records.append(CausalRecord(**kwargs))
    def export(self) -> list[dict]: return [asdict(record) for record in self.records]


class ExecutionGate:
    """No ejecuta acciones externas; emite una autorización explicable."""
    def __init__(self, mode: str = "laboratory", uncertainty_limit: float = .45):
        if mode not in {"observe", "laboratory", "production"}: raise ValueError("modo inválido")
        self.mode, self.uncertainty_limit = mode, uncertainty_limit
    def assess(self, empirical: dict, harmful: bool = False) -> dict:
        if self.mode == "observe": return {"decision": "recommend_only", "reason": "observe_mode"}
        if harmful: return {"decision": "block", "reason": "harmful_outcome"}
        if empirical.get("uncertainty", 1.0) > self.uncertainty_limit:
            return {"decision": "review", "reason": "insufficient_evidence"}
        return {"decision": "allow", "reason": "bounded_laboratory" if self.mode == "laboratory" else "validated_production"}
