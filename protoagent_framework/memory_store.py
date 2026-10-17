"""Public JSON reference store. Data integrity is not host authority."""
from dataclasses import dataclass,asdict
import hashlib
import json
import sqlite3

class ReferenceError(ValueError): pass

def canonical(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(raw.encode())>1024*1024:raise ReferenceError('JSON object exceeds1MiB')
    return raw

@dataclass(frozen=True)
class MemoryReference:
    identity:str
    entity:str
    revision:int
    purpose:str='description'
    schema:int=1
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,value):return cls(**value)

class MemoryStore:
    def __init__(self,path):
        self.path=str(path);self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS memory_objects(identity TEXT PRIMARY KEY,entity TEXT,revision INTEGER,purpose TEXT,body TEXT)');self.db.commit()
    def put(self,body,*,entity,revision,purpose='description'):
        if not isinstance(entity,str) or not entity or type(revision) is not int or revision<0 or not isinstance(purpose,str) or not purpose:raise ReferenceError('invalid reference context')
        raw=canonical(body);identity=hashlib.sha256(canonical([entity,revision,purpose,body]).encode()).hexdigest()
        with self.db:self.db.execute('INSERT OR IGNORE INTO memory_objects VALUES(?,?,?,?,?)',(identity,entity,revision,purpose,raw))
        return MemoryReference(identity,entity,revision,purpose)
    def resolve(self,ref,*,entity,revision):
        if not isinstance(ref,MemoryReference) or ref.schema!=1 or (ref.entity,ref.revision)!=(entity,revision):raise ReferenceError('reference context mismatch')
        row=self.db.execute('SELECT entity,revision,purpose,body FROM memory_objects WHERE identity=?',(ref.identity,)).fetchone()
        if not row or row[:3]!=(entity,revision,ref.purpose):raise ReferenceError('reference absent or incompatible')
        body=json.loads(row[3])
        if hashlib.sha256(canonical([entity,revision,ref.purpose,body]).encode()).hexdigest()!=ref.identity:raise ReferenceError('reference integrity failure')
        return body
    def close(self):self.db.close()

class ReferencedProvider:
    """Wrap any provider; complete description persists before Session stores a ref."""
    def __init__(self,provider,store,*,revision):self.provider=provider;self.store=store;self.revision=revision;self.entity=provider.entity
    def __getattr__(self,key):return getattr(self.provider,key)
    def describe(self,observation):
        body=self.provider.describe(observation);ref=self.store.put(body,entity=self.entity,revision=self.revision())
        return {'schema':'public-reference-description-v1','reference':ref.to_dict(),'authority':False}
    def state_key(self):return ('public-reference-state-v1',hashlib.sha256(canonical(self.provider.state_key()).encode()).hexdigest())
