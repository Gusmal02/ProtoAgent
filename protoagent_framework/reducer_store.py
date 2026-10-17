"""Trusted host-authored durable keyed reducer. Not synthesized business logic.

Permissions are transactional DB records; callers receive opaque grants, never
derive authority from generated source or a recovered application checkpoint.
This adapter assumes trusted local Python and controlled database ownership.
"""
import hashlib,json,secrets,sqlite3
from contextlib import contextmanager

def text(value):
    if type(value) is not str or not 1<=len(value)<=128:raise ValueError('bounded text required')
    return value

@contextmanager
def connection(path):
    db=sqlite3.connect(path,timeout=10,isolation_level=None)
    db.execute('PRAGMA busy_timeout=10000');db.execute('PRAGMA synchronous=FULL')
    try:yield db
    finally:db.close()

class HostAuthority:
    def __init__(self,path):
        self.path=path
        with connection(path) as db:
            db.executescript('CREATE TABLE IF NOT EXISTS grants(token TEXT PRIMARY KEY,actor TEXT,tenant TEXT,enabled INTEGER); CREATE TABLE IF NOT EXISTS states(tenant TEXT,key TEXT,value INTEGER,PRIMARY KEY(tenant,key)); CREATE TABLE IF NOT EXISTS events(tenant TEXT,id TEXT,payload TEXT,value INTEGER,PRIMARY KEY(tenant,id));')
    def grant(self,actor,tenant):
        text(actor);text(tenant);token=secrets.token_hex(32)
        with connection(self.path) as db:db.execute('INSERT INTO grants VALUES(?,?,?,1)',(hashlib.sha256(token.encode()).hexdigest(),actor,tenant))
        return token
    def revoke(self,token):
        with connection(self.path) as db:db.execute('UPDATE grants SET enabled=0 WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def initialize(self,tenant,key,value):
        text(tenant);text(key)
        if type(value) is not int or not 0<=value<=10**6:raise ValueError('state range')
        with connection(self.path) as db:db.execute('INSERT INTO states VALUES(?,?,?)',(tenant,key,value))

class ReducerStore:
    def __init__(self,path):self.path=path;self._fault=lambda phase:None
    def _authorize(self,db,token,tenant):
        if type(token) is not str:raise PermissionError('grant')
        record=db.execute('SELECT actor,tenant,enabled FROM grants WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not record or record[1]!=tenant or record[2]!=1:raise PermissionError('grant revoked or wrong entity')
        return record[0]
    def apply(self,reducer,token,tenant,identity,key,operation,argument):
        for item in (tenant,identity,key,operation):text(item)
        if type(argument) is not int or not 1<=argument<=10**6:raise ValueError('argument range')
        with connection(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                actor=self._authorize(db,token,tenant)
                payload=json.dumps([actor,key,operation,argument],separators=(',',':'))
                old=db.execute('SELECT payload,value FROM events WHERE tenant=? AND id=?',(tenant,identity)).fetchone()
                if old:
                    if old[0]!=payload:raise ValueError('identity conflict')
                    db.commit();return old[1]
                prior=db.execute('SELECT value FROM states WHERE tenant=? AND key=?',(tenant,key)).fetchone()
                if prior is None:raise ValueError('unknown key')
                value=reducer(prior[0],operation,argument)
                if type(value) is not int or not 0<=value<=10**6:raise ValueError('state range')
                db.execute('UPDATE states SET value=? WHERE tenant=? AND key=?',(value,tenant,key))
                db.execute('INSERT INTO events VALUES(?,?,?,?)',(tenant,identity,payload,value))
                self._fault('before_commit');db.commit();self._fault('after_commit')
                return value
            except BaseException:
                if db.in_transaction:db.rollback()
                raise
    def report(self,token,tenant):
        text(tenant)
        with connection(self.path) as db:
            db.execute('BEGIN')
            try:
                self._authorize(db,token,tenant)
                result=dict(db.execute('SELECT key,value FROM states WHERE tenant=? ORDER BY key',(tenant,)))
                db.commit();return result
            except BaseException:db.rollback();raise
