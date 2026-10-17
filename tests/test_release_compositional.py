import copy,json,tempfile,unittest
from pathlib import Path
from protoagent_framework.code_generator import sha
from protoagent_framework.compositional_synthesis import CompositionalSynthesizer,SearchStopped
from protoagent_framework.compositional_generator import CompositionalGenerator
from protoagent_framework.project_editing import compose_project,check_project,publish_project_from_host
from p123_support import BASE,contract,oracle,challenges,samples,execute,security


class CompositionalChecks(unittest.TestCase):
    def test_synthesis_compilation_and_counterexample(self):
        c=contract();values=samples(10104,10)+challenges()
        examples=[{'input':x,'output':oracle(x)} for x in values]
        s=CompositionalSynthesizer();r=s.synthesize(c,examples)
        with tempfile.TemporaryDirectory() as d:
            candidate={'files':{'solution.py':r['source']}};candidate['hash']=sha(candidate['files'])
            self.assertTrue(security(candidate,c)['accepted'])
            reserve=samples(61031,40)
            self.assertEqual(execute(candidate,c,reserve,Path(d)/'candidate'),[oracle(x) for x in reserve])
        self.assertLess(s.used,200000);self.assertLess(s.rows_used,12000000)
        self.assertGreaterEqual(r['quality']['compatible_variants'],2)
        self.assertEqual(r['quality']['selected_row_work'],min(r['quality']['variant_row_work']))

    def test_budget_status_is_explicit(self):
        c=contract();s=CompositionalSynthesizer(candidates=1)
        with self.assertRaises(SearchStopped) as found:s.synthesize(c,c['examples'])
        self.assertEqual(found.exception.status,'search_budget_exhausted')

    def test_durable_generator_replay_binding_feedback(self):
        with tempfile.TemporaryDirectory() as d:
            c=contract();g=CompositionalGenerator(Path(d)/'jobs.sqlite')
            try:
                first=g.generate('first',c,[]);before=g.db.execute('SELECT * FROM budget').fetchone()
                self.assertEqual(first,g.generate('first',c,[]));self.assertEqual(before,g.db.execute('SELECT * FROM budget').fetchone())
                with self.assertRaises(ValueError):g.generate('first',{**c,'goal':'other'},[])
                self.assertEqual(g.generate('second',c,[])['generation_status'],'no_progress')
            finally:g.close()
            g=CompositionalGenerator(Path(d)/'jobs.sqlite')
            try:self.assertEqual(first,g.generate('first',c,[]))
            finally:g.close()

    def test_project_patch_protected_scope_and_current_authority(self):
        c=contract(project=True);values=samples(10104,10)+challenges()
        r=CompositionalSynthesizer().synthesize(c,[{'input':x,'output':oracle(x)} for x in values])
        files=compose_project(BASE,r['source']);self.assertTrue(check_project(BASE,files))
        self.assertNotEqual(files['validation.py'],BASE['validation.py']);self.assertEqual(files['cli.py'],BASE['cli.py'])
        bad=copy.deepcopy(files);bad['transforms.py']=bad['transforms.py'].replace('preserved','changed')
        with self.assertRaises(PermissionError):check_project(BASE,bad)
        bad=copy.deepcopy(files);bad['../escape.py']='x'
        with self.assertRaises(ValueError):check_project(BASE,bad)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=root/'base';base.mkdir()
            for name,source in BASE.items():(base/name).write_text(source,encoding='utf8')
            candidate={'files':files,'hash':sha(files)}
            with self.assertRaises(PermissionError):publish_project_from_host(base,root/'denied',sha(BASE),candidate,candidate['hash'],authorize=lambda:False)
            self.assertFalse((root/'denied').exists())
            publish_project_from_host(base,root/'accepted',sha(BASE),candidate,candidate['hash'],authorize=lambda:True)
            self.assertEqual((root/'accepted/APPROVED.sha256').read_text(),candidate['hash'])
            with self.assertRaises(ValueError):publish_project_from_host(base,root/'stale','0'*64,candidate,candidate['hash'],authorize=lambda:True)
        bad={'files':{'solution.py':'def solve(inputs):\n    return open("private").read()\n'}};bad['hash']=sha(bad['files'])
        self.assertFalse(security(bad,contract())['accepted'])

    def test_library_recovers_materialized_code_with_no_new_search(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=contract();g=CompositionalGenerator(root/'jobs',library_path=root/'library')
            try:
                generated=g.generate('generation',c,[]);candidate=generated['candidate']
                reviews={name:{'accepted':True,'hash':candidate['hash'],'reviewer':name,'measurement':name} for name in ('qa','security')}
                # This fixture verifies the memory mechanism; functional CEGIS
                # correctness is checked separately, not inferred from these labels.
                g.remember('publish',candidate,c,reviews)
                before=g.db.execute('SELECT * FROM budget').fetchone()
                recovered=g.recover('recover',c)
                self.assertEqual(recovered['files'],candidate['files'])
                self.assertEqual(before,g.db.execute('SELECT * FROM budget').fetchone())
                self.assertIsNone(g.recover('incompatible',{**c,'goal':'changed contract'}))
            finally:g.close()


if __name__=='__main__':unittest.main()
