"""Host-owned durable external intent; uncertainty is not permission to resend."""
import hashlib
import json
import sqlite3


class TransactionError(RuntimeError): pass


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
def sha(value): return hashlib.sha256(value).hexdigest()


class GenerationTransaction:
    def __init__(self, path, *, capacity=20, historical_used=16):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS budget(id INTEGER PRIMARY KEY CHECK(id=1),capacity INTEGER,used INTEGER);
        CREATE TABLE IF NOT EXISTS authority(actor TEXT PRIMARY KEY,entity TEXT,revision INTEGER,enabled INTEGER);
        CREATE TABLE IF NOT EXISTS intents(id TEXT PRIMARY KEY,actor TEXT,entity TEXT,revision INTEGER,request TEXT,state TEXT,response BLOB,hash TEXT,proof TEXT);
        CREATE TABLE IF NOT EXISTS parts(intent TEXT,ordinal INTEGER,data BLOB,hash TEXT,PRIMARY KEY(intent,ordinal));
        CREATE TABLE IF NOT EXISTS admissions(intent TEXT PRIMARY KEY,actor TEXT,entity TEXT,revision INTEGER,hash TEXT);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,event TEXT,intent TEXT,body TEXT);
        ''')
        row = self.db.execute('SELECT capacity FROM budget WHERE id=1').fetchone()
        if row and row[0] != capacity: raise TransactionError('budget contract changed')
        if not row:
            if type(capacity) is not int or type(historical_used) is not int or not 0 <= historical_used <= capacity:
                raise TransactionError('invalid budget')
            with self.db: self.db.execute('INSERT INTO budget VALUES(1,?,?)', (capacity, historical_used))

    def event(self, kind, identity, body):
        self.db.execute('INSERT INTO events(event,intent,body) VALUES(?,?,?)', (kind, identity, canonical(body)))

    def grant_from_host(self, actor, entity, revision):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO authority VALUES(?,?,?,1)', (actor, entity, revision))
            self.event('grant', None, {'actor': actor, 'entity': entity, 'revision': revision})

    def revoke_from_host(self, actor):
        with self.db:
            self.db.execute('UPDATE authority SET revision=revision+1,enabled=0 WHERE actor=?', (actor,))
            self.event('revocation', None, {'actor': actor})

    def _current(self, actor, entity, revision):
        return self.db.execute('SELECT entity,revision,enabled FROM authority WHERE actor=?', (actor,)).fetchone() == (entity, revision, 1)

    def row(self, identity):
        row = self.db.execute('SELECT actor,entity,revision,request,state,response,hash,proof FROM intents WHERE id=?', (identity,)).fetchone()
        if not row: raise TransactionError('unknown intent')
        return dict(zip(('actor','entity','revision','request','state','response','hash','proof'), row))

    def reserve(self, identity, actor, entity, revision, request):
        encoded = canonical(request)
        if len(encoded.encode()) > 65536: raise TransactionError('request limit')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing = self.db.execute('SELECT actor,entity,revision,request FROM intents WHERE id=?', (identity,)).fetchone()
            if existing:
                if existing != (actor, entity, revision, encoded): raise TransactionError('intent binding changed')
                self.db.commit(); return self.row(identity)
            if not self._current(actor, entity, revision): raise TransactionError('authority unavailable')
            if self.db.execute("SELECT 1 FROM intents WHERE actor=? AND state NOT IN ('admitted','rejected','resolved_no_result')", (actor,)).fetchone():
                raise TransactionError('prior external result unresolved')
            capacity, used = self.db.execute('SELECT capacity,used FROM budget WHERE id=1').fetchone()
            if used >= capacity: raise TransactionError('budget exhausted')
            self.db.execute('UPDATE budget SET used=used+1 WHERE id=1')
            self.db.execute('INSERT INTO intents VALUES(?,?,?,?,?,?,NULL,NULL,NULL)', (identity, actor, entity, revision, encoded, 'reserved'))
            self.event('reserve', identity, {'consumed': used+1})
            self.db.commit(); return self.row(identity)
        except BaseException: self.db.rollback(); raise

    def begin_dispatch(self, identity):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.row(identity)
            if row['state'] != 'reserved': raise TransactionError('dispatch not replayable')
            if not self._current(row['actor'], row['entity'], row['revision']): raise TransactionError('dispatch authority revoked')
            self.db.execute("UPDATE intents SET state='dispatching' WHERE id=?", (identity,))
            self.event('dispatch', identity, {}); self.db.commit()
        except BaseException: self.db.rollback(); raise

    def receive_part(self, identity, ordinal, data):
        if type(data) is not bytes or len(data) > 65536: raise TransactionError('part limit')
        with self.db:
            if self.row(identity)['state'] not in ('dispatching', 'receiving'): raise TransactionError('late response needs reconciliation')
            existing = self.db.execute('SELECT hash FROM parts WHERE intent=? AND ordinal=?', (identity, ordinal)).fetchone()
            if existing:
                if existing[0] != sha(data): raise TransactionError('part mismatch')
                return
            ordinals = [r[0] for r in self.db.execute('SELECT ordinal FROM parts WHERE intent=? ORDER BY ordinal', (identity,))]
            if ordinal != len(ordinals): raise TransactionError('part out of order')
            length = self.db.execute('SELECT COALESCE(sum(length(data)),0) FROM parts WHERE intent=?', (identity,)).fetchone()[0]
            if length+len(data) > 524288: raise TransactionError('response limit')
            self.db.execute('INSERT INTO parts VALUES(?,?,?,?)', (identity, ordinal, data, sha(data)))
            self.db.execute("UPDATE intents SET state='receiving' WHERE id=?", (identity,))

    def commit_response(self, identity, expected_hash):
        with self.db:
            if self.row(identity)['state'] != 'receiving': raise TransactionError('no response to commit')
            parts = list(self.db.execute('SELECT data,hash FROM parts WHERE intent=? ORDER BY ordinal', (identity,)))
            if any(sha(data) != fingerprint for data, fingerprint in parts): raise TransactionError('response parts corrupted')
            body = b''.join(data for data, _ in parts)
            if sha(body) != expected_hash: raise TransactionError('response incomplete/corrupted')
            json.loads(body)
            self.db.execute("UPDATE intents SET state='response_durable',response=?,hash=? WHERE id=?", (body, expected_hash, identity))
            self.event('response', identity, {'hash': expected_hash})

    def recover(self, identity):
        with self.db:
            row = self.row(identity)
            if row['state'] in ('dispatching', 'receiving'):
                self.db.execute("UPDATE intents SET state='uncertain' WHERE id=?", (identity,))
                self.event('uncertain', identity, {'previous_state': row['state'], 'no_automatic_resend': True})
        return self.row(identity)

    def reconcile_from_host(self, identity, *, body=None, receipt):
        if not receipt: raise TransactionError('explicit reconciliation receipt required')
        with self.db:
            if self.row(identity)['state'] != 'uncertain': raise TransactionError('not an uncertain intent')
            if body is None:
                self.db.execute("UPDATE intents SET state='resolved_no_result' WHERE id=?", (identity,))
            else:
                if type(body) is not bytes or len(body) > 524288: raise TransactionError('reconciled response limit')
                json.loads(body)
                self.db.execute("UPDATE intents SET state='response_durable',response=?,hash=? WHERE id=?", (body, sha(body), identity))
            self.event('host_reconciliation', identity, {'receipt': receipt, 'result_recovered': body is not None, 'budget_refunded': False})

    def validate_from_host(self, identity, validator, hook=lambda _: None):
        row = self.row(identity)
        if row['state'] in ('verified','admitted'): return json.loads(row['proof'])
        if row['state'] != 'response_durable' or sha(row['response']) != row['hash']: raise TransactionError('response not valid/durable')
        proof = validator(json.loads(row['response']))
        hook('during_validation')
        with self.db:
            if self.row(identity)['state'] != 'response_durable': raise TransactionError('validation context changed')
            self.db.execute('UPDATE intents SET state=?,proof=? WHERE id=?', ('verified' if proof['accepted'] else 'rejected', canonical(proof), identity))
            self.event('validation', identity, {'accepted': proof['accepted'], 'response_hash': row['hash']})
        return proof

    def admit_from_host(self, identity, hook=lambda _: None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.row(identity)
            if not self._current(row['actor'],row['entity'],row['revision']): raise TransactionError('admission authority revoked')
            if row['state'] == 'admitted': self.db.commit(); return
            if row['state'] != 'verified' or not json.loads(row['proof'])['accepted']: raise TransactionError('not verified')
            if sha(row['response']) != row['hash']: raise TransactionError('response corrupted before admission')
            self.db.execute('INSERT INTO admissions VALUES(?,?,?,?,?)', (identity,row['actor'],row['entity'],row['revision'],row['hash']))
            self.db.execute("UPDATE intents SET state='admitted' WHERE id=?", (identity,))
            self.event('admission', identity, {'hash': row['hash']})
            hook('before_admission_commit')
            self.db.commit()
        except BaseException: self.db.rollback(); raise

    def budget(self): return self.db.execute('SELECT capacity,used FROM budget WHERE id=1').fetchone()
    def close(self): self.db.close()
