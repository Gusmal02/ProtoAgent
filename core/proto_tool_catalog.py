"""Evidence-gated catalogue of ProtoAgent tools.

The catalogue does not execute tools and does not infer a policy from geometric
similarity by itself.  It exposes declared tool contracts, asks ProtoLibrary
for compatible verified evidence, and returns a recommendation or abstention.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import torch

from core.proto_library import ProtoLibrary


@dataclass(frozen=True)
class ToolContract:
    tool_id: str
    purpose: str
    input_kind: str
    verifier: str
    requires: dict[str, Any]
    estimated_cost: str


class ProtoToolCatalog:
    """Maps verified library policies to explicit, eligible tool contracts."""

    def __init__(self, library: ProtoLibrary) -> None:
        self.library = library
        self._tools: dict[str, ToolContract] = {}

    def register(self, contract: ToolContract) -> None:
        if not contract.tool_id or contract.tool_id in self._tools:
            raise ValueError("tool_id must be unique and non-empty")
        self._tools[contract.tool_id] = contract

    @staticmethod
    def _eligible(contract: ToolContract, context_meta: dict[str, Any]) -> bool:
        return all(context_meta.get(key) == value for key, value in contract.requires.items())

    def recommend(
        self,
        signature: torch.Tensor,
        context_meta: dict[str, Any],
        *,
        min_support: float = .70,
        min_cards: int = 2,
    ) -> dict[str, Any]:
        evidence = self.library.consult(signature, min_support=min_support,
                                        min_cards=min_cards, context_meta=context_meta)
        if evidence["decision"] != "recommend":
            return {"decision": "abstain", "reason": evidence["reason"], "risk": evidence["risk"],
                    "evidence": evidence, "available_tools": sorted(self._tools)}
        tool = self._tools.get(evidence["policy"])
        if tool is None:
            return {"decision": "abstain", "reason": "recommended_tool_not_registered", "risk": 1.0,
                    "evidence": evidence, "available_tools": sorted(self._tools)}
        if not self._eligible(tool, context_meta):
            return {"decision": "abstain", "reason": "tool_contract_ineligible", "risk": 1.0,
                    "evidence": evidence, "available_tools": sorted(self._tools)}
        return {"decision": "recommend", "tool": asdict(tool), "support": evidence["support"],
                "risk": evidence["risk"], "conflicts": evidence["conflicts"], "evidence": evidence}

    def snapshot(self) -> dict[str, Any]:
        return {"tools": [asdict(tool) for tool in self._tools.values()]}
