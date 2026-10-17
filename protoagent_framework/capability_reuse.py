"""Bounded cross-contract reuse; descriptors filter interfaces, not semantics.

Trusted host probes and fresh mission reviews remain mandatory. Compiler-only
artifacts: this protocol is not a hostile-code sandbox.
"""
import json
import time
import uuid
from .code_generator import sha
from .compositional_generator import CompositionalGenerator


def descriptor(contract):
    return sha({'inputs':contract.get('inputs'),'key':contract.get('key'),
                'value':contract.get('value'),'project':contract.get('project_files')})


class CapabilityReuseGenerator(CompositionalGenerator):
    def __init__(self,path,*,library_path,verifier,mode='contextual'):
        if mode not in ('contextual','flat','off') or not callable(verifier):raise ValueError('reuse configuration')
        super().__init__(path,library_path=library_path)
        self.verifier,self.mode=verifier,mode
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS capabilities(identity TEXT,context TEXT,descriptor TEXT,candidate TEXT,PRIMARY KEY(identity,context));
            CREATE TABLE IF NOT EXISTS retrievals(operation TEXT PRIMARY KEY,binding TEXT,state TEXT,result TEXT,metrics TEXT);
        ''')
        self.db.commit()

    def generate(self,identity,contract,feedback):
        if self.db.execute("SELECT 1 FROM retrievals WHERE state!='done'").fetchone():
            raise RuntimeError('retrieval interrupted; explicit reconciliation required')
        return super().generate(identity,contract,feedback)

    def remember(self,operation,candidate,contract,reviews):
        if len(reviews)<2 or any(r.get('accepted') is not True or r.get('hash')!=candidate['hash'] for r in reviews.values()):
            raise ValueError('two independent current reviews required')
        super().remember(operation,candidate,contract,reviews)
        context=sha(contract)
        identity=self.db.execute('SELECT identity FROM published WHERE context=? AND candidate=?',(context,json.dumps(candidate))).fetchone()[0]
        with self.db:self.db.execute('INSERT OR REPLACE INTO capabilities VALUES(?,?,?,?)',
                                    (identity,context,descriptor(contract),json.dumps(candidate)))

    def recovery_evidence(self,contract):
        if self.mode=='off':return None
        rows=self.db.execute('SELECT identity,context,descriptor FROM capabilities ORDER BY identity,context').fetchall()
        matched=[r for r in rows if self.mode=='flat' or r[2]==descriptor(contract)]
        return None if not matched else sha({'descriptor':descriptor(contract),'historical':matched,'mode':self.mode})

    def recover(self,operation,contract):
        binding=sha([contract,self.mode])
        old=self.db.execute('SELECT binding,state,result FROM retrievals WHERE operation=?',(operation,)).fetchone()
        if old:
            if old[0]!=binding:raise ValueError('retrieval binding collision')
            if old[1]!='done':raise RuntimeError('retrieval interrupted; explicit reconciliation required')
            return json.loads(old[2])
        if self.db.execute("SELECT 1 FROM retrievals WHERE state!='done'").fetchone():
            raise RuntimeError('retrieval interrupted; explicit reconciliation required')
        metrics={'catalog_entries':0,'selected':0,'checked':0,'verification_checks':0,'rejected':0,'mode':self.mode}
        with self.db:self.db.execute('INSERT INTO retrievals VALUES(?,?,?,NULL,?)',(operation,binding,'reserved',json.dumps(metrics)))
        began=time.perf_counter();found=None
        if self.mode!='off':
            rows=self.db.execute('SELECT identity,context,descriptor,candidate FROM capabilities ORDER BY identity,context').fetchall()
            metrics['catalog_entries']=len(rows)
            selected=[r for r in rows if self.mode=='flat' or r[2]==descriptor(contract)]
            metrics['selected']=len(selected);metrics['limit_exceeded']=len(selected)>16
            for identity,context,_,raw in selected[:16]:
                if not self.library.eligible(identity,'typed_table',context):continue
                metrics['checked']+=1
                parent=self.path.parent/'transfers';parent.mkdir(parents=True,exist_ok=True)
                delivered=self.library.materialize(identity,parent/uuid.uuid4().hex)
                saved=json.loads(raw)
                files={name:(delivered/name).read_text(encoding='utf8') for name in saved['files']}
                if sha(files)!=saved['hash']:raise ValueError('recovered artifact integrity')
                candidate={**saved,'files':files,'search_evaluations':0}
                with self.db:self.db.execute('UPDATE retrievals SET metrics=? WHERE operation=?',(json.dumps(metrics),operation))
                proof=self.verifier(candidate,contract)
                if type(proof.get('checks')) is not int or not 1<=proof['checks']<=128:raise ValueError('bounded retrieval checks required')
                metrics['verification_checks']+=proof['checks']
                accepted=proof.get('accepted') is True;metrics['rejected']+=not accepted
                self.library.revalidate_from_host(identity,delivered,family='typed_table',contract=sha(contract),
                    verifier=lambda _: {'accepted':accepted,'checks':proof['checks'],'measurement_hash':sha([operation,proof,saved['hash']])},receipt=operation+':'+identity)
                if accepted:
                    found=candidate;metrics['source_context']=context;metrics['target_context']=sha(contract)
                    break
        metrics['seconds']=time.perf_counter()-began
        with self.db:self.db.execute('UPDATE retrievals SET state=?,result=?,metrics=? WHERE operation=?',
                                    ('done',json.dumps(found),json.dumps(metrics),operation))
        return found
