"""Durable shared computational credits, separate from effect transactions.

Credits are reserved before work and never refunded by a failed resource
transaction. Cache is trusted host data, never authority or verifier evidence.
"""
import json
import sqlite3
import uuid

class WorkBudgetExceeded(ValueError):pass

class WorkBudget:
    def __init__(self,path,*,limit):
        if type(limit) is not int or not 1<=limit<=1000000:raise ValueError('work budget limit')
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS budget(id INTEGER PRIMARY KEY,lim INTEGER,used INTEGER);
            CREATE TABLE IF NOT EXISTS reservations(id TEXT PRIMARY KEY,units INTEGER);
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,result TEXT);''')
        self.db.execute('INSERT OR IGNORE INTO budget VALUES(0,?,0)',(limit,));self.db.commit()
        if self.status()['limit']!=limit:self.close();raise ValueError('cannot reset computational budget')
    def status(self):
        limit,used=self.db.execute('SELECT lim,used FROM budget WHERE id=0').fetchone();return {'limit':limit,'used':used}
    def reserve(self,units=1):
        if type(units) is not int or units<1:raise ValueError('invalid work units')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            state=self.status()
            if state['used']+units>state['limit']:raise WorkBudgetExceeded('computational budget exhausted')
            identity=uuid.uuid4().hex
            self.db.execute('INSERT INTO reservations VALUES(?,?)',(identity,units))
            self.db.execute('UPDATE budget SET used=used+? WHERE id=0',(units,));self.db.commit();return identity
        except Exception:self.db.rollback();raise
    def get(self,key):
        row=self.db.execute('SELECT result FROM cache WHERE key=?',(key,)).fetchone()
        return None if row is None else json.loads(row[0])
    def put(self,key,result):
        raw=json.dumps(result,allow_nan=False)
        self.db.execute('INSERT OR REPLACE INTO cache VALUES(?,?)',(key,raw));self.db.commit()
    def close(self):self.db.close()
