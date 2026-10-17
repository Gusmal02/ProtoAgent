"""Host-owned role coordination, bounded delegation and aggregate effect budget.

This is a capability boundary, not role intelligence or a plugin sandbox. Only
the host registers members, changes policy and admits independently verified
artifacts. Actor-facing handles expose narrowed role methods/opaque grants.
Providers MUST persist effect+receipt atomically for each operation ID; otherwise
replaying after the coordinator crashes can duplicate an external side effect.
"""
import hashlib
import json
import math
import secrets
import sqlite3
import time
import threading
from functools import wraps
from types import MappingProxyType

_ROLE_OPERATIONS={
    'Observer':frozenset(('observe',)),
    'Investigator':frozenset(('observe','probe')),
    'Builder':frozenset(('observe','draft')),
    'Auditor':frozenset(('observe','challenge')),
    'Operator':frozenset(('observe','execute')),
    'Architect':frozenset(('observe','delegate','compose')),
    'Supervisor':frozenset(('observe','schedule','cancel')),
}
# Explicit matched baseline: one motor may use the SAME published tool kinds.
# It gains no host-only policy/admission method; scopes and budget still apply.
_ROLE_OPERATIONS['Solo']=frozenset().union(*_ROLE_OPERATIONS.values())
ROLE_OPERATIONS=MappingProxyType(_ROLE_OPERATIONS)
FIRST_ORDER=frozenset(('Observer','Investigator','Builder','Auditor','Operator'))

class TeamError(RuntimeError): pass
class ControlRejected(TeamError):
    """Authorized tool request whose domain preconditions were not satisfied."""

def _identifier(value):
    if type(value) is not str or not 1<=len(value)<=128 or not value.strip():
        raise TeamError('invalid identity')
    return value

