"""Subprocess fixture: physical exit at durable boundaries, never live data."""
import json,os,sqlite3,sys
from pathlib import Path
from protoagent_framework import Session,create_session
from protoagent_framework.durable_counter import DurableCounter

def main():
    import torch
    torch.set_num_threads(1)
    root=Path(sys.argv[1]);point=sys.argv[2];root.mkdir(parents=True,exist_ok=True)
    def event(name,data):
        if name==point and not (root/'cut.json').exists():
            with (root/'cut.json').open('x') as stream:json.dump({'event':name,'pid':os.getpid()},stream);stream.flush();os.fsync(stream.fileno())
            os._exit(87)
    provider=DurableCounter(root/'resource.sqlite',target=2)
    class Wrapped:
        def __getattr__(self,name):return getattr(provider,name)
        def legal_actions(self):return [0]
        def perform(self,operation,action):
            result=provider.perform(operation,action);event('native_committed',{});return result
    if (root/'session.sqlite').exists():session=Session.resume(root/'session.sqlite','cut',events=event)
    else:session=create_session(root/'session.sqlite','cut',budget=8,goal={'target':2},nodes=4,events=event);session.start()
    try:
        session.run(Wrapped(),max_steps=8)
        with sqlite3.connect(root/'resource.sqlite') as db:receipts=db.execute('SELECT count(*) FROM receipts').fetchone()[0]
        print(json.dumps({'checkpoint':session.checkpoint(),'value':provider.value(),'receipts':receipts,'audit':session.audit_intact()}))
    finally:session.close();provider.close()

if __name__=='__main__':main()
