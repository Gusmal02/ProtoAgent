"""Auditable lifecycle state for conditional bridges in the resonant library."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path


@dataclass
class BridgeRecord:
    bridge_id: str
    status: str = "candidate"  # candidate | active | limbo | tension
    weight: float = 0.0
    successes: int = 0
    failures: int = 0
    context: tuple[float, float, float] = (1.0, 0.0, 0.0)
    evidence: list[str] | None = None
    revalidation_receipts: list[str] | None = None


class ResonantLibraryRuntime:
    """Bounded, persisted bridge lifecycle; never fuses library nodes."""
    def __init__(self, max_bridges: int = 128, max_active_bridges: int | None = None,
                 allow_same_context_revalidation: bool = False) -> None:
        self.max_bridges = max_bridges
        # Historical candidates/tensions are cheap audit records; physical active
        # bridges consume a distinct scarce resource.  Defaults preserve the old
        # one-budget behaviour for existing callers.
        self.max_active_bridges = max_bridges if max_active_bridges is None else max_active_bridges
        self.bridges: dict[str, BridgeRecord] = {}
        self.audit: list[dict] = []
        # Opt-in: three fresh, consecutive, caller-verified measurements can
        # recover a changed mechanism even when its visible context is stable.
        # This lifecycle is NOT an authority gate or an evidence verifier.
        self.allow_same_context_revalidation = allow_same_context_revalidation

    @staticmethod
    def _angle(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
        dot = sum(a * b for a, b in zip(left, right)); nl = math.sqrt(sum(a*a for a in left)); nr = math.sqrt(sum(a*a for a in right))
        return math.degrees(math.acos(max(-1.0, min(1.0, dot / max(nl * nr, 1e-12)))))

    def observe(self, bridge_id: str, context: tuple[float, float, float], utility: float,
                mechanism_ok: bool, tension: bool = False, evidence: str = "") -> BridgeRecord:
        if bridge_id not in self.bridges:
            if len(self.bridges) >= self.max_bridges: raise RuntimeError("bridge budget exhausted")
            self.bridges[bridge_id] = BridgeRecord(bridge_id, context=context, evidence=[])
        bridge = self.bridges[bridge_id]
        if evidence: bridge.evidence.append(evidence)
        if tension:
            bridge.status = "tension"; bridge.weight = 0.0; bridge.revalidation_receipts = []
        elif bridge.status == "limbo":
            good = utility >= 0.70 and mechanism_ok
            if self.allow_same_context_revalidation:
                receipts = bridge.revalidation_receipts or []
                if not good:
                    receipts = []; bridge.failures += 1
                elif evidence and evidence not in receipts and bridge.evidence.count(evidence) == 1:
                    receipts.append(evidence)
                bridge.revalidation_receipts = receipts
                recover = good and len(receipts) >= 3
            else:
                recover = self._angle(bridge.context, context) > 30.0 and good
                if not recover: bridge.failures += 1
            if recover:
                if sum(item.status == "active" for item in self.bridges.values()) >= self.max_active_bridges:
                    raise RuntimeError("active bridge budget exhausted")
                bridge.status = "active"; bridge.weight = max(0.5, bridge.weight); bridge.successes += 1; bridge.context = context
                bridge.revalidation_receipts = []
        elif utility >= 0.70 and mechanism_ok:
            bridge.successes += 1; bridge.context = context
            bridge.weight = min(1.0, bridge.weight + 0.35)
            if bridge.successes >= 2:
                # The active budget constrains a transition into the physical
                # layer.  Re-observing an already active bridge must reinforce
                # it, not consume a second slot or raise a false exhaustion.
                if bridge.status != "active" and sum(item.status == "active" for item in self.bridges.values()) >= self.max_active_bridges:
                    raise RuntimeError("active bridge budget exhausted")
                bridge.status = "active"
        else:
            bridge.failures += 1
            if bridge.status == "active":
                bridge.status = "limbo"; bridge.weight *= 0.5; bridge.revalidation_receipts = []
        self.audit.append({"bridge_id": bridge_id, "status": bridge.status, "utility": utility, "mechanism_ok": mechanism_ok, "tension": tension})
        return bridge

    def decay(self, factor: float = 0.85) -> None:
        for bridge in self.bridges.values():
            if bridge.status == "active": bridge.weight *= factor
            if bridge.status == "active" and bridge.weight < 0.15:
                bridge.status = "limbo"; bridge.revalidation_receipts = []

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"max_bridges": self.max_bridges, "max_active_bridges": self.max_active_bridges,
            "allow_same_context_revalidation": self.allow_same_context_revalidation,
            "bridges": [asdict(b) for b in self.bridges.values()], "audit": self.audit}, ensure_ascii=False, indent=2), encoding="utf8")

    @classmethod
    def load(cls, path: str | Path) -> "ResonantLibraryRuntime":
        data = json.loads(Path(path).read_text(encoding="utf8")); runtime = cls(data["max_bridges"], data.get("max_active_bridges"),
            data.get("allow_same_context_revalidation", False))
        runtime.bridges = {item["bridge_id"]: BridgeRecord(**item) for item in data["bridges"]}; runtime.audit = data["audit"]
        return runtime
