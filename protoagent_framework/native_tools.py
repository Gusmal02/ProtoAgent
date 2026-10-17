"""Same-transaction SQLite effect/receipt store; no generic HTTP exactly-once."""
import json
import sqlite3
from .memory_store import canonical
from .toolkit import ToolResult

class NativeToolStore:
    def __init__(self,path,*,initialize=None,events=None):
        self.path=str(path);self.events=events;self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS native_tool_receipts(id TEXT PRIMARY KEY,entity TEXT,binding TEXT,result TEXT); CREATE TABLE IF NOT EXISTS native_tool_fences(id TEXT PRIMARY KEY,entity TEXT);')
        if initialize:initialize(self.db)
        self.db.commit()
    def read(self,query,parameters=()):
        # Host-only query API. No SQL comes from actor text.
        if not query.lstrip().upper().startswith('SELECT '):raise ValueError('read supports SELECT only')
        return self.db.execute(query,parameters).fetchall()
    def execute(self,operation,request,*,mutate,authorize):
        binding=canonical(request.to_dict());self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT 1 FROM native_tool_fences WHERE id=?',(operation,)).fetchone():raise ValueError('operation fenced')
            old=self.db.execute('SELECT entity,binding,result FROM native_tool_receipts WHERE id=?',(operation,)).fetchone()
            if old:
                if old[:2]!=(request.entity,binding):raise ValueError('native binding collision')
                result=ToolResult.from_dict(json.loads(old[2]))
            else:
                if authorize(self.db,request) is not True:raise PermissionError('current native policy denies effect')
                result=mutate(self.db,request)
                if not isinstance(result,ToolResult):raise TypeError('native callback must return ToolResult')
                self.db.execute('INSERT INTO native_tool_receipts VALUES(?,?,?,?)',(operation,request.entity,binding,canonical(result.to_dict())))
            self.db.commit()
        except BaseException:self.db.rollback();raise
        if self.events:self.events('native_effect_committed',{'operation_id':operation,'entity':request.entity,'tool':request.tool})
        return result
    def receipt(self,operation):
        row=self.db.execute('SELECT entity,result FROM native_tool_receipts WHERE id=?',(operation,)).fetchone()
        return None if not row else {'operation_id':operation,'entity':row[0],'result':json.loads(row[1]),'state':'applied'}
    def fence(self,operation,entity):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.db.execute('SELECT entity FROM native_tool_receipts WHERE id=?',(operation,)).fetchone()
            if old:
                if old[0]!=entity:raise ValueError('fence context mismatch')
                self.db.commit();return {'operation_id':operation,'entity':old[0],'state':'applied','fenced':False}
            prior=self.db.execute('SELECT entity FROM native_tool_fences WHERE id=?',(operation,)).fetchone()
            if prior and prior[0]!=entity:raise ValueError('fence context mismatch')
            self.db.execute('INSERT OR IGNORE INTO native_tool_fences VALUES(?,?)',(operation,entity))
            self.db.commit()
            return {'operation_id':operation,'entity':entity,'state':'fenced_not_applied','fenced':True}
        except BaseException:self.db.rollback();raise
    def close(self):self.db.close()
