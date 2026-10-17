import subprocess,sys,tempfile,unittest
from pathlib import Path
from protoagent_framework.verified_tool_memory import VerifiedToolMemory

class LibraryChecks(unittest.TestCase):
    def test_register_recover_revalidate_use_reopen_without_authority(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();(source/'runner.py').write_text('def run(x):\n    return x + 1\n',encoding='utf8')
            memory=VerifiedToolMemory(root/'library.sqlite')
            try:
                first={'accepted':True,'checks':1,'measurement_hash':'first'}
                identity=memory.register_from_host(source,family='increment',contract='v1',author='trusted-test-fixture',receipt='r1',proof=first)
                self.assertFalse(memory.eligible(identity,'increment','v1'))
                memory.register_from_host(source,family='increment',contract='v1',author='trusted-test-fixture',receipt='r2',proof={'accepted':True,'checks':2,'measurement_hash':'second'})
                self.assertTrue(memory.eligible(identity,'increment','v1'));self.assertIn(identity,memory.recover_candidates('increment'))
                delivered=memory.materialize(identity,root/'delivered')
                self.assertEqual((delivered/'runner.py').read_text(),(source/'runner.py').read_text())
                # Host verifier, not library familiarity, checks current content.
                def verifier(path):
                    # Run only this known trusted fixture, with no bytecode
                    # writes into the owned materialization directory.
                    process=subprocess.run([sys.executable,'-I','-B','-c',"import runpy,sys; module=runpy.run_path(sys.argv[1]); assert module['run'](4)==5",str(path/'runner.py')],capture_output=True,text=True,timeout=10)
                    return {'accepted':process.returncode==0 and (path/'runner.py').read_text()==(source/'runner.py').read_text(),'checks':1,'measurement_hash':'third'}
                self.assertTrue(memory.revalidate_from_host(identity,delivered,family='increment',contract='v2',verifier=verifier,receipt='r3')['accepted'])
                self.assertFalse(memory.eligible(identity,'increment','v2'))
                memory.close();memory=VerifiedToolMemory(root/'library.sqlite');self.assertIn(identity,memory.recover_candidates('increment'))
                (delivered/'runner.py').write_text('raise RuntimeError("tampered")',encoding='utf8')
                with self.assertRaises(ValueError):memory.revalidate_from_host(identity,delivered,family='increment',contract='v2',verifier=verifier,receipt='r4')
            finally:memory.close()
