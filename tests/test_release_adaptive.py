"""Small algorithm regressions; actual verified history exercised by campaign."""
import unittest
from protoagent_framework.adaptive_synthesis import AdaptiveSynthesizer,shape,compile_checked
from protoagent_framework.compositional_synthesis import SearchStopped
from protoagent_framework.typed_synthesis import apply,compile_python


class AdaptiveChecks(unittest.TestCase):
    def test_stable_key_sort_is_distinct_from_key_value_sort(self):
        rows=[{'k':'A','v':3},{'k':'A','v':1},{'k':'B','v':0}]
        self.assertEqual(apply(rows,('sort_key',False),'k','v'),rows)
        self.assertNotEqual(apply(rows,('sort',False),'k','v'),rows)
        source=compile_python([('sort_key',False)],'k','v')
        self.assertIn("key=lambda r: r['k']",source)
    def test_seed_can_be_composed_and_cost_is_charged(self):
        seed=('binary','join_subtract',('input','a'),('input','b'))
        c={'inputs':['a','b','c'],'key':'k','value':'v'}
        values=[{'a':[{'k':'X','v':4}],'b':[{'k':'X','v':1}],'c':[{'k':'X','v':2}]},
                {'a':[{'k':'Y','v':7}],'b':[],'c':[{'k':'Y','v':-2}]}]
        examples=[{'input':values[0],'output':[{'k':'X','v':5}]},{'input':values[1],'output':[{'k':'Y','v':5}]}]
        search=AdaptiveSynthesizer([seed]);result=search.synthesize(c,examples)
        self.assertGreater(search.rows_used,search.used);self.assertEqual(result['seed_count'],1)
        self.assertIn('solve',result['source'])
        self.assertEqual(result['source'],compile_checked(result['dag'],c['inputs'],'k','v'))

    def test_invalid_ir_and_budget_are_explicit(self):
        with self.assertRaises(ValueError):shape(['call','open'],['a'])
        with self.assertRaises(ValueError):shape(['binary','concat',['input','a'],['input','a']],['a'])
        c={'inputs':['a','b'],'key':'k','value':'v'}
        with self.assertRaises(SearchStopped):AdaptiveSynthesizer(candidates=0).synthesize(c,[{'input':{'a':[],'b':[]},'output':[]}])


if __name__=='__main__':unittest.main()
