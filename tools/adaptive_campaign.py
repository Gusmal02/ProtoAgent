"""Bounded sequential cold/experienced comparison; no operation deployment."""
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from protoagent_framework import Session,__version__
from protoagent_framework.engine import Engine
from protoagent_framework.adaptive_synthesis import AdaptiveReuseGenerator
from protoagent_framework.programming_runtime import ProgrammingRuntime


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(root,support,evaluator):
    import torch
    torch.set_num_threads(1)
    root.mkdir(parents=True,exist_ok=False);s=load(support,'support');e=load(evaluator,'evaluator')
    def save(name,body):(root/name).write_text(json.dumps(body,indent=2),encoding='utf8')
    def factory(path,actor,budget):return Session(path/(actor+'.sqlite'),actor,Engine(nodes=4,seed=881,config={'enable_evidence_exploration':True,'evidence_exploration_after':2}),budget=budget,goal={'accepted':True})
    began=time.perf_counter();report={'state':'running','tasks':{},'primitive_catalog':'identical_between_arms_including_generic_stable_key_sort','reserves':{'add':95101,'subtract':95102,'append':95103}}
    save('manifest.json',{'sdk':__version__,'search_cap':200000,'row_cap':12000000,'search_seconds':20,'steps':48,'generations':3,'reserves':report['reserves'],'cold_and_warm_history_cost_identical':True,
                         'source_hashes':{str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(support),Path(evaluator))}})
    seed=root/'seed';seed.mkdir();g=AdaptiveReuseGenerator(seed/'jobs.sqlite',library_path=seed/'library',verifier=lambda *_:{'accepted':False,'checks':1})
    try:
        qa,_=s.qa_factory(seed/'qa')
        with ProgrammingRuntime(seed/'mission',contract=s.contract(),generator=g,verifiers={'qa':qa,'security':s.security},session_factory=factory,steps=48,generations=3) as runtime:
            result=runtime.run();assert result['state']['status']=='completed',result['state']['status']
            report['training']={'steps':result['state']['used'],'costs':result['state'].get('generation_costs'),'artifact':result['state']['candidate']['hash'],'experience_count':g.db.execute('SELECT count(*) FROM experiences').fetchone()[0]}
            assert report['training']['experience_count']>0
    finally:g.close()
    tampered=root/'tampered-history';shutil.copytree(seed,tampered)
    bad=AdaptiveReuseGenerator(tampered/'jobs.sqlite',library_path=tampered/'library',verifier=lambda *_:{'accepted':False,'checks':1})
    try:
        with bad.db:bad.db.execute('UPDATE experiences SET dag=?',(json.dumps(['call','open']),))
        try:bad.make_search(e.contract('add'))
        except ValueError:report['tampered_DAG_denied']=True
        else:raise AssertionError('tampered historical DAG accepted')
    finally:bad.close()
    for kind in ('add','subtract','append'):
        report['tasks'][kind]={}
        for mode in ('off','contextual'):
            folder=root/(kind+'-'+mode);shutil.copytree(seed,folder)
            g=AdaptiveReuseGenerator(folder/'jobs.sqlite',library_path=folder/'library',verifier=lambda *_:{'accepted':False,'checks':1},mode=mode)
            contract=e.contract(kind);calls=[]
            def qa(candidate,c):
                safe=s.security(candidate,c)
                if not safe['accepted']:return safe
                values=[ex['input'] for ex in c['examples']]
                outputs=s.execute(candidate,c,values,folder/('qa-'+str(len(calls))));calls.append(candidate['hash'])
                for value,output in zip(values,outputs):
                    target=e.expected(value,kind)
                    if output!=target:return {'accepted':False,'counterexample':{'input':value,'output':target}}
                return {'accepted':True,'checks':len(values)}
            start=time.perf_counter()
            try:
                before=g.db.execute('SELECT candidates,rows FROM budget').fetchone()
                with ProgrammingRuntime(folder/'new-mission',contract=contract,generator=g,verifiers={'qa':qa,'security':s.security},session_factory=factory,steps=48,generations=3) as runtime:
                    outcome=runtime.run();state=outcome['state'];after=g.db.execute('SELECT candidates,rows FROM budget').fetchone()
                    row={'status':state['status'],'steps':state['used'],'attempts':state['attempts'],'candidates':after[0]-before[0],'rows':after[1]-before[1],'seconds':time.perf_counter()-start,'audit':outcome['audit']}
                    (folder/'motor.json').write_text(json.dumps(outcome,indent=2),encoding='utf8')
                    if state['status']=='completed':
                        values=e.samples(report['reserves'][kind],100)
                        outputs=s.execute(state['candidate'],contract,values,folder/'reserve')
                        assert outputs==[e.expected(v,kind) for v in values]
                        row['reserve_passed']=100
                        row['artifact']=state['candidate']['hash']
                        if mode=='contextual':
                            old=json.loads(g.db.execute('SELECT dag FROM experiences WHERE hash=?',(report['training']['artifact'],)).fetchone()[0])
                            generated=[json.loads(r[0]) for r in g.db.execute("SELECT result FROM jobs WHERE state='done'")]
                            ir=next(r['provenance']['dag'] for r in generated if r.get('candidate',{}).get('hash')==row['artifact'])
                            def contains(node):return node==old or any(contains(child) for child in node[2:] if isinstance(child,list) and child and child[0] in ('input','unary','binary'))
                            assert contains(ir),'new program did not contain verified experience'
                            row['contains_verified_DAG']=True
                    report['tasks'][kind][mode]=row;save('progress.json',report)
                    if mode=='contextual':assert state['status']=='completed',row
            finally:g.close()
    report.update(state='passed',seconds=time.perf_counter()-began);save('result.json',report);return report


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--support',type=Path,required=True);p.add_argument('--evaluator',type=Path,required=True);p.add_argument('--worker',action='store_true');a=p.parse_args()
    if not a.worker:
        proc=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),str(a.output.resolve()),'--support',str(a.support.resolve()),'--evaluator',str(a.evaluator.resolve()),'--worker'],timeout=180)
        raise SystemExit(proc.returncode)
    try:print(json.dumps(run(a.output,a.support,a.evaluator),indent=2))
    except Exception as exc:
        if a.output.exists():(a.output/'failure.json').write_text(json.dumps({'type':type(exc).__name__,'error':str(exc)},indent=2))
        raise


if __name__=='__main__':main()
