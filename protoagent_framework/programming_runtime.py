"""Motor-selected code generation/delegation. Host registers capabilities, not turns.

Generation callbacks must be durable/idempotent. Verifiers are trusted host
callbacks; this module never executes generated Python or calls external APIs.
"""
import json
from pathlib import Path
from .native_tools import NativeToolStore
from .toolkit import Observation,ToolDefinition,ToolRegistry,RegisteredProvider,ToolResult
from .code_generator import sha,validate_candidate

class ProgrammingRuntime:
    def __init__(self,path,*,contract,generator,verifiers,session_factory,steps=40,generations=3):
        if type(verifiers) is not dict or not 1<=len(verifiers)<=8 or any(type(name) is not str or not name.isidentifier() or name in ('lead','builder') or not callable(callback) for name,callback in verifiers.items()) or type(steps) is not int or not 1<=steps<=1000 or type(generations) is not int or not 1<=generations<=20:raise ValueError('bounded mission and independent verifier names required')
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.contract=contract;self.generator=generator;self.verifiers=verifiers;self.limit=steps;self.generation_limit=generations
        self.identity=sha([contract,sorted(verifiers),steps,generations]);self.store=NativeToolStore(self.path/'work.sqlite')
        self.store.db.executescript('CREATE TABLE IF NOT EXISTS mission(id INTEGER PRIMARY KEY,identity TEXT,state TEXT); CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,state TEXT,result TEXT);')
        columns={row[1] for row in self.store.db.execute('PRAGMA table_info(attempts)')}
        for column in ('actor','binding'):
            if column not in columns:self.store.db.execute('ALTER TABLE attempts ADD COLUMN '+column+' TEXT')
        prior=self.store.db.execute('SELECT identity FROM mission WHERE id=1').fetchone()
        if prior and prior[0]!=self.identity:self.store.close();raise ValueError('mission contract changed')
        self.store.db.execute('INSERT OR IGNORE INTO mission VALUES(1,?,?)',(self.identity,json.dumps({'candidate':None,'reviews':{},'attempts':0,'used':0,'status':'running','enabled':True,'revision':0,'events':[]})))
        self.store.db.commit()
        self.sessions={}
        try:
            for name in ['lead','builder']+list(verifiers):self.sessions[name]=session_factory(self.path,name,steps)
            for session in self.sessions.values():
                if session.checkpoint()['status']=='ready':session.start()
        except BaseException:
            self.close();raise
    def state(self):return json.loads(self.store.read('SELECT state FROM mission WHERE id=1')[0][0])
    def revoke(self):
        state=self.state();state['enabled']=False;state['revision']+=1
        self.store.db.execute('UPDATE mission SET state=? WHERE id=1',(json.dumps(state),));self.store.db.commit()
    def observation(self):
        state=self.state()
        return Observation('programming',state['revision'],(float(bool(state['candidate'])),len(state['reviews'])/len(self.verifiers),state['used']/self.limit),
            state=state,description={'contract':self.contract,'capabilities':list(self.verifiers),'authority':'host registered capabilities; no generated code execution'})
    def provider(self,actor):
        names=['generate','repair','publish','abstain']+['delegate_'+name for name in self.sessions if name!='lead'] if actor=='lead' else (['generate','repair'] if actor=='builder' else ['review'])
        def available(name,view):
            s=view.state
            if not s['enabled'] or s['status']!='running' or s['used']>=self.limit:return False,'mission stopped'
            if name in ('generate','repair'):return s['attempts']<self.generation_limit and (not s['candidate'] if name=='generate' else bool(s['candidate']) and any(not r['accepted'] for r in s['reviews'].values())),'generation preconditions'
            if name=='review':return bool(s['candidate']) and actor not in s['reviews'],'review current candidate once'
            if name=='publish':return self.accepted(s),'independent acceptance required'
            return True,'available'
        def completion(view):
            s=view.state
            if not self.accepted(s) or not s['enabled'] or s['status']!='running':return None
            return {'entity':view.entity,'revision':view.revision,'goal_scope':self.identity,
                    'artifact_hash':s['candidate']['hash'],
                    'evidence_hashes':[sha(s['reviews'][name]) for name in sorted(self.verifiers)]}
        specs=[ToolDefinition(name,'observe',lambda view:{'mission':self.identity},
            handler=lambda op,r:self.effect(actor,op,r),available=lambda view,n=name:available(n,view),
            completion=completion if name=='publish' else None) for name in names]
        return RegisteredProvider(ToolRegistry(specs),self.observation,lambda _:self.state()['status']=='completed',session=self.sessions[actor])
    def accepted(self,state):
        candidate=state['candidate']
        return bool(candidate) and candidate.get('hash')==sha(candidate.get('files')) and set(state['reviews'])==set(self.verifiers) and all(r['accepted'] is True and r['hash']==candidate['hash'] for r in state['reviews'].values())
    def effect(self,actor,operation,request):
        # Dispatch nested sessions BEFORE opening effect transaction, never
        # round-robin. Only a motor-selected delegate action gets here.
        s=self.state();output=None;tool=request.tool
        names=(['generate','repair','publish','abstain']+['delegate_'+name for name in self.sessions if name!='lead'] if actor=='lead' else ['generate','repair'] if actor=='builder' else ['review'] if actor in self.verifiers else [])
        if tool not in names or request.entity!='programming' or request.payload!={'mission':self.identity}:raise PermissionError('actor or mission binding')
        if not s['enabled'] or request.revision!=s['revision']:raise PermissionError('mission authority changed')
        old=self.store.receipt(operation)
        if old:
            prior_actor=self.store.db.execute('SELECT actor FROM attempts WHERE id=?',(operation,)).fetchone()
            if prior_actor and prior_actor[0]!=actor:raise PermissionError('receipt actor mismatch')
            return self.store.execute(operation,request,mutate=lambda db,r:None,authorize=lambda db,r:False)
        if s['status']!='running':raise PermissionError('mission stopped')
        prior=self.store.db.execute('SELECT state,result,actor,binding FROM attempts WHERE id=?',(operation,)).fetchone()
        if prior and prior[2:]!=(actor,sha(request.to_dict())):raise PermissionError('attempt binding changed or legacy uncertain attempt')
        if not prior and tool in ('generate','repair') and (s['attempts']>=self.generation_limit or (bool(s['candidate']) if tool=='generate' else not s['candidate'] or not any(not r['accepted'] for r in s['reviews'].values()))):raise PermissionError('generation preconditions')
        if tool=='review' and (not s['candidate'] or actor in s['reviews']):raise PermissionError('review preconditions')
        if tool=='publish' and not self.accepted(s):raise PermissionError('unverified candidate')
        if not prior and s['used']>=self.limit:raise RuntimeError('aggregate dispatch budget exhausted')
        # Reserve aggregate budget durably before any callback or nested action.
        if prior and prior[0]=='uncertain':raise RuntimeError('uncertain generation needs host reconciliation; no resend')
        if not prior:
            s['used']+=1
            if tool in ('generate','repair'):s['attempts']+=1
            with self.store.db:
                self.store.db.execute('UPDATE mission SET state=? WHERE id=1',(json.dumps(s),))
                self.store.db.execute('INSERT INTO attempts(id,state,result,actor,binding) VALUES(?,?,NULL,?,?)',(operation,'reserved',actor,sha(request.to_dict())))
        if prior and prior[0]=='prepared':output=json.loads(prior[1])
        else:
            if tool.startswith('delegate_'):
                target=tool[len('delegate_'):]
                if actor!='lead' or target not in self.sessions or target=='lead':raise PermissionError('invalid delegation')
                with self.store.db:self.store.db.execute("UPDATE attempts SET state='uncertain' WHERE id=?",(operation,))
                trace=self.sessions[target].step(self.provider(target))
                output={'delegate':target,'trace_action':trace.get('chosen_action')}
            elif tool in ('generate','repair'):
                with self.store.db:self.store.db.execute("UPDATE attempts SET state='uncertain' WHERE id=?",(operation,))
                try:
                    output=self.generator.generate(operation,self.contract,list(s['reviews'].values()))
                    metadata={k:output[k] for k in ('search_evaluations','grammar') if k in output}
                    output={**validate_candidate(output,output.get('author','generator')),**metadata}
                except RuntimeError as exc:
                    if str(exc) not in ('native synthesis budget exhausted','no candidate in finite grammar'):raise
                    output={'known_exhaustion':str(exc)}
            elif tool=='review':
                output=self.verifiers[actor](s['candidate'],self.contract)
                if type(output) is not dict or type(output.get('accepted')) is not bool:raise ValueError('verifier result schema')
                output={**output,'hash':s['candidate']['hash'],'reviewer':actor}
            else:output={}
            with self.store.db:self.store.db.execute('UPDATE attempts SET state=?,result=? WHERE id=?',('prepared',json.dumps(output),operation))
        def mutate(db,r):
            current=self.state()
            if tool in ('generate','repair'):
                if 'known_exhaustion' in output:current['status']='capability_exhausted'
                else:
                    current.update(candidate=output,reviews={})
                    current['search_evaluations']=current.get('search_evaluations',0)+output.get('search_evaluations',0)
            elif tool=='review':current['reviews'][actor]=output
            elif tool=='publish':
                if not self.accepted(current):raise PermissionError('unverified candidate')
                current['status']='completed'
            elif tool=='abstain':current['status']='abstained'
            current['events'].append({'operation':operation,'actor':actor,'tool':tool,'candidate':current['candidate']['hash'] if current['candidate'] else None})
            db.execute('UPDATE mission SET state=? WHERE id=1',(json.dumps(current),))
            return ToolResult(self.observation().features,reward=1. if current['status']=='completed' else .05 if tool=='review' else 0.,terminal=current['status']=='completed',evidence={'at_goal':current['status']=='completed','actor':actor,'tool':tool,'output':output})
        return self.store.execute(operation,request,mutate=mutate,authorize=lambda db,r:self.state()['enabled'] and r.revision==self.state()['revision'])
    def run(self):
        traces=[];reconciled=[]
        # A publish can commit before the lead's checkpoint. Reconcile only a
        # recorded native receipt, never infer no effect from an absent record.
        for name,session in self.sessions.items():
            pending=session.checkpoint().get('pending')
            if pending and self.store.receipt(pending):
                traces.append(session.step(self.provider(name)));reconciled.append(name)
            elif pending and self.state()['status']!='running':
                raise RuntimeError('terminal mission has uncertain session; host reconciliation required')
        for _ in range(self.limit):
            if self.state()['status']!='running' or self.state()['used']>=self.limit:break
            traces.append(self.sessions['lead'].step(self.provider('lead')))
        if self.state()['status']=='completed':
            for name,session in self.sessions.items():
                if session.checkpoint()['status']!='completed':session.complete(self.provider(name))
        return {'state':self.state(),'traces':traces,'reconciled_sessions':reconciled,'audit':{name:s.audit_intact() for name,s in self.sessions.items()}}
    def close(self):
        for session in self.sessions.values():session.close()
        self.store.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
