"""F1 execution boundary: resolve evidence from an owned registry, not documents."""
import json
import sqlite3
import threading
from dataclasses import asdict
from .contracts import ActionSpec, Evidence, authorize, revalidate, digest

class GovernedSQLite:
    def __init__(self, path, contract):
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS proofs(id TEXT PRIMARY KEY, entity TEXT,
                operation TEXT, revision INTEGER, expires INTEGER, permitted INTEGER);
            CREATE TABLE IF NOT EXISTS canary(entity TEXT PRIMARY KEY, paused INTEGER);
            CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY, record TEXT);
        """)
        self.contract=contract
        self.tick=0
        self.fail_once=False
        self.db.commit()

    @property
    def contract(self):
        with self.lock: return self._contract

    @contract.setter
    def contract(self,value):
        with self.lock: self._contract=value

    @property
    def tick(self):
        with self.lock: return self._tick

    @tick.setter
    def tick(self,value):
        with self.lock: self._tick=value

    def issue_from_trusted_connector(self, entity, operation, expires, permitted=True):
        with self.lock:
            return self._issue_from_trusted_connector(entity,operation,expires,permitted)

    def _issue_from_trusted_connector(self, entity, operation, expires, permitted=True):
        # Internal connector method, not an ingestion endpoint available to documents.
        identity=digest([entity,operation,self.tick,expires,permitted])
        self.db.execute("INSERT OR REPLACE INTO proofs VALUES(?,?,?,?,?,?)",
                        (identity,entity,operation,self.tick,expires,int(permitted)))
        self.db.commit()
        return identity

    def validate(self, spec):
        with self.lock: return self._validate(spec)

    def _validate(self, spec):
        evidence=[]
        for identity in set(spec.evidence_ids):
            row=self.db.execute("SELECT entity,operation,revision,expires,permitted FROM proofs WHERE id=?",
                                (identity,)).fetchone()
            if row and row[0]==spec.entity and row[1]==spec.operation and row[3]>=self.tick and row[4]:
                evidence.append(Evidence(identity,"trusted_monitor",row[0],str(row[2]),
                                         json.dumps({"operation":row[1]}),"verified_finite"))
        conflict=self.db.execute(
            "SELECT 1 FROM proofs WHERE entity=? AND operation=? AND revision=? AND permitted=0",
            (spec.entity,spec.operation,self.tick)).fetchone()
        decision=authorize(spec,self.contract,tuple(evidence))
        return decision,tuple(evidence),bool(conflict)

    def execute(self,spec,before_execution=None):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                return self._execute(spec,before_execution)
            except Exception:
                self.db.rollback()
                raise

    def _execute(self,spec,before_execution=None):
        decision,evidence,conflict=self.validate(spec)
        if before_execution: before_execution(self)
        fresh,fresh_evidence,fresh_conflict=self.validate(spec)
        accepted=(not conflict and not fresh_conflict and
                  revalidate(spec,decision,self.contract,fresh_evidence))
        outcome={"accepted":False,"reason":fresh.reason if not fresh.allowed else
                 "evidence_conflict" if conflict or fresh_conflict else "contract_changed",
                 "rolled_back":False,"changed":False}
        if accepted:
            if spec.operation not in ("pause_canary","resume_canary"):
                raise ValueError("unsupported declared operation")
            try:
                cursor=self.db.execute("UPDATE canary SET paused=? WHERE entity=?",
                                       (int(spec.operation=="pause_canary"),spec.entity))
                if cursor.rowcount!=1:
                    raise RuntimeError("target entity unavailable")
                if self.fail_once:
                    self.fail_once=False
                    raise RuntimeError("injected tool failure")
                self.db.commit()
                outcome={"accepted":True,"reason":"verified_execution","changed":True,"rolled_back":False}
            except RuntimeError:
                self.db.rollback()
                outcome={"accepted":False,"reason":"tool_failure","changed":False,"rolled_back":True}
        self.db.execute("INSERT INTO journal(record) VALUES(?)",(json.dumps({
            "tick":self.tick,"request":asdict(spec),"decision":outcome,
            "active_contract":self.contract.fingerprint},sort_keys=True),))
        self.db.commit()
        return outcome

    def close(self):
        with self.lock: self.db.close()
