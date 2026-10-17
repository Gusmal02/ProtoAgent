"""Host-owned durable tool records backed by actual ProtoLibrary/Runtime.

Historical verified experience is a candidate, never a grant in a new contract.
No generated Python executes here; only a supplied trusted host verifier may run it.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import os

import torch
from core.proto_library import ProtoLibrary
from core.proto_tool_catalog import ProtoToolCatalog, ToolContract
from core.resonant_library_runtime import ResonantLibraryRuntime, BridgeRecord


SIGNATURE = torch.tensor([1., .2, .1])


def modules(path):
    return {p.name: p.read_text(encoding='utf8') for p in sorted(Path(path).glob('*.py'))}


def digest(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


class VerifiedToolMemory:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tools(id TEXT PRIMARY KEY, family TEXT, author TEXT, source TEXT);
        CREATE TABLE IF NOT EXISTS proofs(receipt TEXT PRIMARY KEY, tool TEXT, contract TEXT, family TEXT, accepted INTEGER, evidence TEXT);
        CREATE TABLE IF NOT EXISTS lifecycle(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT);
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, event TEXT, body TEXT);
        ''')
        self.rebuild()

    def rebuild(self):
        self.library = ProtoLibrary()
        self.candidates = ProtoLibrary()
        self.catalog = ProtoToolCatalog(self.library)
        row = self.db.execute('SELECT body FROM lifecycle WHERE id=1').fetchone()
        self.runtime = ResonantLibraryRuntime(max_bridges=256, max_active_bridges=256)
        if row:
            value = json.loads(row[0])
            self.runtime.bridges = {b['bridge_id']: BridgeRecord(**b) for b in value['bridges']}
            self.runtime.audit = value['audit']
        for identity, family, author, source in self.db.execute('SELECT * FROM tools ORDER BY id'):
            receipts = list(self.db.execute('SELECT receipt,contract,accepted FROM proofs WHERE tool=? ORDER BY receipt', (identity,)))
            for receipt, contract, accepted in receipts:
                if not accepted: continue
                out = {'author': author, 'tool': identity, 'contract': contract, 'receipt': receipt}
                self.library.admit(receipt, SIGNATURE, identity, 'verified_finite', out, {'requires': {'family': family, 'contract': contract}})
                self.candidates.admit(receipt, SIGNATURE, identity, 'verified_finite', out, {'requires': {'family': family}})
            self.catalog.register(ToolContract(identity, 'Historical verified executable module', 'JSON events',
                                              'Independent host verifier', {'family': family}, 'bounded Docker execution'))

    def _save_runtime(self):
        body = {'bridges': [asdict(b) for b in self.runtime.bridges.values()], 'audit': self.runtime.audit}
        self.db.execute('INSERT OR REPLACE INTO lifecycle VALUES(1,?)', (json.dumps(body),))

    def register_from_host(self, path, *, family, contract, author, receipt, proof):
        if not proof.get('accepted'): raise ValueError('host verification rejected')
        if type(proof.get('checks')) is not int or proof['checks'] < 1: raise ValueError('verification evidence missing')
        source = modules(path); identity = digest(source)
        if not source or 'runner.py' not in source: raise ValueError('module set incomplete')
        stored = self.db.execute('SELECT family,author FROM tools WHERE id=?', (identity,)).fetchone()
        if stored and stored != (family, author): raise ValueError('artifact provenance conflict')
        existing = self.db.execute('SELECT tool,contract,evidence FROM proofs WHERE receipt=?', (receipt,)).fetchone()
        body = json.dumps(proof, sort_keys=True)
        if existing:
            if existing != (identity, contract, body): raise ValueError('receipt identity conflict')
            return identity
        prior = [json.loads(e[0]) for e in self.db.execute('SELECT evidence FROM proofs WHERE tool=? AND contract=? AND accepted=1', (identity, contract))]
        if any(p == proof for p in prior) or (proof.get('measurement_hash') and any(p.get('measurement_hash') == proof['measurement_hash'] for p in prior)):
            # New operation IDs do not turn the same experiment into new support.
            return identity
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO tools VALUES(?,?,?,?)', (identity, family, author, json.dumps(source, sort_keys=True)))
            self.db.execute('INSERT INTO proofs VALUES(?,?,?,?,?,?)', (receipt, identity, contract, family, 1, body))
            self.runtime.observe(identity + ':' + contract, (1., .2, .1), 1., True, evidence=receipt)
            self._save_runtime()
            self.db.execute('INSERT INTO audit(event,body) VALUES(?,?)', ('register', json.dumps({'tool': identity, 'receipt': receipt, 'author': author})))
        self.rebuild()
        return identity

    def recover_candidates(self, family, excluded=()):
        decision = self.candidates.consult(SIGNATURE, min_cards=1, context_meta={'family': family})
        # Preserve alternatives when votes conflict; don't silently choose the
        # most resonant artifact as an answer. The motor selects candidates.
        identities = sorted({card['policy'] for card in decision.get('cards', [])} - set(excluded))
        self.db.execute('INSERT INTO audit(event,body) VALUES(?,?)', ('consult', json.dumps({'family': family, 'candidates': identities, 'decision': decision['decision']})))
        self.db.commit()
        return identities

    def materialize(self, identity, directory, hook=lambda _:None):
        row = self.db.execute('SELECT source FROM tools WHERE id=?', (identity,)).fetchone()
        if not row: raise ValueError('unknown tool')
        source = json.loads(row[0])
        if digest(source) != identity: raise ValueError('stored tool integrity failure')
        directory = Path(directory)
        if directory.exists() and not directory.is_dir():raise ValueError('materialization target not directory')
        directory.mkdir(exist_ok=True)
        marker=directory/'.materialization.json'
        names={name for name in source}
        if marker.exists():
            if json.loads(marker.read_text(encoding='utf8')).get('module')!=identity:raise ValueError('materialization owner mismatch')
        else:
            existing={p.name:p.read_text(encoding='utf8') for p in directory.glob('*.py')}
            if existing:
                if existing!=source:raise ValueError('unowned nonempty materialization target')
                return directory  # Historical complete delivery, read-only.
            marker_pending=directory/'.materialization.pending'
            if any(p!=marker_pending for p in directory.iterdir()):raise ValueError('unowned materialization files')
            # A interrupted marker write has no delivered code yet. Recreate
            # only this reserved temporary marker, never arbitrary contents.
            with marker_pending.open('w',encoding='utf8') as stream:
                json.dump({'module':identity},stream);stream.flush();os.fsync(stream.fileno())
            hook('materialization_owner_before_rename')
            os.replace(marker_pending,marker)
            hook('materialization_owner_after_rename')
        allowed=names|{'.materialization.json'}|{'.'+name+'.pending' for name in names}
        if any(p.name not in allowed for p in directory.iterdir()):raise ValueError('unexpected materialization content')
        for name, text in source.items():
            if Path(name).name != name or not name.endswith('.py'): raise ValueError('invalid module name')
            target=directory/name
            if target.exists():
                if target.read_text(encoding='utf8')!=text:raise ValueError('delivered module changed')
                continue
            temporary=directory/('.'+name+'.pending')
            # Only files inside a module-owned delivery directory are rewritten.
            with temporary.open('w',encoding='utf8') as stream:
                stream.write(text);stream.flush();os.fsync(stream.fileno())
            hook('materialization_before_rename')
            os.replace(temporary,target)
            hook('materialization_after_rename')
        return directory

    def revalidate_from_host(self, identity, path, *, family, contract, verifier, receipt):
        if digest(modules(path)) != identity: raise ValueError('materialized tool altered')
        proof = verifier(path)
        if proof['accepted']:
            self.register_from_host(path, family=family, contract=contract, author=self.db.execute('SELECT author FROM tools WHERE id=?', (identity,)).fetchone()[0], receipt=receipt, proof=proof)
        else:
            bridge = identity + ':' + contract
            # A failure in a NEW context must also be limbo, not merely a weak
            # untested candidate. It does not revoke proofs for unrelated contexts.
            self.runtime.observe(bridge, (1., .2, .1), 0., False, evidence=receipt)
            self.runtime.bridges[bridge].status = 'limbo'
            self.runtime.bridges[bridge].weight = 0.
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO proofs VALUES(?,?,?,?,?,?)', (receipt, identity, contract, family, 0, json.dumps(proof, sort_keys=True)))
                self._save_runtime()
                self.db.execute('INSERT INTO audit(event,body) VALUES(?,?)', ('reject', json.dumps({'tool': identity, 'contract': contract, 'receipt': receipt})))
            self.rebuild()
        return proof

    def eligible(self, identity, family, contract):
        row = self.db.execute('SELECT source FROM tools WHERE id=? AND family=?', (identity, family)).fetchone()
        if not row or digest(json.loads(row[0])) != identity: return False
        bridge = self.runtime.bridges.get(identity + ':' + contract)
        recommendation = self.catalog.recommend(SIGNATURE, {'family': family, 'contract': contract}, min_cards=2)
        relevant = [c for c in recommendation['evidence'].get('cards', []) if c['policy'] == identity]
        return bool(bridge and bridge.status == 'active' and len(relevant) >= 2 and recommendation.get('tool', {}).get('tool_id') == identity)

    def close(self): self.db.close()
