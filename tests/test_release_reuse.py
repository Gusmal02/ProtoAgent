"""Reuse safety and local human handoff regression; no hostile code execution."""
import json
import tempfile
import unittest
from pathlib import Path
from protoagent_framework.capability_reuse import CapabilityReuseGenerator,descriptor
from protoagent_framework.community import prepare_review,decide
from protoagent_framework.code_generator import sha


class ReuseChecks(unittest.TestCase):
    def test_descriptor_is_public_interface_not_answer(self):
        c={'inputs':['a','b'],'key':'k','value':'v','examples':[1],'goal':'first'}
        self.assertEqual(descriptor(c),descriptor({**c,'examples':[2],'goal':'new'}))
        self.assertNotEqual(descriptor(c),descriptor({**c,'inputs':['c','d']}))

    def test_retrieval_replay_collision_and_uncertainty(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g=CapabilityReuseGenerator(root/'jobs',library_path=root/'library',verifier=lambda *_:{'accepted':False,'checks':1},mode='off')
            try:
                self.assertIsNone(g.recover('r',{'goal':'one'}))
                before=list(g.db.execute('SELECT * FROM retrievals'))
                self.assertIsNone(g.recover('r',{'goal':'one'}));self.assertEqual(before,list(g.db.execute('SELECT * FROM retrievals')))
                with self.assertRaises(ValueError):g.recover('r',{'goal':'two'})
                with g.db:g.db.execute('INSERT INTO retrievals VALUES(?,?,?,?,?)',('pending','b','reserved',None,'{}'))
                with self.assertRaises(RuntimeError):g.recover('new',{})
                with self.assertRaises(RuntimeError):g.generate('g',{},[])
            finally:g.close()

    def test_human_decision_is_hash_bound_and_no_overwrite(self):
        c={'files':{'solution.py':'def solve(x):\n    return x\n'},'author':'test'};c['hash']=sha(c['files'])
        reviews={n:{'accepted':True,'hash':c['hash']} for n in ('qa','security')}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            prepare_review(root/'accept',c,{'goal':'exercise'},reviews)
            self.assertEqual(decide(root/'accept',decision='approve',reviewer='test-only')['artifact_hash'],c['hash'])
            with self.assertRaises(FileExistsError):decide(root/'accept',decision='reject',reviewer='test-only')
            prepare_review(root/'tamper',c,{},reviews)
            (root/'tamper/files/solution.py').write_text('def solve(x): return 0',encoding='utf8')
            with self.assertRaises(ValueError):decide(root/'tamper',decision='approve',reviewer='test-only')
            prepare_review(root/'reject',c,{},reviews)
            self.assertEqual(decide(root/'reject',decision='reject',reviewer='test-only')['decision'],'reject')
            bad={**reviews,'security':{'accepted':False,'hash':c['hash']}}
            with self.assertRaises(PermissionError):prepare_review(root/'denied',c,{},bad)


if __name__=='__main__':unittest.main()
