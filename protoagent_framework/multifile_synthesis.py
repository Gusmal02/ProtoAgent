"""Finite binary-expression synthesis plus a declared module-interface compiler.

Compiler wiring/storage are Codex infrastructure, not inferred architecture.
Only operation expressions are selected from examples; no name-specific rules.
"""
import ast,itertools
from .code_generator import validate_candidate

class MultiFileGenerator:
    def __init__(self,evaluations=50000):self.limit=evaluations
    def generate(self,identity,contract,feedback):
        if contract.get('profile')!='bounded_keyed_integer_reducer_v1':raise ValueError('unsupported profile')
        examples=contract.get('operations')
        if type(examples) is not dict or not 1<=len(examples)<=8:raise ValueError('operations')
        used=0;expressions={};discovered={}
        for name,samples in examples.items():
            if type(name) is not str or not 1<=len(name)<=128:raise ValueError('operation name')
            if type(samples) is not list or not 2<=len(samples)<=16:raise ValueError('examples')
            if any(type(p) is not list or len(p)!=3 or any(type(v) is not int or abs(v)>10**6 for v in p) for p in samples):raise ValueError('integer triples')
            atoms=[('state',tuple(p[0] for p in samples)),('argument',tuple(p[1] for p in samples))]+[(str(c),tuple(c for _ in samples)) for c in (-1,0,1)]
            target=tuple(p[2] for p in samples);frontier=list(atoms);pool=list(atoms);seen=set();chosen=None
            for depth in range(3):
                candidates=atoms if depth==0 else ((f'({a}{op}{b})',tuple(fn(x,y) for x,y in zip(av,bv))) for a,av in tuple(frontier) for b,bv in atoms for op,fn in (('+',lambda x,y:x+y),('-',lambda x,y:x-y),('*',lambda x,y:x*y)))
                following=[]
                for expression,values in candidates:
                    used+=len(samples)
                    if used>self.limit:raise RuntimeError('native synthesis budget exhausted')
                    if values in seen:continue
                    seen.add(values)
                    if values==target:chosen=expression;break
                    if max(map(abs,values))<=10**9:following.append((expression,values))
                if chosen is not None:break
                frontier=following;pool.extend(following)
            if chosen is None:raise RuntimeError('no candidate in finite grammar')
            expressions[name]=chosen;discovered[name]={'expression':chosen,'cumulative_evaluations':used}
        rules=['def reduce(state, operation, argument):']
        for name,expression in expressions.items():rules.extend([f'    if operation == {name!r}:',f'        return {expression}'])
        rules.append('    raise ValueError("unknown operation")')
        files={'rules.py':'\n'.join(rules)+'\n',
               'repository.py':'from protoagent_framework.reducer_store import ReducerStore\nfrom rules import reduce\n\nclass Repository:\n    def __init__(self, path):\n        self.store = ReducerStore(path)\n    def apply(self, token, tenant, identity, key, operation, argument):\n        return self.store.apply(reduce, token, tenant, identity, key, operation, argument)\n    def report(self, token, tenant):\n        return self.store.report(token, tenant)\n',
               'service.py':'from repository import Repository\n\nclass Service:\n    def __init__(self, path):\n        self.repository = Repository(path)\n    def execute(self, token, tenant, identity, key, operation, argument):\n        return self.repository.apply(token, tenant, identity, key, operation, argument)\n    def report(self, token, tenant):\n        return self.repository.report(token, tenant)\n'}
        for source in files.values():ast.parse(source)
        result=validate_candidate({'files':files},'finite_expression_search_with_Codex_module_compiler')
        result.update(identity=identity,search_evaluations=used,grammar='bounded_binary_expression_module_compiler_v1',provenance={'selected_rules':discovered,'module_layout':'Codex_fixed_interface_compiler','storage':'Codex_trusted_reducer_store','feedback_used':False})
        return result
