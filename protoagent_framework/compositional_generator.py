"""Durable local generation adapter using existing ProgrammingRuntime port."""
import json
import sqlite3
from pathlib import Path
import uuid
from .code_generator import sha, validate_candidate
from .compositional_synthesis import CompositionalSynthesizer, SearchStopped
from .project_editing import compose_project


class CompositionalGenerator:
    def __init__(self, path, *, library_path=None):
        self.path=Path(path)
        self.library=None
        if library_path:
            from .verified_tool_memory import VerifiedToolMemory
            self.library=VerifiedToolMemory(library_path)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,binding TEXT,state TEXT,result TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS budget(id INTEGER PRIMARY KEY,candidates INTEGER,rows INTEGER,seconds REAL)')
        self.db.execute('INSERT OR IGNORE INTO budget VALUES(1,0,0,0)')
        self.db.execute('CREATE TABLE IF NOT EXISTS published(context TEXT,identity TEXT,candidate TEXT,PRIMARY KEY(context,identity))')
        self.db.commit()

    def generate(self, identity, contract, feedback):
        binding = sha([contract, feedback])
        old = self.db.execute('SELECT binding,state,result FROM jobs WHERE id=?', (identity,)).fetchone()
        if old:
            if old[0] != binding:
                raise ValueError('generation binding collision')
            if old[1] != 'done':
                raise RuntimeError('local generation interrupted; host reconciliation required')
            return json.loads(old[2])
        if self.db.execute("SELECT 1 FROM jobs WHERE state!='done'").fetchone():
            raise RuntimeError('local generation interrupted; host reconciliation required')
        prior = self.db.execute('SELECT state,result FROM jobs WHERE binding=?', (binding,)).fetchone()
        if prior:
            return {'generation_status': 'no_progress', 'generation_cost': {}}
        with self.db:
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,NULL)', (identity, binding, 'reserved'))
        examples = list(contract['examples'])
        for review in feedback:
            counterexample = review.get('counterexample')
            if counterexample and counterexample not in examples:
                examples.append(counterexample)
        used, rows, seconds = self.db.execute('SELECT candidates,rows,seconds FROM budget WHERE id=1').fetchone()
        search = self.make_search(contract)
        search.used, search.rows_used, search.elapsed = used, rows, seconds
        try:
            result = search.synthesize(contract, examples)
            files = compose_project(contract['project_files'], result['source']) if 'project_files' in contract else {'solution.py': result['source']}
            candidate = validate_candidate({'files': files}, 'finite_compositional_search_with_Codex_compiler')
            candidate.update(search_evaluations=search.used - used, grammar=result.get('grammar','factored_typed_table_DAG_v1'))
            output = {'generation_status': 'candidate', 'candidate': candidate,
                      'provenance': {'dag': result['dag'], 'compiler': 'Codex', 'selection': 'finite_search', 'feedback_used': len(examples) - len(contract['examples'])}}
        except SearchStopped as exc:
            output = {'generation_status': exc.status}
        output['generation_cost'] = {'candidates': search.used - used, 'row_operations': search.rows_used - rows,
                                     'seconds': search.elapsed - seconds}
        output=json.loads(json.dumps(output))
        with self.db:
            self.db.execute('UPDATE budget SET candidates=?,rows=?,seconds=? WHERE id=1', (search.used, search.rows_used, search.elapsed))
            self.db.execute('UPDATE jobs SET state=?,result=? WHERE id=?', ('done', json.dumps(output), identity))
        return output

    def make_search(self,contract):
        return CompositionalSynthesizer()

    def close(self):
        if self.library:self.library.close()
        self.db.close()

    def remember(self,operation,candidate,contract,reviews):
        if not self.library:return
        folder=self.path.parent/'library-source'/candidate['hash'];folder.mkdir(parents=True,exist_ok=True)
        for name,source in candidate['files'].items():(folder/name).write_text(source,encoding='utf8')
        entry='from transforms import transform as run\n' if 'project_files' in contract else 'from solution import solve as run\n'
        (folder/'runner.py').write_text(entry,encoding='utf8')
        context=sha(contract);identity=None
        for name,review in sorted(reviews.items()):
            if review.get('accepted') is not True or review.get('hash')!=candidate['hash']:raise ValueError('unverified library publication')
            identity=self.library.register_from_host(folder,family='typed_table',contract=context,author=candidate['author'],receipt=operation+':'+name,
                proof={'accepted':True,'checks':1,'measurement_hash':sha(review)})
        with self.db:self.db.execute('INSERT OR REPLACE INTO published VALUES(?,?,?)',(context,identity,json.dumps(candidate)))

    def recover(self,operation,contract):
        if not self.library:return None
        context=sha(contract)
        candidates=set(self.library.recover_candidates('typed_table'))
        for identity,raw in self.db.execute('SELECT identity,candidate FROM published WHERE context=?',(context,)):
            if identity not in candidates or not self.library.eligible(identity,'typed_table',context):continue
            saved=json.loads(raw)
            parent=self.path.parent/'recoveries';parent.mkdir(parents=True,exist_ok=True)
            delivered=self.library.materialize(identity,parent/uuid.uuid4().hex)
            files={name:(delivered/name).read_text(encoding='utf8') for name in saved['files']}
            proof=self.library.revalidate_from_host(identity,delivered,family='typed_table',contract=context,
                verifier=lambda _: {'accepted':sha(files)==saved['hash'],'checks':len(files),'measurement_hash':sha([operation,files])},receipt=operation)
            if proof['accepted']:
                return {**saved,'files':files,'search_evaluations':0}
        return None
