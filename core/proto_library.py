"""Small evidence library for a traceable ProtoAgent.

This is deliberately not a general database.  It keeps compact, verifiable
experience cards and uses ContextualMemory only to retrieve relevant cards.
Recommendations include their support, conflicts, and conditions; they never
hide a conflict behind a single policy label.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import torch

from core.contextual_memory import ContextualMemory


VALID_EVIDENCE = {"verified_finite", "formal"}


@dataclass(frozen=True)
class LibraryCard:
    card_id: str
    policy: str
    evidence_state: str
    outcome: dict[str, Any]
    conditions: dict[str, Any]
    confidence: float
    t_insert: int


class ProtoLibrary:
    """A small, evidence-gated library with explicit epistemic state."""

    def __init__(self, theta: float = .62, gamma_decay: float = .0) -> None:
        self.memory = ContextualMemory(theta_ctx=theta, gamma_decay=gamma_decay)
        self.theta = theta
        self._cards: dict[int, LibraryCard] = {}
        self._ids: set[str] = set()

    @staticmethod
    def _unit(vector: torch.Tensor) -> torch.Tensor:
        value = vector.detach().float().flatten()
        if value.numel() == 0 or value.norm().item() == 0:
            raise ValueError("signature must be non-zero")
        return value / value.norm().clamp_min(1e-8)

    def admit(
        self,
        card_id: str,
        signature: torch.Tensor,
        policy: str,
        evidence_state: str,
        outcome: dict[str, Any],
        conditions: dict[str, Any],
        confidence: float = 1.0,
    ) -> LibraryCard:
        """Store only locally verifiable finite or formal experience cards."""
        if evidence_state not in VALID_EVIDENCE:
            raise ValueError("library admits only verified_finite or formal evidence")
        if not card_id or card_id in self._ids:
            raise ValueError("card_id must be unique and non-empty")
        if not 0.0 < confidence <= 1.0:
            raise ValueError("confidence must be in (0, 1]")
        tick = len(self._cards)
        card = LibraryCard(card_id, policy, evidence_state, dict(outcome), dict(conditions), confidence, tick)
        vector = self._unit(signature)
        self.memory.add(vector, vector, t_insert=tick, label=policy)
        self._cards[tick] = card
        self._ids.add(card_id)
        return card

    @staticmethod
    def _eligible(card: LibraryCard, context_meta: dict[str, Any] | None) -> bool:
        if context_meta is None:
            # A card that declares categorical requirements cannot be reused
            # without the metadata needed to check them.
            return not card.conditions.get("requires")
        conditions = card.conditions
        requires = conditions.get("requires", {})
        if not isinstance(requires, dict):
            raise ValueError("conditions.requires must be a mapping when present")
        # `requires` is intentionally exact and conservative. Similarity in
        # omega-space never overrides an absent or incompatible declared scope.
        for key, expected in requires.items():
            if key not in context_meta or context_meta[key] != expected:
                return False
        density = context_meta.get("density")
        nodes = context_meta.get("nodes")
        if density is not None:
            if density < conditions.get("min_density", float("-inf")) or density > conditions.get("max_density", float("inf")):
                return False
        if nodes is not None:
            if nodes < conditions.get("min_nodes", float("-inf")) or nodes > conditions.get("max_nodes", float("inf")):
                return False
        return True

    def consult(self, signature: torch.Tensor, min_support: float = .70, min_cards: int = 2, context_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a recommendation or explicit abstention, never a hidden vote."""
        vector = self._unit(signature)
        evoked = self.memory.evoke(vector, theta=self.theta)
        votes: dict[str, float] = {}
        cards: list[dict[str, Any]] = []
        for trace, similarity in evoked:
            card = self._cards.get(trace.t_insert)
            if card is None:
                continue
            if not self._eligible(card, context_meta):
                continue
            weight = float(similarity) * trace.strength * card.confidence
            votes[card.policy] = votes.get(card.policy, .0) + weight
            cards.append({"card_id": card.card_id, "policy": card.policy, "similarity": round(float(similarity), 5),
                          "confidence": card.confidence, "conditions": card.conditions, "outcome": card.outcome})
        total = sum(votes.values())
        if not votes:
            return {"decision": "abstain", "reason": "no_relevant_verified_cards", "cards": [], "votes": {}, "risk": 1.0}
        policy = sorted(votes, key=lambda item: (-votes[item], item))[0]
        support = votes[policy] / total if total else 0.0
        conflicts = len(votes) > 1
        risk = 1.0 - support
        if len(cards) < min_cards:
            return {"decision": "abstain", "reason": "insufficient_evidence", "cards": cards, "votes": votes, "risk": risk}
        if support < min_support:
            return {"decision": "abstain", "reason": "conflicting_verified_cards", "cards": cards, "votes": votes, "risk": risk}
        return {"decision": "recommend", "policy": policy, "support": support, "risk": risk,
                "conflicts": conflicts, "cards": cards, "votes": votes}

    def snapshot(self) -> dict[str, Any]:
        return {"cards": [asdict(card) for card in self._cards.values()], "memory": self.memory.summary(), "theta": self.theta}
