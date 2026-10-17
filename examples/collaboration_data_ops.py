"""Host-driven protocol example; not autonomous team superiority."""
import argparse,hashlib,json
from pathlib import Path
from protoagent_framework import TeamCoordinator
from protoagent_framework.collaboration import Collaboration

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);args=parser.parse_args()
    root=Path(args.workspace);root.mkdir(parents=True,exist_ok=False)
    team=TeamCoordinator(root/'team.sqlite','demo',budget=40);collaboration=None
    try:
        tokens={}
        for actor,role in [('lead','Supervisor'),('data','Operator'),('ops','Operator'),('security','Auditor')]:
            team.register_member_from_host(actor,role,actor);tokens[actor]=team.grant_from_host(actor,('demo',),ttl=60)
        collaboration=Collaboration(team,root/'tasks.sqlite',reviewers=('security',))
        def command(actor,id,action,task,payload):return collaboration.command(tokens[actor],'demo',id,action,task,payload)
        for id,owner,deps in [('data','data',[]),('ops','ops',['data'])]:
            command('lead','request-'+id,'request',id,{'goal':'synthetic report' if id=='data' else 'consume approved report','owner':owner,'acceptance':'host verifier on exact artifact','dependencies':deps})
        command('data','accept-data','accept','data',{})
        artifact=hashlib.sha256(b'synthetic report v1').hexdigest();evidence=hashlib.sha256(b'host verification result').hexdigest()
        command('data','submit-data','submit','data',{'artifact':artifact,'evidence':[evidence]})
        # A real application must RUN its independent verifier before this pass.
        command('security','review-data','review','data',{'artifact':artifact,'evidence':[evidence],'verdict':'pass'})
        command('ops','accept-ops','accept','ops',{})
        print(json.dumps({'data':collaboration.inspect(tokens['lead'],'demo','data')['state'],'ops':collaboration.inspect(tokens['lead'],'demo','ops')['state'],'deploy_performed':False}))
    finally:
        if collaboration:collaboration.close()
        team.close()

if __name__=='__main__':main()
