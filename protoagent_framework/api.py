"""Experimental SDK boundary. Planners and documents never mint authority."""
from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Protocol
from dataclasses import asdict
from .contracts import (ActionSpec, AuditLog, Contract, Decision, Evidence, Outcome,
                        QuerySpec, authorize, digest, revalidate)

API_VERSION = '0.1'

class ContractError(ValueError):
    pass

@dataclass(frozen=True)
class Capability:
    operation: str
    kind: str
    parameters: tuple[str, ...] = ()
    reversible: bool = True
    impact: str = 'entity'
    minimum_evidence: int = 1

@dataclass(frozen=True)
class AdapterManifest:
    name: str
    version: str
    capabilities: tuple[Capability, ...]
    schema_version: str = API_VERSION
    def __post_init__(self):
        if self.schema_version != API_VERSION or not self.name or not self.version:
            raise ContractError('incompatible manifest')
        names=[c.operation for c in self.capabilities]
        if len(names)!=len(set(names)) or not names:
            raise ContractError('duplicate or missing capabilities')
        for c in self.capabilities:
            if (not c.operation or c.kind not in ('query','action') or
                c.impact!='entity' or type(c.minimum_evidence) is not int or c.minimum_evidence<1 or
                type(c.reversible) is not bool or len(c.parameters)!=len(set(c.parameters))):
                raise ContractError('unsupported capability')
            if c.kind=='action' and (not c.reversible or c.parameters):
                raise ContractError('only parameter-free reversible actions in API 0.1')
    def capability(self, operation, kind):
        found=next((c for c in self.capabilities if c.operation==operation and c.kind==kind),None)
        if found is None: raise ContractError('undeclared operation')
        return found

class Adapter(Protocol):
    manifest: AdapterManifest
    def transaction(self): ...
    def query(self, request: QuerySpec) -> tuple[Evidence, ...]: ...
    def verify_evidence(self, evidence: Evidence, action: ActionSpec) -> bool: ...
    def execute(self, request: ActionSpec) -> Outcome: ...
    def verify(self, outcome: Outcome) -> bool: ...
    def rollback(self, outcome: Outcome) -> Outcome: ...

@dataclass(frozen=True)
class ExecutionResult:
    state: str
    reason: str
    outcome: Outcome | None = None

