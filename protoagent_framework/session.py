"""Durable host-owned sessions over a provider with durable operation receipts.

The session DB is trusted host storage, not agent-editable workspace. Providers
must bind operation ID to action/entity and atomically persist effect + receipt.
External non-idempotent effects are explicitly outside this guarantee.
"""
import hashlib
import json
import sqlite3
import time
import uuid
from .engine import Engine
from .checkpoint_storage import pack,unpack

class SessionError(RuntimeError): pass

class Session:
    def __init__(self, path, session_id, engine=None, *, budget=100, goal=None,events=None):
        self.events=events
        if type(budget) is not int or not 1<=budget<=100000:
            raise ValueError('invalid session step budget')
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, status TEXT NOT NULL,
            used INTEGER NOT NULL, budget INTEGER NOT NULL, version INTEGER NOT NULL,
            checkpoint BLOB NOT NULL, checksum TEXT NOT NULL, pending TEXT,
            goal TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            session TEXT NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL,
            previous TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, session TEXT NOT NULL,
            entity TEXT, action INTEGER, request TEXT, result TEXT, state TEXT NOT NULL,
            view TEXT);
        CREATE INDEX IF NOT EXISTS events_session_seq ON events(session,seq);
        ''')
        self.id=session_id
        existing=self.db.execute('SELECT 1 FROM sessions WHERE id=?',(session_id,)).fetchone()
        if existing and engine is not None:
            self.db.close(); raise SessionError('session ID exists; use resume instead of recreating it')
        if existing is None:
            if engine is None: raise SessionError('session not found')
            raw=pack(engine.snapshot())
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?)',
                (session_id,'ready',0,budget,0,raw,hashlib.sha256(raw).hexdigest(),None,
                 json.dumps(goal or {},allow_nan=False)))
            self._event('created',{'budget':budget,'goal':goal or {}})
            self.db.commit()
        try: self._load()
        except Exception: self.db.close(); raise

    def _event(self, event, payload):
        encoded=json.dumps(payload,sort_keys=True,allow_nan=False,separators=(',',':'))
        row=self.db.execute('SELECT hash FROM events WHERE session=? ORDER BY seq DESC LIMIT 1',(self.id,)).fetchone()
        previous=row[0] if row else '0'*64
        digest=hashlib.sha256(json.dumps([self.id,event,encoded,previous]).encode()).hexdigest()
        self.db.execute('INSERT INTO events(session,event,payload,previous,hash) VALUES(?,?,?,?,?)',
                        (self.id,event,encoded,previous,digest))

    def _row(self):
        return self.db.execute('SELECT status,used,budget,version,checkpoint,checksum,pending,goal FROM sessions WHERE id=?',
                               (self.id,)).fetchone()

    def _load(self):
        row=self._row()
        if hashlib.sha256(row[4]).hexdigest()!=row[5]: raise SessionError('corrupt checkpoint')
        if not self.audit_intact(): raise SessionError('corrupt audit chain')
        self.engine=Engine.restore(unpack(row[4])); self.version=row[3]

    def audit_intact(self):
        previous='0'*64
        for event,payload,before,digest in self.db.execute(
            'SELECT event,payload,previous,hash FROM events WHERE session=? ORDER BY seq',(self.id,)):
            expected=hashlib.sha256(json.dumps([self.id,event,payload,previous]).encode()).hexdigest()
            if before!=previous or digest!=expected: return False
            previous=digest
        return True

    def start(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self._row()
            if row[0] in ('cancelled','completed','exhausted'): raise SessionError('session is terminal')
            self.db.execute('UPDATE sessions SET status=? WHERE id=?',('running',self.id))
            self._event('started',{}); self.db.commit()
        except Exception: self.db.rollback(); raise

    def pause(self): self._status('paused')
    def cancel(self): self._status('cancelled')

    def _status(self, status):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self._row()[0] in ('completed','cancelled','exhausted'): raise SessionError('session is terminal')
            self.db.execute('UPDATE sessions SET status=? WHERE id=?',(status,self.id))
            self._event(status,{}); self.db.commit()
        except Exception: self.db.rollback(); raise

    def checkpoint(self):
        # Export is diagnostic only; callers cannot restore old exported versions.
        row=self._row()
        return {'session_id':self.id,'version':row[3],'used':row[1],
                'budget':row[2],'checksum':row[5],'pending':row[6],'status':row[0]}

    def pending_operation_view_from_host(self):
        """Detached diagnostic of the ORIGINAL frozen view; never a restore/grant.

        Providers can rebind an interrupted operation without querying private
        tables. Editing this return value cannot change the persisted request.
        """
        row=self._row()
        if row[6] is None:return None
        if not self.audit_intact():raise SessionError('corrupt session audit')
        operation=self.db.execute('SELECT view FROM operations WHERE id=? AND session=?',(row[6],self.id)).fetchone()
        if not operation or operation[0] is None:raise SessionError('pending view missing')
        return {'operation_id':row[6],'session_id':self.id,'session_version':row[3],
                'view':json.loads(operation[0]),'authority_restored':False}

    def export_motor_checkpoint(self):
        """Read the already committed motor bytes without serializing it again.

        This is a diagnostic/learning export, NOT a Session resume token. It
        cannot rewind version/budget/goal or supply any host grant. A pending
        effect leaves the pre-effect checkpoint; callers must reconcile first.
        """
        row=self._row()
        if row[6] is not None:raise SessionError('pending operation requires reconciliation before export')
        if hashlib.sha256(row[4]).hexdigest()!=row[5]:raise SessionError('corrupt checkpoint')
        return unpack(row[4])

    @classmethod
    def resume(cls,path,session_id,*,expected_version=None,events=None):
        result=cls(path,session_id,events=events)
        if expected_version is not None and result.version!=expected_version:
            result.close(); raise SessionError('stale checkpoint version')
        try: result.start()
        except Exception: result.close(); raise
        return result

    def step(self, provider):
        """Provider exposes observations + idempotent perform and current gate.

        Holding BEGIN IMMEDIATE serializes a session's decisions across processes.
        The pending operation/budget is committed before invoking the motor.
        A crash replays the same motor checkpoint and operation ID; provider must
        return a recorded receipt without producing another effect.
        """
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self._row()
            if row[0]!='running': raise SessionError('session is not running')
            if row[3]!=self.version: raise SessionError('another process advanced this session')
            if row[6] is None:
                if row[1]>=row[2]:
                    self.db.execute('UPDATE sessions SET status=? WHERE id=?',('exhausted',self.id))
                    self._event('budget_exhausted',{}); self.db.commit()
                    raise SessionError('budget exhausted')
                operation=uuid.uuid4().hex
                view={'observation':provider.observe().tolist(), 'legal':provider.legal_actions(),
                      'context':provider.context_vector(), 'state':provider.state_key(),
                      'description':provider.describe(provider.observe()), 'entity':provider.entity,
                      'bindings':{str(a):provider.request_binding(a) for a in provider.legal_actions()}}
                # Decision inputs are part of the durable intent, not a live
                if callable(getattr(provider,'planning_problem',None)):
                    view['planning_problem']=provider.planning_problem()
                if callable(getattr(provider,'following_plan',None)):
                    view['following_plan']=provider.following_plan()
                if callable(getattr(provider,'verified_completions',None)):
                    view['verified_completions']=provider.verified_completions()
                if callable(getattr(provider,'verified_replans',None)):
                    view['verified_replans']=provider.verified_replans()
                # callback that may change after the effect commits.
                for method in ('deterministic_score','is_information_action'):
                    callback=getattr(provider,method,None)
                    if callable(callback):view[method]={str(a):callback(a) for a in view['legal']}
                self.db.execute('INSERT INTO operations(id,session,state,view,entity) VALUES(?,?,?,?,?)',
                                (operation,self.id,'prepared',json.dumps(view,allow_nan=False),provider.entity))
                self.db.execute('UPDATE sessions SET used=used+1,pending=? WHERE id=?',(operation,self.id))
                self._event('reserved',{'operation':operation,'used':row[1]+1})
            self.db.commit()
        except Exception: self.db.rollback(); raise

        if self.events:self.events('operation_prepared',{'session_id':self.id,'operation_id':self._row()[6]})
        self.db.execute('BEGIN IMMEDIATE')
        before=self._row()
        try:
            if before[0]!='running' or before[3]!=self.version: raise SessionError('session changed')
            operation=before[6]
            view=json.loads(self.db.execute('SELECT view FROM operations WHERE id=?',(operation,)).fetchone()[0])
            session=self
            class GuardedEnvironment:
                def observe(self):
                    import numpy as np
                    return np.array(view['observation'],dtype=np.float32)
                def legal_actions(self): return view['legal']
                def context_vector(self): return view['context']
                def state_key(self): return tuple(view['state'])
                def describe(self,observation): return view['description']
                def planning_problem(self):return view.get('planning_problem')
                def planning_transition(self,state,action):return provider.planning_transition(operation,state,action)
                def following_plan(self):return view.get('following_plan')
                def verified_completions(self):return view.get('verified_completions',[])
                def verified_replans(self):return view.get('verified_replans',[])
                def __getattr__(self,name):
                    if name in ('snapshot','restore'): raise AttributeError(name)
                    if name in ('deterministic_score','is_information_action') and name in view:
                        return lambda action:view[name][str(action)]
                    return getattr(provider,name)
                def step(self,action):
                    row=session.db.execute('SELECT entity,action,request FROM operations WHERE id=?',(operation,)).fetchone()
                    entity=provider.entity
                    request=json.dumps(provider.request_binding(action),sort_keys=True,allow_nan=False)
                    if (entity!=view['entity'] or provider.request_binding(action)!=view['bindings'].get(str(action))):
                        raise SessionError('pending entity or request binding changed')
                    if row[1] is not None and (row[0],row[1],row[2])!=(entity,action,request):
                        raise SessionError('replayed operation binding changed')
                    session.db.execute('UPDATE operations SET entity=?,action=?,request=? WHERE id=?',
                                       (entity,action,request,operation))
                    # Native provider checks CURRENT policy inside its effect transaction.
                    return provider.perform(operation,action)
            result=self.engine.step(GuardedEnvironment())
            if self.events:self.events('checkpoint_pending',{'session_id':self.id,'operation_id':operation})
            raw=pack(self.engine.snapshot())
            result_json=json.dumps(result,sort_keys=True,allow_nan=False)
            self.db.execute('UPDATE operations SET state=?,result=? WHERE id=?',('verified',result_json,operation))
            self.db.execute('UPDATE sessions SET checkpoint=?,checksum=?,version=version+1,pending=NULL WHERE id=?',
                            (raw,hashlib.sha256(raw).hexdigest(),self.id))
            self._event('verified_step',{'operation':operation,'motor_step':self.engine.steps,
                                        'result_hash':hashlib.sha256(result_json.encode()).hexdigest()})
            self.db.commit(); self.version+=1
            return result
        except Exception:
            self.db.rollback(); self.engine=Engine.restore(unpack(before[4])); raise

    def complete(self, provider):
        # Goal completion is an independent provider verdict, never a text claim.
        if self._row()[6] is not None or not provider.verify_goal(json.loads(self._row()[7])):
            raise SessionError('goal not verified or pending operation')
        self._status('completed')

    def abandon_pending_from_host(self,*,fence):
        """Clear a pending decision ONLY after native cancellation fences late calls.

        `fence` is a trusted host callback, NOT an actor report/JSON claim. It must
        atomically record a durable tombstone in the resource's effect transaction
        or return applied/unknown. Absence of a receipt is NOT proof of no effect.
        Budget already reserved is never refunded; prior learning is preserved.
        """
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self._row(); operation=row[6]
            if operation is None:
                self.db.commit(); return {'state':'no_pending_operation'}
            record=self.db.execute('SELECT entity FROM operations WHERE id=? AND session=?',
                                   (operation,self.id)).fetchone()
            if not record: raise SessionError('pending operation record absent')
            verdict=fence(operation,record[0])
            if (type(verdict) is not dict or verdict.get('operation_id')!=operation
                    or verdict.get('entity')!=record[0]):
                raise SessionError('native fence identity mismatch')
            if verdict.get('state')!='fenced_not_applied' or verdict.get('fenced') is not True:
                self._event('reconciliation_required',{'operation':operation,'verdict':verdict})
                self.db.commit()
                return {'state':'needs_reconciliation','operation_id':operation}
            self.db.execute('UPDATE operations SET state=?,result=? WHERE id=? AND session=?',
                            ('fenced_cancelled',json.dumps(verdict,allow_nan=False),operation,self.id))
            self.db.execute('UPDATE sessions SET pending=NULL,version=version+1 WHERE id=?',(self.id,))
            self._event('pending_fenced_cancelled',{'operation':operation,'verdict':verdict,
                                                  'used_preserved':row[1]})
            self.db.commit(); self.version=row[3]+1
            # Another process may have advanced the last checkpoint before this
            # host operation. Reload it, never revive an old local trajectory.
            self._load()
            return {'state':'abandoned_without_effect','operation_id':operation}
        except Exception: self.db.rollback(); raise

    def run(self,provider,*,max_steps=None):
        """Bounded loop; independent native goal check, not a success declaration."""
        remaining=self._row()[2]-self._row()[1]
        limit=remaining if max_steps is None else max_steps
        if type(limit) is not int or limit<0: raise ValueError('invalid run budget')
        results=[]
        for _ in range(min(limit,remaining)):
            if provider.verify_goal(json.loads(self._row()[7])):
                self.complete(provider); break
            if self._row()[0]!='running': break
            results.append(self.step(provider))
            if results[-1].get('actual_evidence',{}).get('abstained'):
                self.pause();break
        if self._row()[0]=='running' and provider.verify_goal(json.loads(self._row()[7])):
            self.complete(provider)
        return {'checkpoint':self.checkpoint(),'results':results}

    def close(self): self.db.close()

    def operation_receipts_from_host(self,*,limit=100):
        """Read committed history; data/provenance only, never a resume grant."""
        if type(limit) is not int or not 1<=limit<=10000:raise ValueError('history limit')
        rows=self.db.execute('SELECT id,entity,state,action,result FROM operations WHERE session=? ORDER BY rowid DESC LIMIT ?',(self.id,limit)).fetchall()
        return [{'operation_id':r[0],'entity':r[1],'state':r[2],'action':r[3],'result':json.loads(r[4]) if r[4] else None} for r in rows]


def create_session(path,session_id,*,budget=100,goal=None,events=None,**engine_options):
    return Session(path,session_id,Engine(**engine_options),budget=budget,goal=goal,events=events)
