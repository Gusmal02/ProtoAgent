import hashlib,tempfile,unittest
from pathlib import Path
from protoagent_framework import TeamCoordinator
from protoagent_framework.collaboration import Collaboration

class CollaborationChecks(unittest.TestCase):
    def test_dependency_review_repair_reopen_and_revocation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);team=TeamCoordinator(root/'team','team',budget=60);c=None
            try:
                tokens={}
                for actor,role in [('lead','Supervisor'),('data','Operator'),('ops','Operator'),('security','Auditor')]:
                    team.register_member_from_host(actor,role,actor);tokens[actor]=team.grant_from_host(actor,('A',),ttl=600)
                c=Collaboration(team,root/'tasks',reviewers=('security',))
                def call(a,id,action,task,payload):return c.command(tokens[a],'A',id,action,task,payload)
                h=lambda value:hashlib.sha256(value.encode()).hexdigest()
                for task,owner,deps in [('data','data',[]),('ops','ops',['data'])]:call('lead','r'+task,'request',task,dict(goal='work',owner=owner,acceptance='independent proof',dependencies=deps))
                with self.assertRaises(Exception):call('ops','early','accept','ops',{})
                call('data','accept','accept','data',{});call('data','bad','submit','data',dict(artifact=h('bad'),evidence=[h('functional')]))
                with self.assertRaises(Exception):call('data','self','review','data',dict(artifact=h('bad'),evidence=[h('fake')],verdict='pass'))
                call('security','negative','review','data',dict(artifact=h('bad'),evidence=[h('counterexample')],verdict='fail'))
                with self.assertRaises(Exception):call('ops','blocked','accept','ops',{})
                call('data','repair','accept','data',{});call('data','fixed','submit','data',dict(artifact=h('fixed'),evidence=[h('regression')]))
                with self.assertRaises(Exception):call('security','stale','review','data',dict(artifact=h('bad'),evidence=[h('old')],verdict='pass'))
                call('security','positive','review','data',dict(artifact=h('fixed'),evidence=[h('measured')],verdict='pass'))
                used=team.status()['used'];c.close();c=Collaboration(team,root/'tasks',reviewers=('security',))
                call('security','positive','review','data',dict(artifact=h('fixed'),evidence=[h('measured')],verdict='pass'));self.assertEqual(team.status()['used'],used)
                self.assertEqual(call('ops','allowed','accept','ops',{})['state'],'accepted')
                team.revoke_from_host(tokens['ops'])
                with self.assertRaises(Exception):call('ops','revoked','submit','ops',dict(artifact=h('deploy'),evidence=[h('proof')]))
                with self.assertRaises(Exception):c.inspect(tokens['data'],'B','data')
            finally:
                if c:c.close()
                team.close()
