"""Host-governed durable work contracts; no planner or security oracle."""
import json,sqlite3
from .team import TeamError,_json,_digest,_identifier

class Collaboration:
    def __init__(self,team,path,*,reviewers):
        self.team=team;self.reviewers=tuple(reviewers)
        if not self.reviewers:raise ValueError('independent reviewer required')
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS tasks(entity TEXT,id TEXT,body TEXT,PRIMARY KEY(entity,id)); CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,binding TEXT,result TEXT);')
        policy={'team':team.id,'reviewers':sorted(self.reviewers)}
        self.db.execute('CREATE TABLE IF NOT EXISTS config(id INTEGER PRIMARY KEY,body TEXT)')
        old=self.db.execute('SELECT body FROM config WHERE id=1').fetchone()
        if old and json.loads(old[0])!=policy:
            self.db.close()
            raise TeamError('collaboration policy changed')
        self.db.execute('INSERT OR IGNORE INTO config VALUES(1,?)',(_json(policy),));self.db.commit()
    def _load(self,entity,identity):
        row=self.db.execute('SELECT body FROM tasks WHERE entity=? AND id=?',(entity,identity)).fetchone()
        if not row:raise TeamError('task absent in scope')
        return json.loads(row[0])
    def inspect(self,token,entity,task_id):
        with self.team._lock:
            self.team._authorize(token,'observe',entity)
            return self._load(entity,task_id)
    def command(self,token,entity,operation_id,action,task_id,payload):
        _identifier(operation_id);_identifier(task_id);_identifier(entity)
        if type(payload) is not dict:raise TeamError('payload must be object')
        # Derive identity/role from trusted grant, never from payload.
        with self.team._lock:
            actor,role,*_=self.team._authorize(token,'observe',entity)
            revision=self.team.status()['revision']
            binding=_digest([entity,task_id,action,payload,actor,revision])
            def effect(_):
                self.db.execute('BEGIN IMMEDIATE')
                try:
                    old=self.db.execute('SELECT binding,result FROM receipts WHERE id=?',(operation_id,)).fetchone()
                    if old:
                        if old[0]!=binding:raise TeamError('collaboration identity collision')
                        self.db.commit();return json.loads(old[1])
                    if action=='request':
                        if role not in ('Architect','Supervisor'):raise TeamError('request authority required')
                        if set(payload)!= {'goal','owner','acceptance','dependencies'}:raise TeamError('request schema')
                        if not isinstance(payload['goal'],str) or not payload['goal'] or not isinstance(payload['acceptance'],str) or not payload['acceptance']:raise TeamError('empty contract')
                        if not isinstance(payload['dependencies'],list) or len(payload['dependencies'])>100:raise TeamError('dependency schema')
                        if not self.team.db.execute('SELECT 1 FROM members WHERE team=? AND actor=?',(self.team.id,payload['owner'])).fetchone():raise TeamError('unknown owner')
                        if self.db.execute('SELECT 1 FROM tasks WHERE entity=? AND id=?',(entity,task_id)).fetchone():raise TeamError('task exists')
                        for dep in payload['dependencies']:
                            _identifier(dep)
                            self._load(entity,dep)
                        task={**payload,'id':task_id,'entity':entity,'revision':revision,'state':'requested','artifact':None,'history':[]}
                    else:
                        task=self._load(entity,task_id)
                        if task['revision']!=revision:raise TeamError('obsolete task contract')
                        owner=actor==task['owner']
                        if action in ('accept','reject'):
                            if not owner or task['state'] not in ('requested','blocked'):raise TeamError('owner/state mismatch')
                            if set(payload):raise TeamError('unexpected decision payload')
                            if action=='accept':
                                for dep in task['dependencies']:
                                    parent=self._load(entity,dep)
                                    if parent['state']!='approved' or parent['revision']!=revision:raise TeamError('dependency not accepted')
                            task['state']='accepted' if action=='accept' else 'rejected'
                        elif action=='submit':
                            if not owner or task['state']!='accepted':raise TeamError('submission authority/state')
                            if set(payload)!= {'artifact','evidence'}:raise TeamError('submission schema')
                            self._evidence(payload);self._hash(payload['artifact'])
                            task.update(state='submitted',artifact=payload['artifact'],evidence=payload['evidence'])
                        elif action=='review':
                            if actor not in self.reviewers or owner or task['state']!='submitted':raise TeamError('independent reviewer required')
                            if set(payload)!= {'artifact','evidence','verdict'} or payload['artifact']!=task['artifact'] or payload['verdict'] not in ('pass','fail'):raise TeamError('review binding/schema')
                            self._evidence(payload)
                            task['state']='approved' if payload['verdict']=='pass' else 'blocked'
                            task['review']=dict(payload)
                        else:raise TeamError('unknown collaboration action')
                    task['history'].append({'operation':operation_id,'actor':actor,'action':action,'state':task['state'],'artifact':task['artifact']})
                    self.db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?)',(entity,task_id,_json(task)))
                    self.db.execute('INSERT INTO receipts VALUES(?,?,?)',(operation_id,binding,_json(task)))
                    self.db.commit();return task
                except BaseException:self.db.rollback();raise
            return self.team.perform(token,entity,operation_id,'observe',{'collaboration':binding},effect)
    @staticmethod
    def _hash(value):
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise TeamError('SHA256 required')
    @classmethod
    def _evidence(cls,payload):
        values=payload['evidence']
        if type(values) is not list or not 1<=len(values)<=100:raise TeamError('evidence required')
        for value in values:cls._hash(value)
    def close(self):self.db.close()
