import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from protoagent_framework import Session,create_session,Observation,ToolDefinition,ToolRegistry,RegisteredProvider,ToolResult,ToolRequest
from protoagent_framework.engine import Engine
from protoagent_framework.durable_counter import DurableCounter
from protoagent_framework.code_generator import BoundedExpressionGenerator
from protoagent_framework.programming_runtime import ProgrammingRuntime

class MotorChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        torch.set_num_threads(1)
    def test_actual_motor_programming_closes_after_reviews(self):
        with tempfile.TemporaryDirectory() as d:
            def factory(root,actor,budget):return Session(root/(actor+'.sqlite'),actor,Engine(nodes=4,seed=881,config={'enable_evidence_exploration':True,'evidence_exploration_after':2}),budget=budget,goal={'accepted':True})
            with ProgrammingRuntime(Path(d),contract={'examples':[[1,1],[2,2]]},generator=BoundedExpressionGenerator(),verifiers={'qa':lambda c,g:{'accepted':True},'security':lambda c,g:{'accepted':True}},session_factory=factory,steps=32,generations=2) as runtime:
                result=runtime.run();self.assertEqual(result['state']['status'],'completed')
                self.assertTrue(all(result['audit'].values()));self.assertEqual(result['state']['events'][-1]['tool'],'publish')
                self.assertTrue(any(t.get('verified_completion',{}).get('selected') for t in result['traces']))
                self.assertIn('abstain',[s.name for s in runtime.provider('lead').registry.tools.values()])
    def test_legacy_session_reopens_without_budget_reset_and_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);provider=DurableCounter(root/'native',target=2)
            class IncrementOnly:
                def __getattr__(self,name):return getattr(provider,name)
                def legal_actions(self):return [0]
            session=create_session(root/'session','s',nodes=4,budget=8,goal={'target':2})
            try:
                session.start();session.step(IncrementOnly());before=session.checkpoint();session.pause();session.close()
                session=Session.resume(root/'session','s');self.assertEqual(session.checkpoint()['used'],before['used'])
                self.assertEqual(session.run(IncrementOnly())['checkpoint']['status'],'completed')
            finally:session.close();provider.close()
    def test_physical_cuts_before_effect_and_after_commit(self):
        worker=Path(__file__).with_name('release_crash_worker.py')
        with tempfile.TemporaryDirectory() as d:
            for point in ('operation_prepared','native_committed'):
                root=Path(d)/point
                cut=subprocess.run([sys.executable,'-I',str(worker),str(root),point],capture_output=True,text=True,timeout=45)
                self.assertEqual(cut.returncode,87,cut.stderr)
                resumed=subprocess.run([sys.executable,'-I',str(worker),str(root),point],capture_output=True,text=True,timeout=45)
                self.assertEqual(resumed.returncode,0,resumed.stderr);result=json.loads(resumed.stdout)
                self.assertEqual(result['value'],2);self.assertEqual(result['receipts'],2);self.assertTrue(result['audit'])
                self.assertEqual(result['checkpoint']['used'],2);self.assertIsNone(result['checkpoint']['pending'])
    def test_publish_commit_before_lead_checkpoint_recovers_once(self):
        worker=Path(__file__).with_name('release_programming_worker.py')
        with tempfile.TemporaryDirectory() as d:
            command=[sys.executable,'-I',str(worker),d]
            cut=subprocess.run(command,capture_output=True,text=True,timeout=60);self.assertEqual(cut.returncode,88,cut.stderr)
            before=json.loads((Path(d)/'cut.json').read_text())
            resumed=subprocess.run(command,capture_output=True,text=True,timeout=60);self.assertEqual(resumed.returncode,0,resumed.stderr)
            result=json.loads(resumed.stdout);self.assertEqual(result['status'],'completed');self.assertEqual(result['used'],before['used'])
            self.assertEqual(sum(e['tool']=='publish' for e in result['events']),1);self.assertIn('lead',result['reconciled'])
            self.assertTrue(all(result['audit'].values()));self.assertTrue(all(v['status']=='completed' and v['pending'] is None for v in result['sessions'].values()))

if __name__=='__main__':unittest.main()