def _ttl(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=3600:
        raise TeamError('invalid grant TTL')
    return value

def _serialized(method):
    @wraps(method)
    def guarded(self,*args,**kwargs):
        with self._lock: return method(self,*args,**kwargs)
    return guarded

def _json(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(raw.encode())>65536: raise TeamError('message exceeds byte budget')
    return raw

def _digest(value): return hashlib.sha256(_json(value).encode()).hexdigest()

class TeamCoordinator:
    def __init__(self,path,team_id,*,budget=500,clock=None,events=None):
        if type(budget) is not int or not 1<=budget<=1000000: raise ValueError('invalid aggregate budget')
        self.id=_identifier(team_id); self.clock=clock or time.time;self.events=events
        self._lock=threading.RLock()
        self.db=sqlite3.connect(path,timeout=10,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY,budget INTEGER NOT NULL,
            used INTEGER NOT NULL,revision INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS members(team TEXT,actor TEXT,role TEXT,session TEXT,
            PRIMARY KEY(team,actor),UNIQUE(team,session));
        CREATE TABLE IF NOT EXISTS grants(hash TEXT PRIMARY KEY,team TEXT,actor TEXT,
            role TEXT,scopes TEXT,ceiling TEXT,expires REAL,revision INTEGER,parent TEXT,revoked INTEGER);
        CREATE TABLE IF NOT EXISTS team_operations(team TEXT,id TEXT,actor TEXT,binding TEXT,
            state TEXT,result TEXT,PRIMARY KEY(team,id));
        CREATE TABLE IF NOT EXISTS messages(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT,sender TEXT,recipient TEXT,entity TEXT,revision INTEGER,payload TEXT);
        CREATE TABLE IF NOT EXISTS artifacts(team TEXT,hash TEXT,owner TEXT,manifest TEXT,
            status TEXT,revision INTEGER,verification TEXT,entity TEXT,PRIMARY KEY(team,hash));
        CREATE TABLE IF NOT EXISTS agenda(team TEXT,id TEXT,owner TEXT,worker TEXT,entity TEXT,
            goal TEXT,state TEXT,revision INTEGER,PRIMARY KEY(team,id));
        CREATE TABLE IF NOT EXISTS grant_delivery(team TEXT,operation TEXT,child TEXT,token TEXT,
            PRIMARY KEY(team,operation));
        CREATE TABLE IF NOT EXISTS team_fences(team TEXT,id TEXT,entity TEXT,PRIMARY KEY(team,id));
        CREATE TABLE IF NOT EXISTS control_intents(team TEXT,id TEXT,entity TEXT,kind TEXT,PRIMARY KEY(team,id));
        CREATE TABLE IF NOT EXISTS operation_catalog(team TEXT,id TEXT,actor TEXT,entity TEXT,revision INTEGER,kind TEXT,binding TEXT,PRIMARY KEY(team,id));
        CREATE TABLE IF NOT EXISTS durable_deliveries(team TEXT,id TEXT,binding TEXT,seq INTEGER,origin TEXT,recipient TEXT,PRIMARY KEY(team,id));
        CREATE TABLE IF NOT EXISTS delivery_acks(team TEXT,actor TEXT,seq INTEGER,digest TEXT,PRIMARY KEY(team,actor,seq));
        ''')
        columns={row[1] for row in self.db.execute('PRAGMA table_info(artifacts)')}
        if 'entity' not in columns:
            # Old candidates carry no context evidence: migration must NOT make
            # them usable in all entities. Require fresh drafting/verification.
            self.db.execute('ALTER TABLE artifacts ADD COLUMN entity TEXT')
            self.db.execute("UPDATE artifacts SET status='obsolete' WHERE entity IS NULL")
        self.db.execute('INSERT OR IGNORE INTO teams VALUES(?,?,0,0)',(team_id,budget))
        self.db.commit()
        if self.status()['budget']!=budget:
            self.db.close(); raise TeamError('cannot recreate team with a different budget')

    @_serialized
    def status(self):
        budget,used,revision=self.db.execute('SELECT budget,used,revision FROM teams WHERE id=?',(self.id,)).fetchone()
        return {'budget':budget,'used':used,'revision':revision}

    def _charge(self):
        status=self.status()
        if status['used']>=status['budget']: raise TeamError('aggregate budget exhausted')
        self.db.execute('UPDATE teams SET used=used+1 WHERE id=?',(self.id,))

    @_serialized
    def register_member_from_host(self,actor,role,session_id):
        _identifier(actor); _identifier(session_id)
        if role not in ROLE_OPERATIONS: raise TeamError('invalid member')
        self.db.execute('INSERT INTO members VALUES(?,?,?,?)',(self.id,actor,role,session_id)); self.db.commit()

    def _issue(self,actor,scopes,ceiling,expires,parent=None):
        member=self.db.execute('SELECT role FROM members WHERE team=? AND actor=?',(self.id,actor)).fetchone()
        if not member: raise TeamError('unknown member')
        if not scopes or len(scopes)>256: raise TeamError('invalid scope')
        for scope in scopes: _identifier(scope)
        if set(ceiling)-FIRST_ORDER: raise TeamError('invalid delegation ceiling')
        if ceiling and member[0] not in ('Architect','Solo'):
            raise TeamError('role cannot receive delegation authority')
        token=secrets.token_urlsafe(32); fingerprint=hashlib.sha256(token.encode()).hexdigest()
        self.db.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,0)',
            (fingerprint,self.id,actor,member[0],_json(sorted(set(scopes))),_json(sorted(set(ceiling))),
             expires,self.status()['revision'],parent))
        return token

    @_serialized
    def grant_from_host(self,actor,scopes,*,ttl=60,delegation_roles=()):
        _ttl(ttl)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            token=self._issue(actor,scopes,delegation_roles,self.clock()+ttl)
            self.db.commit(); return token
        except Exception: self.db.rollback(); raise

    @_serialized
    def _grant(self,token):
        if type(token) is not str or not 16<=len(token)<=256: raise TeamError('invalid grant')
        key=hashlib.sha256(token.encode()).hexdigest(); seen=set(); leaf=None
        while key:
            if key in seen or len(seen)>=4: raise TeamError('delegation chain invalid')
            seen.add(key)
            row=self.db.execute('SELECT actor,role,scopes,ceiling,expires,revision,parent,revoked FROM grants WHERE hash=? AND team=?',
                                (key,self.id)).fetchone()
            if not row or row[7] or row[4]<=self.clock() or row[5]!=self.status()['revision']:
                raise TeamError('grant expired, revoked or obsolete')
            if leaf is None: leaf=row
            key=row[6]
        return leaf

    def _authorize(self,token,operation,entity):
        grant=self._grant(token)
        if operation not in ROLE_OPERATIONS[grant[1]] or entity not in json.loads(grant[2]):
            raise TeamError('role or entity outside capability')
        return grant

    @_serialized
    def delegate(self,token,child,scopes,*,ttl=30):
        _ttl(ttl)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            parent=self._grant(token)
            role=self.db.execute('SELECT role FROM members WHERE team=? AND actor=?',(self.id,child)).fetchone()
            if (parent[1] not in ('Architect','Solo') or not role or role[0] not in json.loads(parent[3])
                    or not scopes or not set(scopes)<=set(json.loads(parent[2])) or child==parent[0]):
                raise TeamError('delegation exceeds host ceiling')
            self._charge()
            new=self._issue(child,scopes,(),min(self.clock()+ttl,parent[4]),hashlib.sha256(token.encode()).hexdigest())
            self.db.commit(); return new
        except Exception: self.db.rollback(); raise

    @_serialized
    def revoke_from_host(self,token):
        self.db.execute('UPDATE grants SET revoked=1 WHERE hash=? AND team=?',
                        (hashlib.sha256(token.encode()).hexdigest(),self.id)); self.db.commit()

    @_serialized
    def revise_policy_from_host(self):
        # Old grants AND prior tool admissions become obsolete together.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('UPDATE teams SET revision=revision+1 WHERE id=?',(self.id,))
            self.db.execute('UPDATE artifacts SET status=? WHERE team=?',('obsolete',self.id))
            self.db.commit()
        except Exception: self.db.rollback(); raise

    @_serialized
    def send(self,token,recipient,entity,payload):
        raw=_json(payload)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            grant=self._authorize(token,'observe',entity)
            if not self.db.execute('SELECT 1 FROM members WHERE team=? AND actor=?',(self.id,recipient)).fetchone():
                raise TeamError('recipient not registered')
            self._charge()
            # Sender and policy version are host fields, not claims in the payload.
            self.db.execute('INSERT INTO messages(team,sender,recipient,entity,revision,payload) VALUES(?,?,?,?,?,?)',
                            (self.id,grant[0],recipient,entity,self.status()['revision'],raw))
            self.db.commit()
        except Exception: self.db.rollback(); raise

    @_serialized
    def receive(self,token,entity,*,after=0,limit=50):
        grant=self._authorize(token,'observe',entity)
        if type(after) is not int or type(limit) is not int or not 1<=limit<=100: raise TeamError('invalid mailbox bound')
        return [dict(seq=row[0],sender=row[1],revision=row[2],entity=entity,payload=json.loads(row[3])) for row in
            self.db.execute('SELECT seq,sender,revision,payload FROM messages WHERE team=? AND recipient=? AND entity=? AND seq>? ORDER BY seq LIMIT ?',
                            (self.id,grant[0],entity,after,limit))]

    @_serialized
    def publish_delivery(self,token,entity,delivery_id,recipient,*,origin,kind,payload):
        from .deliveries import publish
        return publish(self,token,entity,delivery_id,recipient,origin,kind,payload)

    @_serialized
    def acknowledge_delivery(self,token,entity,seq):
        from .deliveries import acknowledge
        return acknowledge(self,token,entity,seq)

    @_serialized
    def inspect_artifact(self,token,entity,identity):
        self._authorize(token,'observe',entity)
        row=self.db.execute('SELECT owner,manifest,status,revision FROM artifacts WHERE team=? AND entity=? AND hash=?',(self.id,entity,identity)).fetchone()
        if not row:raise TeamError('artifact absent in entity scope')
        return {'identity':identity,'owner':row[0],'manifest':json.loads(row[1]),'status':row[2],'entity':entity,'revision':row[3],'current':row[3]==self.status()['revision']}

    @_serialized
    def operation_receipt(self,token,entity,identity):
        self._authorize(token,'observe',entity)
        row=self.db.execute('SELECT c.actor,c.revision,c.kind,o.state,o.result FROM operation_catalog c JOIN team_operations o ON c.team=o.team AND c.id=o.id WHERE c.team=? AND c.entity=? AND c.id=?',(self.id,entity,identity)).fetchone()
        return None if not row else {'operation_id':identity,'entity':entity,'actor':row[0],'revision':row[1],'kind':row[2],'state':row[3],'result':json.loads(row[4]) if row[4] else None}

    @_serialized
    def draft(self,token,entity,manifest):
        raw=_json(manifest)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            grant=self._authorize(token,'draft',entity)
            identity=_digest({'team':self.id,'owner':grant[0],'entity':entity,'revision':self.status()['revision'],'manifest':manifest})
            self._charge()
            self.db.execute('INSERT OR IGNORE INTO artifacts(team,hash,owner,manifest,status,revision,verification,entity) VALUES(?,?,?,?,?,?,NULL,?)',
                            (self.id,identity,grant[0],raw,'candidate',self.status()['revision'],entity))
            self.db.commit(); return identity
        except Exception: self.db.rollback(); raise

    @_serialized
    def admit_from_host_verifier(self,identity,*,verify):
        """Host-only callback to an independent verifier, never an actor report."""
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT manifest,revision,entity,owner FROM artifacts WHERE team=? AND hash=?',(self.id,identity)).fetchone()
            if not row or row[1]!=self.status()['revision'] or row[2] is None:
                raise TeamError('artifact stale, absent or lacks entity evidence')
            result=verify({'identity':identity,'manifest':json.loads(row[0]),
                           'entity':row[2],'owner':row[3],'revision':row[1]})
            if type(result) is not dict or result.get('accepted') is not True:
                raise TeamError('independent verifier rejected artifact')
            self.db.execute('UPDATE artifacts SET status=?,verification=? WHERE team=? AND hash=?',
                            ('active',_json(result),self.id,identity)); self.db.commit()
        except Exception: self.db.rollback(); raise

    @_serialized
    def perform(self,token,entity,operation_id,kind,payload,execute,*,artifact=None,agenda=None,prepare=None):
        _identifier(operation_id); _identifier(entity)
        if artifact is not None and (type(artifact) is not str or len(artifact)!=64
                or any(character not in '0123456789abcdef' for character in artifact)):
            raise TeamError('invalid artifact identity')
        if agenda is not None:_identifier(agenda)
        binding=_digest({'entity':entity,'kind':kind,'payload':payload,'artifact':artifact,'agenda':agenda})
        self.db.execute('BEGIN IMMEDIATE')
        try:
            grant=self._authorize(token,kind,entity)
            if self.db.execute('SELECT 1 FROM team_fences WHERE team=? AND id=?',(self.id,operation_id)).fetchone():
                raise TeamError('operation durably fenced')
            row=self.db.execute('SELECT actor,binding,state,result FROM team_operations WHERE team=? AND id=?',
                                (self.id,operation_id)).fetchone()
            if row and row[:2]!=(grant[0],binding): raise TeamError('operation identity collision')
            if row and row[2]=='verified':
                self.db.commit(); return json.loads(row[3])
            if row is None:
                status=self.status()
                if status['used']>=status['budget']: raise TeamError('aggregate budget exhausted')
                self.db.execute('INSERT INTO team_operations VALUES(?,?,?,?,?,NULL)',
                                (self.id,operation_id,grant[0],binding,'prepared'))
                self.db.execute('INSERT INTO operation_catalog VALUES(?,?,?,?,?,?,?)',(self.id,operation_id,grant[0],entity,self.status()['revision'],kind,binding))
                self.db.execute('UPDATE teams SET used=used+1 WHERE id=?',(self.id,))
            self.db.commit()
        except Exception: self.db.rollback(); raise
        # Host-owned preparation can perform separately durable suboperations.
        # Parent reservation above is durable; authority is rechecked below.
        if prepare is not None:prepare(operation_id)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._authorize(token,kind,entity)
            if self.db.execute('SELECT 1 FROM team_fences WHERE team=? AND id=?',(self.id,operation_id)).fetchone():
                raise TeamError('operation durably fenced during preparation')
            if agenda is not None:
                task=self.db.execute('SELECT worker,entity,state,revision FROM agenda WHERE team=? AND id=?',
                    (self.id,agenda)).fetchone()
                if task!=(grant[0],entity,'scheduled',self.status()['revision']):
                    raise TeamError('agenda cancelled, stale or assigned to another actor')
            if artifact is not None:
                admitted=self.db.execute('SELECT status,revision,entity FROM artifacts WHERE team=? AND hash=?',(self.id,artifact)).fetchone()
                if admitted!=('active',self.status()['revision'],entity):
                    raise TeamError('artifact not currently admitted for this entity')
            # Re-read after acquiring lock: another process may have finished it.
            row=self.db.execute('SELECT actor,binding,state,result FROM team_operations WHERE team=? AND id=?',
                                (self.id,operation_id)).fetchone()
            if row[:2]!=(grant[0],binding): raise TeamError('operation changed')
            if row[2]=='verified': result=json.loads(row[3])
            else:
                result=execute(operation_id)
                self.db.execute('UPDATE team_operations SET state=?,result=? WHERE team=? AND id=?',
                                ('verified',_json(result),self.id,operation_id))
            self.db.commit()
            if self.events:self.events('team_effect_committed',{'operation_id':operation_id,'entity':entity,'kind':kind})
            return result
        except Exception: self.db.rollback(); raise

    @_serialized
    def close(self): self.db.close()

    @_serialized
    def fence_native_from_host(self,operation_id,entity,*,fence):
        """Resolve a prepared native intent only with its durable native fence.

        Receipt absence alone is never sufficient. Callback is trusted host
        infrastructure, not a claim supplied by an actor. Credit is preserved.
        """
        _identifier(operation_id);_identifier(entity)
        original=self.db.execute('SELECT actor,binding,state FROM team_operations WHERE team=? AND id=?',(self.id,operation_id)).fetchone()
        catalog=self.db.execute('SELECT entity FROM operation_catalog WHERE team=? AND id=?',(self.id,operation_id)).fetchone()
        if not original or catalog!=(entity,):raise TeamError('native intent absent or context mismatch')
        if self.db.execute('SELECT 1 FROM control_intents WHERE team=? AND id=?',(self.id,operation_id)).fetchone():raise TeamError('use control fence for control intents')
        if original[2]=='verified':return {'state':'applied_or_verified','operation_id':operation_id,'entity':entity,'fenced':False}
        verdict=fence(operation_id,entity)
        if type(verdict) is not dict or verdict.get('operation_id')!=operation_id or verdict.get('entity')!=entity:raise TeamError('native fence identity mismatch')
        if verdict.get('state')!='fenced_not_applied' or verdict.get('fenced') is not True:return {'state':'needs_reconciliation','operation_id':operation_id,'entity':entity,'fenced':False}
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current=self.db.execute('SELECT actor,binding,state FROM team_operations WHERE team=? AND id=?',(self.id,operation_id)).fetchone()
            if current[:2]!=original[:2]:raise TeamError('native intent changed')
            if current[2]=='verified':self.db.commit();return {'state':'verified_during_reconciliation','operation_id':operation_id,'entity':entity,'fenced':False}
            self.db.execute('INSERT OR IGNORE INTO team_fences VALUES(?,?,?)',(self.id,operation_id,entity))
            self.db.execute("UPDATE team_operations SET state='fenced_cancelled',result=? WHERE team=? AND id=?",(_json(verdict),self.id,operation_id))
            self.db.commit();return verdict
        except BaseException:self.db.rollback();raise

    @_serialized
    def perform_control(self,token,entity,operation_id,request):
        from .control_effects import perform_control
        return perform_control(self,token,entity,operation_id,request)

    @_serialized
    def record_control_rejection_from_host(self,token,entity,operation_id,request,reason):
        """Native rejected receipt; permission errors never enter this path."""
        permission='observe' if request['kind']=='message' else request['kind']
        binding=_digest({'entity':entity,'request':request})
        self.db.execute('BEGIN IMMEDIATE')
        try:
            grant=self._authorize(token,permission,entity)
            row=self.db.execute('SELECT actor,binding,state,result FROM team_operations WHERE team=? AND id=?',
                (self.id,operation_id)).fetchone()
            if not row or row[:2]!=(grant[0],binding):raise TeamError('rejection intent mismatch')
            if row[2]=='verified':self.db.commit();return json.loads(row[3])
            if row[2]!='prepared' or not self.db.execute('SELECT 1 FROM control_intents WHERE team=? AND id=?',
                (self.id,operation_id)).fetchone():raise TeamError('rejection intent absent or fenced')
            result={'kind':request['kind'],'rejected':True,'reason':str(reason),'effect':None}
            self.db.execute('UPDATE team_operations SET state=?,result=? WHERE team=? AND id=?',
                ('verified',_json(result),self.id,operation_id));self.db.commit();return result
        except Exception:self.db.rollback();raise

    @_serialized
    def delivered_grant_from_host(self,operation_id,child):
        """Trusted host delivery; never return credentials in a provider trace."""
        row=self.db.execute('SELECT token FROM grant_delivery WHERE team=? AND operation=? AND child=?',
            (self.id,operation_id,child)).fetchone()
        if not row or self._grant(row[0])[0]!=child:raise TeamError('grant delivery absent or invalid')
        return row[0]

    @_serialized
    def fence_control_from_host(self,operation_id,entity):
        """Only atomic control effects: ordinary prepared callbacks are unknown."""
        _identifier(operation_id);_identifier(entity)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT state,result FROM team_operations WHERE team=? AND id=?',
                (self.id,operation_id)).fetchone()
            if row and row[0]=='verified':
                outcome=json.loads(row[1])
                if isinstance(outcome,dict) and outcome.get('rejected') is True:
                    self.db.commit();return {'operation_id':operation_id,'entity':entity,'state':'rejected',
                        'effect_applied':False,'fenced':False}
                self.db.commit();return {'operation_id':operation_id,'entity':entity,'state':'applied','fenced':False}
            if row and not self.db.execute('SELECT 1 FROM control_intents WHERE team=? AND id=? AND entity=?',
                    (self.id,operation_id,entity)).fetchone():
                self.db.commit();return {'operation_id':operation_id,'entity':entity,'state':'unknown','fenced':False}
            self.db.execute('INSERT OR IGNORE INTO team_fences VALUES(?,?,?)',(self.id,operation_id,entity))
            if row:self.db.execute('UPDATE team_operations SET state=? WHERE team=? AND id=?',
                ('fenced_cancelled',self.id,operation_id))
            self.db.commit();return {'operation_id':operation_id,'entity':entity,'state':'fenced_not_applied','fenced':True}
        except Exception:self.db.rollback();raise

class RoleProvider:
    """Connects an actual Session/motor to a domain provider through the gate.

    Domain must declare action_kind(action). The same provider/tools are offered
    to matched single-agent and team arms; budget is shared at coordinator level.
    Tokens and coordinator are never part of Engine.snapshot or recovered memory.
    """
    def __init__(self,coordinator,token,provider):
        self.coordinator=coordinator; self.token=token; self.provider=provider
        self.entity=provider.entity
    def __getattr__(self,name): return getattr(self.provider,name)
    def legal_actions(self):
        grant=self.coordinator._grant(self.token)
        if self.entity not in json.loads(grant[2]): raise TeamError('entity outside role scope')
        # Filter by published capabilities, not by whether an action solves the task.
        # The same role gate still rejects direct out-of-capability attempts.
        return [action for action in self.provider.legal_actions()
                if self.provider.action_kind(action) in ROLE_OPERATIONS[grant[1]]]
    def request_binding(self,action):
        grant=self.coordinator._grant(self.token)
        required=getattr(self.provider,'required_artifact',None)
        agenda=getattr(self.provider,'required_agenda',None)
        control=getattr(self.provider,'control_request',None)
        return {'actor':grant[0],'role':grant[1],'entity':self.entity,
                'kind':self.provider.action_kind(action),
                'native_request':self.provider.request_binding(action),
                'control_request':control(action) if callable(control) else None,
                'agenda':agenda(action) if callable(agenda) else None,
                'artifact':required(action) if callable(required) else None}
    def perform(self,operation_id,action):
        kind=self.provider.action_kind(action)
        binding=self.request_binding(action)
        control=getattr(self.provider,'control_request',None)
        request=control(action) if callable(control) else None
        if request is not None:
            if request.get('kind')!=kind and not (kind=='observe' and request.get('kind')=='message'):
                raise TeamError('control/tool kind mismatch')
            try:result=self.coordinator.perform_control(self.token,self.entity,operation_id,request)
            except ControlRejected as error:
                result=self.coordinator.record_control_rejection_from_host(self.token,self.entity,operation_id,request,error)
            return self.provider.control_outcome(action,result)
        def native(identity):
            obs,reward,terminal,evidence=self.provider.perform(identity,action)
            return [obs.tolist(),float(reward),bool(terminal),evidence]
        result=self.coordinator.perform(self.token,self.entity,operation_id,kind,
                    binding,native,artifact=binding['artifact'],agenda=binding['agenda'],
                    prepare=(lambda identity:self.provider.prepare_action(identity,action))
                    if callable(getattr(self.provider,'prepare_action',None)) else None)
        import numpy as np
        return np.array(result[0],dtype=np.float32),result[1],result[2],result[3]

class RoleSession:
    """Host-created role actor with a REAL independent Session and motor state.

    This facade does not supply a role's domain implementation, a task solution
    or a supervisor strategy. Explicit tools/providers still implement those.
    No grant is exported in checkpoint or inferred from recovered memory.
    """
    def __init__(self,coordinator,actor,session,grant):
        member=coordinator.db.execute('SELECT role,session FROM members WHERE team=? AND actor=?',
                                     (coordinator.id,actor)).fetchone()
        assigned=coordinator._grant(grant)
        if not member or member[1]!=session.id or assigned[:2]!=(actor,member[0]):
            raise TeamError('grant/member/session binding mismatch')
        self.coordinator=coordinator; self.actor=actor; self.role=member[0]
        self.session=session; self._grant=grant

    @classmethod
    def create_from_host(cls,coordinator,path,actor,role,scopes,*,goal,budget=100,
                         seed=881,config=None,ttl=60,delegation_roles=(),events=None):
        from .session import create_session
        _identifier(actor)
        if coordinator.db.execute('SELECT 1 FROM members WHERE team=? AND actor=?',
                                  (coordinator.id,actor)).fetchone():
            raise TeamError('member already exists; resume its session')
        # No domain-specific filename or hidden task route; stable identity only.
        session_id='role-'+_digest({'team':coordinator.id,'actor':actor})[:32]
        session=create_session(path,session_id,budget=budget,goal=goal,seed=seed,config=config,events=events)
        try:
            coordinator.register_member_from_host(actor,role,session_id)
            grant=coordinator.grant_from_host(actor,scopes,ttl=ttl,delegation_roles=delegation_roles)
            result=cls(coordinator,actor,session,grant); session.start(); return result
        except Exception:
            # Persisted partial registration may be inspected by the host; do not
            # silently delete a durable journal or claim a cross-DB transaction.
            session.close(); raise

    @classmethod
    def resume_from_host(cls,coordinator,path,actor,grant,*,expected_version=None,events=None):
        from .session import Session
        member=coordinator.db.execute('SELECT session FROM members WHERE team=? AND actor=?',
                                     (coordinator.id,actor)).fetchone()
        if not member: raise TeamError('member not registered')
        # Verify new host authority BEFORE loading/resuming the old trajectory.
        if coordinator._grant(grant)[0]!=actor: raise TeamError('grant actor mismatch')
        session=Session.resume(path,member[0],expected_version=expected_version,events=events)
        try: return cls(coordinator,actor,session,grant)
        except Exception: session.close(); raise

    def step(self,provider):
        result=self.session.step(RoleProvider(self.coordinator,self._grant,provider))
        return {'actor':self.actor,'role':self.role,'result':result,
                'session':self.session.checkpoint(),'aggregate':self.coordinator.status()}

    def send(self,recipient,entity,payload):
        return self.coordinator.send(self._grant,recipient,entity,payload)

    def publish_delivery(self,delivery_id,recipient,entity,*,origin,kind,payload):
        return self.coordinator.publish_delivery(self._grant,entity,delivery_id,recipient,origin=origin,kind=kind,payload=payload)

    def acknowledge_delivery(self,entity,seq):
        return self.coordinator.acknowledge_delivery(self._grant,entity,seq)

    def inspect_artifact(self,entity,identity):return self.coordinator.inspect_artifact(self._grant,entity,identity)
    def operation_receipt(self,entity,identity):return self.coordinator.operation_receipt(self._grant,entity,identity)

    def receive(self,entity,*,after=0,limit=50):
        return self.coordinator.receive(self._grant,entity,after=after,limit=limit)

    def draft(self,entity,manifest):
        return self.coordinator.draft(self._grant,entity,manifest)

    def delegate(self,child,scopes,*,ttl=30):
        return self.coordinator.delegate(self._grant,child,scopes,ttl=ttl)

    def checkpoint(self):
        return {'actor':self.actor,'role':self.role,'session':self.session.checkpoint(),
                'aggregate':self.coordinator.status()}

    def pending_operation_view_from_host(self):
        return self.session.pending_operation_view_from_host()

    def complete(self,provider):
        self.coordinator._authorize(self._grant,'observe',provider.entity)
        self.session.complete(RoleProvider(self.coordinator,self._grant,provider))

    def close(self): self.session.close()
