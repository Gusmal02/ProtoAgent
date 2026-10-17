"""Typed, provider-independent contracts. No LLM or numerical dependencies."""
from dataclasses import dataclass, asdict
from typing import Protocol
import hashlib
import json

SCHEMA_VERSION = "0.1"

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()

@dataclass(frozen=True)
class QuerySpec:
    connector: str
    operation: str
    entity: str
    parameters: tuple[tuple[str, str], ...] = ()

@dataclass(frozen=True)
class ActionSpec:
    connector: str
    operation: str
    entity: str
    evidence_ids: tuple[str, ...]
    reversible: bool = True

@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    connector: str
    entity: str
    revision: str
    payload_json: str
    status: str = "candidate"

@dataclass(frozen=True)
class Contract:
    version: str
    entities: frozenset[str]
    operations: frozenset[tuple[str, str]]
    minimum_evidence: int = 1
    require_reversible: bool = True

    @property
    def fingerprint(self) -> str:
        return digest({"version": self.version, "entities": sorted(self.entities),
                       "operations": sorted(self.operations), "minimum_evidence": self.minimum_evidence,
                       "require_reversible": self.require_reversible})

@dataclass(frozen=True)
class Proposal:
    action: ActionSpec
    rationale: str

@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    contract_fingerprint: str
    request_fingerprint: str

@dataclass(frozen=True)
class Outcome:
    success: bool
    evidence_ids: tuple[str, ...]
    rollback_token: str | None = None

@dataclass(frozen=True)
class AuditRecord:
    sequence: int
    event: str
    request_fingerprint: str
    previous_hash: str
    record_hash: str

class Connector(Protocol):
    name: str
    def query(self, spec: QuerySpec) -> tuple[Evidence, ...]: ...
    def execute(self, spec: ActionSpec) -> Outcome: ...
    def verify(self, outcome: Outcome) -> bool: ...
    def rollback(self, outcome: Outcome) -> Outcome: ...

def authorize(request: QuerySpec | ActionSpec, contract: Contract,
              evidence: tuple[Evidence, ...] = ()) -> Decision:
    """Low-level check: evidence must already come from a trusted connector.

    Never deserialize a document's claimed status into trusted Evidence here.
    Untrusted proposals require a registry-backed execution boundary.
    """
    reason = "allowed"
    if request.entity not in contract.entities:
        reason = "entity_not_authorized"
    elif (request.connector, request.operation) not in contract.operations:
        reason = "operation_not_authorized"
    elif isinstance(request, ActionSpec):
        valid = {e.evidence_id for e in evidence
                 if e.entity == request.entity and e.status in ("verified_finite", "formal")}
        if len(set(request.evidence_ids) & valid) < contract.minimum_evidence:
            reason = "insufficient_verified_evidence"
        elif contract.require_reversible and not request.reversible:
            reason = "reversibility_required"
    return Decision(reason == "allowed", reason, contract.fingerprint, digest(asdict(request)))

def revalidate(request, decision: Decision, current: Contract, evidence=()) -> bool:
    fresh = authorize(request, current, evidence)
    return (decision.allowed and fresh.allowed
            and decision.contract_fingerprint == fresh.contract_fingerprint
            and decision.request_fingerprint == fresh.request_fingerprint)

class AuditLog:
    """Hash chain detects changes; it is not an external immutable storage service."""
    def __init__(self):
        self.records: list[AuditRecord] = []

    def append(self, event: str, request) -> AuditRecord:
        sequence = len(self.records)
        previous = self.records[-1].record_hash if self.records else "0" * 64
        fingerprint = digest(asdict(request))
        record = AuditRecord(sequence, event, fingerprint, previous,
                             digest([sequence, event, fingerprint, previous]))
        self.records.append(record)
        return record

    def intact(self) -> bool:
        previous = "0" * 64
        for sequence, record in enumerate(self.records):
            if (record.sequence != sequence or record.previous_hash != previous
                or record.record_hash != digest([sequence, record.event, record.request_fingerprint, previous])):
                return False
            previous = record.record_hash
        return True
