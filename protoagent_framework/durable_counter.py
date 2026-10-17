"""Native numerical adapter example with receipts and policy in host-owned SQLite.

Example provider, NOT a generic production payment adapter. Policy and native
effect/receipt share a transaction. No SQL or commands from agent text are run.
"""
import json
import sqlite3
from .session import SessionError

class DurableCounter:
    def __init__(self,path,entity='A',*,target=3):
        self.entity=entity; self.target=target
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS counters(entity TEXT PRIMARY KEY, value INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS policy(entity TEXT PRIMARY KEY, enabled INTEGER NOT NULL, revision INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, entity TEXT NOT NULL,
            binding TEXT NOT NULL, result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operation_fences(id TEXT PRIMARY KEY, entity TEXT NOT NULL);
        ''')
        self.db.execute('INSERT OR IGNORE INTO counters VALUES(?,0)',(entity,))
        self.db.execute('INSERT OR IGNORE INTO policy VALUES(?,1,0)',(entity,)); self.db.commit()
    def value(self): return self.db.execute('SELECT value FROM counters WHERE entity=?',(self.entity,)).fetchone()[0]
    def observe(self):
        import numpy as np
        return np.array([1.,self.value()/10.,self.target/10.],dtype=np.float32)
    def legal_actions(self): return [0,1]
    def is_information_action(self,action): return False
    def describe(self,observation): return {'counter':self.value(),'target':self.target}
    def context_vector(self): return [1.,0.,self.target/10.]
    def state_key(self): return (self.entity,self.value(),self.target)
    def request_binding(self,action): return {'entity':self.entity,'action':action,'target':self.target}
    def perform(self,operation,action):
        if type(action) is not int or action not in (0,1): raise SessionError('undeclared action')
        binding=json.dumps(self.request_binding(action),sort_keys=True)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT 1 FROM operation_fences WHERE id=?',(operation,)).fetchone():
                raise SessionError('operation durably fenced')
            receipt=self.db.execute('SELECT entity,binding,result FROM receipts WHERE id=?',(operation,)).fetchone()
            if receipt:
                if receipt[:2]!=(self.entity,binding): raise SessionError('idempotency collision')
                data=json.loads(receipt[2]); self.db.commit()
            else:
                enabled=self.db.execute('SELECT enabled FROM policy WHERE entity=?',(self.entity,)).fetchone()[0]
                if not enabled: raise SessionError('current policy revoked')
                before=self.value(); after=before+(1 if action==0 else -1)
                self.db.execute('UPDATE counters SET value=? WHERE entity=?',(after,self.entity))
                data={'observation':[1.,after/10.,self.target/10.],
                      'reward':float(abs(self.target-before)-abs(self.target-after)),
                      'terminal':after==self.target,
                      'evidence':{'at_goal':after==self.target,'resource':'full' if after==self.target else 'available'}}
                self.db.execute('INSERT INTO receipts VALUES(?,?,?,?)',(operation,self.entity,binding,json.dumps(data)))
                self.db.commit()
        except Exception: self.db.rollback(); raise
        import numpy as np
        return np.array(data['observation'],dtype=np.float32),data['reward'],data['terminal'],data['evidence']
    def revoke(self):
        self.db.execute('UPDATE policy SET enabled=0,revision=revision+1 WHERE entity=?',(self.entity,)); self.db.commit()
    def fence_operation_from_host(self,operation,entity):
        """Reference local native fence; no HTTP/distributed guarantee implied."""
        if entity!=self.entity: raise SessionError('native fence entity mismatch')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            receipt=self.db.execute('SELECT entity FROM receipts WHERE id=?',(operation,)).fetchone()
            if receipt:
                if receipt[0]!=entity: raise SessionError('receipt belongs to another entity')
                result={'state':'applied','operation_id':operation,'entity':entity,'fenced':False}
            else:
                prior=self.db.execute('SELECT entity FROM operation_fences WHERE id=?',(operation,)).fetchone()
                if prior and prior[0]!=entity: raise SessionError('fence identity collision')
                self.db.execute('INSERT OR IGNORE INTO operation_fences VALUES(?,?)',(operation,entity))
                result={'state':'fenced_not_applied','operation_id':operation,'entity':entity,'fenced':True}
            self.db.commit(); return result
        except Exception: self.db.rollback(); raise
    def verify_goal(self,goal): return goal=={'target':self.target} and self.value()==self.target
    def close(self): self.db.close()
