"""Sequential reuse comparison + community handoff on synthetic data only."""
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
from protoagent_framework.code_generator import sha
from protoagent_framework.capability_reuse import CapabilityReuseGenerator
from protoagent_framework.programming_runtime import ProgrammingRuntime
from protoagent_framework.community import prepare_review


def run(root, support):
    import torch
    torch.set_num_threads(1)
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('support',support);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
    began_all=time.perf_counter();cpu_all=time.process_time()
    report={'state':'running','training':[],'arms':{},'synthetic_only':True}
    (root/'manifest.json').write_text(json.dumps({'reserve_seed':84519,'reserve_count':100,'modes':['off','flat','contextual'],
        'sdk':__version__,'dispatches':48,'generations':3,'candidate_limit':16,
        'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'support_sha256':hashlib.sha256(Path(support).read_bytes()).hexdigest()},indent=2))
    def factory(path,actor,budget):
        return Session(path/(actor+'.sqlite'),actor,Engine(nodes=4,seed=881,config={'enable_evidence_exploration':True,'evidence_exploration_after':2}),budget=budget,goal={'accepted':True})
    def probe(folder):
        calls=[]
        def verify(candidate,c):
            if not s.security(candidate,c)['accepted']:return {'accepted':False,'checks':1,'reason':'interface or source'}
            values=[e['input'] for e in c['examples']]
            actual=s.execute(candidate,c,values,folder/str(len(calls)));calls.append(candidate['hash'])
            return {'accepted':actual==[e['output'] for e in c['examples']],'checks':len(values)}
        return verify
    seed=root/'seed';seed.mkdir()
    generator=CapabilityReuseGenerator(seed/'jobs.sqlite',library_path=seed/'library',verifier=probe(seed/'probe'))
    try:
        for label,project in [('tabular',False),('project',True)]:
            c=s.contract(project=project);qa,_=s.qa_factory(seed/('qa-'+label))
            with ProgrammingRuntime(seed/label,contract=c,generator=generator,verifiers={'qa':qa,'security':s.security},session_factory=factory,steps=48,generations=3) as runtime:
                result=runtime.run();assert result['state']['status']=='completed',result['state']['status']
                report['training'].append({'kind':label,'steps':result['state']['used'],'cost':result['state'].get('generation_costs'),
                                           'artifact':result['state']['candidate']['hash']})
    finally:generator.close()
    target=s.contract();target['goal']='Consultoria ficticia: conciliar honorarios y devoluciones positivas unicas por cuenta; API tabular compartida.'
    values=s.samples(84518,12)+s.challenges()
    target['examples']=[{'input':v,'output':s.oracle(v)} for v in values]
    for mode in ('off','flat','contextual'):
        folder=root/mode;shutil.copytree(seed,folder)
        generator=CapabilityReuseGenerator(folder/'jobs.sqlite',library_path=folder/'library',verifier=probe(folder/'new-probes'),mode=mode)
        qa,_=s.qa_factory(folder/'target-qa');began=time.perf_counter()
        try:
            before=generator.db.execute('SELECT candidates,rows FROM budget').fetchone()
            with ProgrammingRuntime(folder/'target',contract=target,generator=generator,verifiers={'qa':qa,'security':s.security},session_factory=factory,steps=48,generations=3) as runtime:
                result=runtime.run();assert result['state']['status']=='completed',result['state']['status']
                assert all(result['audit'].values())
                candidate=result['state']['candidate'];reserve=s.samples(84519,100)
                assert s.execute(candidate,target,reserve,folder/'reserve')==[s.oracle(x) for x in reserve]
                after=generator.db.execute('SELECT candidates,rows FROM budget').fetchone()
                report['arms'][mode]={'steps':result['state']['used'],'attempts':result['state']['attempts'],
                    'new_search_candidates':after[0]-before[0],'new_search_rows':after[1]-before[1],
                    'fresh_qa_cases':14,'fresh_security_checks':1,'terminal_reserve_checks':100,
                    'recovery':[json.loads(r[0]) for r in generator.db.execute('SELECT metrics FROM retrievals')],
                    'reserve_passed':100,'seconds':time.perf_counter()-began,'events':result['state']['events']}
                if mode=='contextual':
                    assert result['state']['attempts']==0,'motor did not reuse'
                    op=next(e['operation'] for e in result['state']['events'] if e['tool']=='recover')
                    before_replay=list(generator.db.execute('SELECT * FROM retrievals'))
                    assert generator.recover(op,target)['hash']==candidate['hash']
                    assert before_replay==list(generator.db.execute('SELECT * FROM retrievals'))
                    report['positive_replay_without_extra_probe']=True
                    prepare_review(root/'community-delivery',candidate,target,result['state']['reviews'])
                    # New requirement cannot be silently accepted using prior code.
                    incompatible=s.contract(include_zero=True)
                    incompatible['examples']=[{'input':v,'output':s.oracle(v,True)} for v in s.challenges()]
                    assert generator.recover('incompatible',incompatible) is None
                    try:generator.recover('incompatible',target)
                    except ValueError:report['binding_collision_denied']=True
                    else:raise AssertionError('binding collision accepted')
                    report['incompatible_rejected']=True
                    runtime.revoke();assert not runtime.provider('lead').verified_replans()
                    report['revocation_respected']=True
        finally:generator.close()
    report['state']='passed';report['community_state']='awaiting_real_human_review'
    report['seconds_total']=time.perf_counter()-began_all
    report['cpu_seconds_self']=time.process_time()-cpu_all;report['children_cpu_included']=False
    report['disk_bytes']=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    (root/'result.json').write_text(json.dumps(report,indent=2));return report


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--support',type=Path,required=True);p.add_argument('--worker',action='store_true');a=p.parse_args()
    if not a.worker:
        proc=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),str(a.output.resolve()),'--support',str(a.support.resolve()),'--worker'],timeout=180)
        raise SystemExit(proc.returncode)
    try:result=run(a.output,a.support)
    except Exception as exc:
        if a.output.exists():(a.output/'failure.json').write_text(json.dumps({'type':type(exc).__name__,'error':str(exc)},indent=2))
        raise
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
