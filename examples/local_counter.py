"""Installed-motor example: synthetic local counter, no network or LLM."""
import argparse,json
from pathlib import Path
from protoagent_framework import create_session
from protoagent_framework.durable_counter import DurableCounter
from protoagent_framework.runtime_config import RuntimeConfig

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);args=parser.parse_args()
    root=Path(args.workspace);root.mkdir(parents=True,exist_ok=False)
    config=RuntimeConfig(session_steps=24);config.check_workspace_from_host(root)
    provider=DurableCounter(root/'resource.sqlite',entity='synthetic-counter',target=2)
    session=create_session(root/'session.sqlite','counter-example',budget=config.session_steps,goal={'target':2},nodes=4)
    try:
        session.start();result=session.run(provider,max_steps=24)
        print(json.dumps({'status':result['checkpoint']['status'],'value':provider.value(),'audit':session.audit_intact()}))
        if result['checkpoint']['status']!='completed':raise RuntimeError('example did not complete within budget')
    finally:session.close();provider.close()

if __name__=='__main__':main()
