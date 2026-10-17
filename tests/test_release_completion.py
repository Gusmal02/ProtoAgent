"""Release regression: trusted proof, not a text claim or an authority token."""
import json,tempfile,unittest
from pathlib import Path
from protoagent_framework import Observation,ToolDefinition,ToolRegistry,ToolRequest,ToolResult,RegisteredProvider
from protoagent_framework.code_generator import BoundedExpressionGenerator
from protoagent_framework.programming_runtime import ProgrammingRuntime

class StubSession:
    def checkpoint(self):return {'status':'running'}
    def pending_operation_view_from_host(self):return None
    def close(self):pass
    def complete(self,provider):pass

class CompletionChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.runtime=ProgrammingRuntime(self.path,contract={'examples':[[1,1],[2,2]]},generator=BoundedExpressionGenerator(),verifiers={'qa':lambda c,g:{'accepted':True},'security':lambda c,g:{'accepted':True}},session_factory=lambda *args:StubSession(),generations=1)
    def tearDown(self):self.runtime.close();self.tmp.cleanup()
    def request(self,name):return ToolRequest(name,'programming',self.runtime.state()['revision'],{'mission':self.runtime.identity})
    def effect(self,actor,name,operation):return self.runtime.effect(actor,operation,self.request(name))
    def ready(self):
        self.effect('lead','generate','g');self.effect('qa','review','q');self.effect('security','review','s')
    def save(self,state):
        self.runtime.store.db.execute('UPDATE mission SET state=? WHERE id=1',(json.dumps(state),));self.runtime.store.db.commit()
    def test_publish_only_after_all_verifiers_and_abstain_preserved(self):
        self.assertEqual(self.runtime.provider('lead').verified_completions(),[])
        self.effect('lead','generate','g');self.effect('qa','review','q')
        self.assertEqual(self.runtime.provider('lead').verified_completions(),[])
        self.effect('security','review','s');provider=self.runtime.provider('lead')
        self.assertEqual(len(provider.verified_completions()),1)
        abstain=provider.registry.identifier('abstain');self.assertTrue(provider.registry.tools[abstain].available(provider.view)[0])
        self.effect('lead','publish','p');used=self.runtime.state()['used']
        self.effect('lead','publish','p');self.assertEqual(self.runtime.state()['used'],used)
    def test_verified_replan_requires_current_counterexample_and_authority(self):
        self.effect('lead','generate','g');state=self.runtime.state()
        state['reviews']['qa']={'accepted':False,'hash':state['candidate']['hash'],'counterexample':{'input':1,'output':2}}
        self.save(state)
        # Existing fixture permits ONE generation: repair must be denied there.
        self.assertEqual(self.runtime.provider('lead').verified_replans(),[])
        self.runtime.close()
        self.runtime=ProgrammingRuntime(self.path/'repair-budget',contract={'examples':[[1,1],[2,2]]},generator=BoundedExpressionGenerator(),verifiers={'qa':lambda c,g:{'accepted':True},'security':lambda c,g:{'accepted':True}},session_factory=lambda *args:StubSession(),generations=2)
        self.effect('lead','generate','g');state=self.runtime.state()
        state['reviews']['qa']={'accepted':False,'hash':state['candidate']['hash'],'counterexample':{'input':1,'output':2}}
        self.save(state);self.assertTrue(self.runtime.provider('lead').verified_replans())
        state['reviews']['qa']['hash']='0'*64;self.save(state)
        provider=self.runtime.provider('lead');repairs={provider.registry.identifier(n) for n in ('repair','delegate_builder')}
        self.assertFalse(any(offer['action'] in repairs for offer in provider.verified_replans()))
        state['reviews']['qa']['hash']=state['candidate']['hash'];state['enabled']=False;self.save(state)
        self.assertEqual(self.runtime.provider('lead').verified_replans(),[])
    def test_negative_stale_and_modified_code_no_offer(self):
        self.ready();original=self.runtime.state()
        for variant in ('negative','stale','modified'):
            state=json.loads(json.dumps(original))
            if variant=='negative':state['reviews']['qa']['accepted']=False
            elif variant=='stale':state['reviews']['qa']['hash']='0'*64
            else:state['candidate']['files']['solution.py']+='\n# modified\n'
            self.save(state);self.assertEqual(self.runtime.provider('lead').verified_completions(),[])
            with self.assertRaises(PermissionError):self.effect('lead','publish','bad'+variant)
    def test_revoked_offer_and_late_execution_denied(self):
        self.ready();old=self.request('publish');self.runtime.revoke()
        self.assertEqual(self.runtime.provider('lead').verified_completions(),[])
        with self.assertRaises(PermissionError):self.runtime.effect('lead','p',old)
        with self.assertRaises(PermissionError):self.runtime.effect('lead','g',self.request('generate'))
    def test_no_role_escalation_or_receipt_binding_collision(self):
        self.ready()
        with self.assertRaises(PermissionError):self.effect('qa','publish','bad')
        with self.assertRaises(PermissionError):self.effect('builder','generate','g')
        with self.assertRaises(ValueError):self.effect('lead','abstain','g')
        with self.assertRaises(PermissionError):self.runtime.effect('lead','x',ToolRequest('publish','other',0,{'mission':self.runtime.identity}))
    def test_uncertain_attempt_blocks_resend_without_reset(self):
        class Uncertain:
            calls=0
            def generate(self,*args):self.calls+=1;raise OSError('provider connection lost')
        uncertain=Uncertain();self.runtime.generator=uncertain
        with self.assertRaises(OSError):self.effect('lead','generate','g')
        used=self.runtime.state()['used']
        with self.assertRaises(RuntimeError):self.effect('lead','generate','g')
        self.assertEqual(uncertain.calls,1);self.assertEqual(self.runtime.state()['used'],used)
    def test_completion_schema_not_free_text(self):
        spec=ToolDefinition('done','observe',lambda v:{},handler=lambda *a:ToolResult((0,0,0)),completion=lambda v:{'claim':'done'})
        provider=RegisteredProvider(ToolRegistry([spec]),lambda:Observation('e',0,(0,0,0)),lambda g:False)
        with self.assertRaises(ValueError):provider.verified_completions()

if __name__=='__main__':unittest.main()
