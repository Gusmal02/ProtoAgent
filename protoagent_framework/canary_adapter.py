"""Native SQLite reference adapter; no heuristic/LLM chooses its operations."""
from contextlib import contextmanager
import json
import sqlite3
import threading
import uuid
from .api import AdapterManifest, Capability, ContractError
from .contracts import Evidence, Outcome

class CanaryAdapter:
    manifest=AdapterManifest('canary','0.1',(
        Capability('read_state','query'), Capability('pause','action'), Capability('resume','action')))
    def __init__(self, path=':memory:'):
        self.lock=threading.RLock(); self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS targets(entity TEXT PRIMARY KEY, paused INTEGER, revision INTEGER)')
        self.db.commit(); self.proofs={}; self.receipts={}; self.fail_once=False
    @contextmanager
    def transaction(self):
        with self.lock: yield
    def seed(self, entity, paused=False):
        with self.lock:
            self.db.execute('INSERT INTO targets VALUES(?,?,0)',(entity,int(paused))); self.db.commit()
    def state(self, entity):
        with self.lock:
            row=self.db.execute('SELECT paused,revision FROM targets WHERE entity=?',(entity,)).fetchone()
            return None if row is None else tuple(row)
    def query(self, request):
        if request.connector!=self.manifest.name or request.operation!='read_state' or request.parameters:
            raise ContractError('unsupported native query')
        row=self.state(request.entity)
        if row is None: return ()
        proof=Evidence(uuid.uuid4().hex,'canary',request.entity,str(row[1]),json.dumps({'paused':bool(row[0])}),'verified_finite')
        self.proofs[proof.evidence_id]=proof
        return (proof,)
    def verify_evidence(self, evidence, action):
        row=self.state(action.entity)
        return (self.proofs.get(evidence.evidence_id)==evidence and row is not None and
                evidence.entity==action.entity and evidence.revision==str(row[1]) and action.operation in ('pause','resume'))
    def execute(self, action):
        if action.operation not in ('pause','resume'): raise ContractError('unsupported native action')
        if not any(i in self.proofs and self.verify_evidence(self.proofs[i],action) for i in action.evidence_ids):
            raise ContractError('stale native evidence')
        before=self.state(action.entity)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if not any(i in self.proofs and self.verify_evidence(self.proofs[i],action) for i in action.evidence_ids):
                raise ContractError('evidence changed before native transaction')
            changed=self.db.execute('UPDATE targets SET paused=?,revision=revision+1 WHERE entity=? AND revision=?',
                            (int(action.operation=='pause'),action.entity,before[1]))
            if changed.rowcount!=1: raise ContractError('native revision conflict')
            if self.fail_once:
                self.fail_once=False; raise RuntimeError('injected transaction failure')
            self.db.commit()
        except Exception:
            self.db.rollback(); raise
        token=uuid.uuid4().hex
        outcome=Outcome(True,action.evidence_ids,token)
        self.receipts[token]=(action.entity,before,self.state(action.entity),outcome)
        return outcome
    def verify(self, outcome):
        record=self.receipts.get(outcome.rollback_token)
        return bool(record and record[3]==outcome and self.state(record[0])==record[2])
    def rollback(self, outcome):
        record=self.receipts.get(outcome.rollback_token)
        if not record or record[3]!=outcome or self.state(record[0])!=record[2]: return Outcome(False,())
        entity,before,_,_=record
        # Never rewind revision: a restored value is still a new observed event.
        changed=self.db.execute('UPDATE targets SET paused=?,revision=revision+1 WHERE entity=? AND revision=?',
                               (before[0],entity,record[2][1])); self.db.commit()
        if changed.rowcount!=1: return Outcome(False,())
        del self.receipts[outcome.rollback_token]
        return Outcome(self.state(entity)[0]==before[0],outcome.evidence_ids)
    def close(self):
        with self.lock: self.db.close()
