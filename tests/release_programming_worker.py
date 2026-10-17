"""Publication committed, lead checkpoint interrupted; only local fixture."""
import json,os,sqlite3,sys
from pathlib import Path
from protoagent_framework import Session
from protoagent_framework.engine import Engine
from protoagent_framework.programming_runtime import ProgrammingRuntime
from protoagent_framework.code_generator import BoundedExpressionGenerator

def main():
    import torch
    torch.set_num_threads(1)
    root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
    def event(name,data):
        if name!='checkpoint_pending' or (root/'cut.json').exists():return
        with sqlite3.connect(root/'work.sqlite') as db:state=json.loads(db.execute('SELECT state FROM mission WHERE id=1').fetchone()[0])
        if state['status']=='completed':
            with (root/'cut.json').open('x') as stream:json.dump({'point':'publish_commit_before_checkpoint','pid':os.getpid(),'used':state['used']},stream);stream.flush();os.fsync(stream.fileno())
            os._exit(88)
    def factory(path,actor,budget):
        file=path/(actor+'.sqlite')
        if file.exists():return Session.resume(file,actor,events=event)
        return Session(file,actor,Engine(nodes=4,seed=881,config={'enable_evidence_exploration':True,'evidence_exploration_after':2}),budget=budget,goal={'accepted':True},events=event)
    with ProgrammingRuntime(root,contract={'examples':[[1,1],[2,2]]},generator=BoundedExpressionGenerator(),verifiers={'qa':lambda c,g:{'accepted':True},'security':lambda c,g:{'accepted':True}},session_factory=factory,steps=32,generations=2) as runtime:
        result=runtime.run();print(json.dumps({'status':result['state']['status'],'used':result['state']['used'],'events':result['state']['events'],'audit':result['audit'],'reconciled':result['reconciled_sessions'],'sessions':{n:s.checkpoint() for n,s in runtime.sessions.items()}}))

if __name__=='__main__':main()