class GovernedRuntime:
    """In-process, serialized authority boundary; not the cognitive planner.

    Trusted adapters must share their native transaction lock with all writers.
    Distributed/native policy checks remain the responsibility of the provider.
    """
    def __init__(self, contract: Contract, *, proof_ttl=60., clock=None, capacity=512):
        import time
        if proof_ttl<=0 or capacity<1: raise ContractError('invalid budget')
        self._contract=contract; self._lock=threading.RLock(); self._adapters={}
        self._proofs={}; self._receipts={}; self._keys={}; self.capacity=capacity
        self.clock=clock or time.monotonic; self.proof_ttl=proof_ttl; self.audit=AuditLog()
    @property
    def contract(self):
        with self._lock: return self._contract
    def set_contract(self, contract):
        with self._lock: self._contract=contract
    def register(self, adapter: Adapter):
        with self._lock:
            if not isinstance(adapter.manifest,AdapterManifest): raise ContractError('invalid manifest')
            if adapter.manifest.name in self._adapters: raise ContractError('duplicate adapter')
            for method in ('transaction','query','verify_evidence','execute','verify','rollback'):
                if not callable(getattr(adapter,method,None)): raise ContractError('missing adapter method')
            self._adapters[adapter.manifest.name]=adapter
    def _adapter(self, request, kind):
        from .wire import dumps, loads
        if loads(dumps(request))!=request: raise ContractError('invalid request types')
        adapter=self._adapters.get(request.connector)
        if adapter is None: raise ContractError('unknown adapter')
        cap=adapter.manifest.capability(request.operation,kind)
        if kind=='action' and request.reversible!=cap.reversible:
            raise ContractError('reversibility does not match capability')
        if kind=='query':
            keys=[p[0] for p in request.parameters]
            if len(keys)!=len(set(keys)) or set(keys)!=set(cap.parameters):
                raise ContractError('unsupported query parameters')
        return adapter, cap
    def observe(self, request: QuerySpec) -> tuple[Evidence,...]:
        with self._lock:
            adapter,_=self._adapter(request,'query')
            decision=authorize(request,self._contract); self.audit.append('query',request)
            if not decision.allowed: raise ContractError(decision.reason)
            with adapter.transaction(): proofs=tuple(adapter.query(request))
            if any(not isinstance(p,Evidence) or p.connector!=request.connector or
                   p.entity!=request.entity or p.status not in ('verified_finite','formal') for p in proofs):
                raise ContractError('adapter evidence scope violation')
            now=self.clock()
            self._proofs={k:v for k,v in self._proofs.items() if v[1]>=now}
            fresh={p.evidence_id for p in proofs}-set(self._proofs)
            if len(self._proofs)+len(fresh)>self.capacity: raise ContractError('proof budget exhausted')
            for p in proofs:
                old=self._proofs.get(p.evidence_id)
                if old and old[0]!=p: raise ContractError('evidence identity collision')
            for p in proofs: self._proofs[p.evidence_id]=(p,now+self.proof_ttl)
            return proofs
    def _authorize(self, action):
        adapter, cap=self._adapter(action,'action')
        evidence=tuple(self._proofs[i][0] for i in set(action.evidence_ids) if i in self._proofs and
            self._proofs[i][1]>=self.clock() and adapter.verify_evidence(self._proofs[i][0],action))
        decision=authorize(action,self._contract,evidence)
        if len(evidence)<cap.minimum_evidence:
            decision=Decision(False,'adapter_evidence_quorum',decision.contract_fingerprint,decision.request_fingerprint)
        return adapter,decision,evidence
    def authorize(self, action: ActionSpec) -> Decision:
        with self._lock:
            adapter,_=self._adapter(action,'action')
            with adapter.transaction(): return self._authorize(action)[1]
    def execute(self, action: ActionSpec, decision: Decision, *, idempotency_key=None) -> ExecutionResult:
        with self._lock:
            adapter,_=self._adapter(action,'action')
            with adapter.transaction():
                if idempotency_key is not None:
                    if not isinstance(idempotency_key,str) or not 1<=len(idempotency_key)<=128:
                        raise ContractError('invalid idempotency key')
                    existing=self._keys.get(idempotency_key)
                    if existing:
                        binding=(digest(asdict(action)),self._contract.fingerprint)
                        if existing[0][0]!=binding[0]: raise ContractError('idempotency conflict')
                        if (existing[0][1]!=binding[1] or not decision.allowed or
                            decision.request_fingerprint!=binding[0] or decision.contract_fingerprint!=binding[1]):
                            return ExecutionResult('denied','contract_or_request_changed')
                        # Returning a prior receipt is not another mutation and
                        # does not demand a post-mutation revision match.
                        self.audit.append('idempotent_receipt',action)
                        return existing[1]
                _,fresh,evidence=self._authorize(action)
                self.audit.append('execute_attempt',action)
                if not fresh.allowed or not revalidate(action,decision,self._contract,evidence):
                    return ExecutionResult('denied',fresh.reason if not fresh.allowed else 'contract_or_request_changed')
                binding=(fresh.request_fingerprint,fresh.contract_fingerprint)
                if len(self._receipts)>=self.capacity: raise ContractError('receipt budget exhausted')
                try: outcome=adapter.execute(action)
                except Exception:
                    self.audit.append('tool_failure',action)
                    return ExecutionResult('failed','adapter_failure')
                if not outcome.success or not adapter.verify(outcome):
                    restored=adapter.rollback(outcome)
                    self.audit.append('verification_failure',action)
                    return ExecutionResult('rolled_back' if restored.success else 'incident', 'native_verification_failed',restored)
                if not outcome.rollback_token or outcome.rollback_token in self._receipts:
                    raise ContractError('invalid rollback token: adapter incident')
                self._receipts[outcome.rollback_token]=(action,outcome)
                result=ExecutionResult('executed','native_verified',outcome)
                if idempotency_key is not None: self._keys[idempotency_key]=(binding,result)
                self.audit.append('verified',action)
                return result
    def rollback(self, token: str) -> ExecutionResult:
        with self._lock:
            record=self._receipts.get(token)
            if record is None: raise ContractError('unknown rollback token')
            action,outcome=record; adapter,_=self._adapter(action,'action')
            # Rollback is an explicit, separately authorized capability.
            rollback_request=QuerySpec(action.connector,'rollback',action.entity)
            if not authorize(rollback_request,self._contract).allowed: return ExecutionResult('denied','rollback_not_authorized')
            with adapter.transaction(): restored=adapter.rollback(outcome)
            self.audit.append('rollback',action)
            if restored.success:
                del self._receipts[token]
                self._keys={k:v for k,v in self._keys.items() if v[1].outcome.rollback_token!=token}
            return ExecutionResult('rolled_back' if restored.success else 'incident','native_rollback',restored)
