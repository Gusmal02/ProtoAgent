"""Finite composition from verified historical DAGs, not learned primitives."""
import json
import time
from .code_generator import sha
from .capability_reuse import CapabilityReuseGenerator
from .compositional_synthesis import SearchStopped
from .typed_synthesis import canonical
from .typed_synthesis_v2 import apply
from .typed_synthesis_v3 import evaluate,compile_dag


ACTIONS=[('filter_gt',n) for n in (-1,0,1)]+[('filter_lt',0),('scale',-1),('scale',2),('scale',3),('offset',-1),('offset',1),('unique',None),('group_sum',None),('sort',False),('sort',True),('sort_key',False),('sort_key',True)]


def shape(expr,names,depth=0):
    if depth>12 or not isinstance(expr,(tuple,list)) or not expr:raise ValueError('DAG shape')
    if expr[0]=='input' and len(expr)==2 and expr[1] in names:return 1,frozenset([expr[1]])
    if expr[0]=='unary' and len(expr)==3 and tuple(expr[1]) in ACTIONS:
        n,deps=shape(expr[2],names,depth+1);return n+1,deps
    if expr[0]=='binary' and len(expr)==4 and expr[1] in ('concat','join_add','join_subtract'):
        a,ad=shape(expr[2],names,depth+1);b,bd=shape(expr[3],names,depth+1)
        if ad & bd:raise ValueError('overlapping input dependencies')
        return a+b+1,ad|bd
    raise ValueError('DAG opcode')


def compile_checked(expr,names,key,value):
    count,_=shape(expr,names)
    if count>32:raise ValueError('DAG node bound')
    lines=compile_dag(expr,key,value).splitlines();safe=[lines[0],'    _validate(inputs)']
    for index,line in enumerate(lines[1:],1):
        if line.startswith('    indexed = '):
            right=line.split(' for r in ')[1].rstrip('}')
            left=lines[index+1].split(' for r in ')[1].split(']')[0]
            safe += [f'    _unique_keys({left})',f'    _unique_keys({right})']
        safe.append(line)
    prelude=('def _validate(inputs):\n'
        f'    if type(inputs) is not dict or set(inputs) != set({tuple(names)!r}): raise ValueError("input names")\n'
        '    for rows in inputs.values():\n'
        '        if type(rows) is not list or len(rows) > 100: raise ValueError("table bound")\n'
        f'        if any(type(r) is not dict or set(r) != set({(key,value)!r}) or type(r[{key!r}]) is not str or type(r[{value!r}]) is not int or abs(r[{value!r}]) > 10000 for r in rows): raise ValueError("typed table schema")\n'
        'def _unique_keys(rows):\n'
        f'    if len({{r[{key!r}] for r in rows}}) != len(rows): raise ValueError("join requires unique keys")\n')
    return prelude+'\n'.join(safe)+'\n'


class AdaptiveSynthesizer:
    def __init__(self,seeds=(),candidates=200000,row_operations=12000000,seconds=20):
        self.seeds=list(seeds);self.cap=candidates;self.row_cap=row_operations;self.seconds=seconds
        self.used=self.rows_used=0;self.elapsed=0.

    def synthesize(self,contract,examples):
        names,key,value=contract['inputs'],contract['key'],contract['value']
        if not 2<=len(names)<=3 or len(set(names))!=len(names) or key==value or not all(type(n) is str and n.isidentifier() for n in names+[key,value]):raise ValueError('typed interfaces')
        if not 1<=len(examples)<=32:raise ValueError('example bound')
        for e in examples:
            if set(e['input'])!=set(names):raise ValueError('input names')
            for rows in list(e['input'].values())+[e['output']]:
                if type(rows) is not list or len(rows)>100 or any(type(r) is not dict or set(r)!={key,value} or type(r[key]) is not str or type(r[value]) is not int or abs(r[value])>10000 for r in rows):raise ValueError('typed examples')
        began=time.monotonic();target=[e['output'] for e in examples];pool=[];seen=set()
        row_bound=sum(len(t) for e in examples for t in e['input'].values())
        def consider(expr):
            count,deps=shape(expr,names)
            if count>32:return None
            cost=count*row_bound
            if self.used>=self.cap or self.rows_used+cost>self.row_cap or self.elapsed+time.monotonic()-began>=self.seconds:raise SearchStopped('search_budget_exhausted')
            self.used+=1;self.rows_used+=cost
            try:states=[evaluate(expr,e['input'],key,value) for e in examples]
            except ValueError:return None
            if any(len(rows)>100 or any(abs(r[value])>10**8 for r in rows) for rows in states):return None
            if states==target:
                source=compile_checked(expr,names,key,value)
                return {'dag':expr,'source':source,'grammar':'verified_seed_composition_v1',
                        'seed_count':len(self.seeds),'candidates_total':self.used,'row_operations_total':self.rows_used}
            token=(deps,canonical(states))
            if token not in seen:seen.add(token);following.append((expr,deps))
            return None
        try:
            following=[]
            for seed in self.seeds+[('input',name) for name in names]:
                result=consider(seed)
                if result:return result
            pool=following
            for _ in range(8):
                following=[]
                for expr,_ in pool:
                    for action in ACTIONS:
                        result=consider(('unary',action,expr))
                        if result:return result
                for left,ld in pool:
                    for right,rd in pool:
                        if ld & rd:continue
                        for op in ('join_add','join_subtract','concat'):
                            result=consider(('binary',op,left,right))
                            if result:return result
                if not following:break
                pool+=following
            raise SearchStopped('frontier_exhausted')
        finally:self.elapsed+=time.monotonic()-began


class AdaptiveReuseGenerator(CapabilityReuseGenerator):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS experiences(hash TEXT PRIMARY KEY,context TEXT,contract TEXT,dag TEXT)');self.db.commit()

    def remember(self,operation,candidate,contract,reviews):
        super().remember(operation,candidate,contract,reviews)
        if set(candidate['files'])!={'solution.py'}:return
        for raw, in self.db.execute("SELECT result FROM jobs WHERE state='done'"):
            result=json.loads(raw)
            if result.get('candidate',{}).get('hash')!=candidate['hash']:continue
            dag=result['provenance']['dag']
            if compile_checked(dag,contract['inputs'],contract['key'],contract['value'])!=candidate['files']['solution.py']:raise ValueError('DAG/source binding')
            with self.db:self.db.execute('INSERT OR REPLACE INTO experiences VALUES(?,?,?,?)',(candidate['hash'],sha(contract),json.dumps(contract),json.dumps(dag)))
            break

    def make_search(self,contract):
        if len(contract['inputs'])==2:return super().make_search(contract)
        seeds=[]
        if self.mode!='off':
            for artifact,context,raw,ir in self.db.execute('SELECT hash,context,contract,dag FROM experiences ORDER BY hash LIMIT 16'):
                old=json.loads(raw);dag=json.loads(ir)
                if old['key']!=contract['key'] or old['value']!=contract['value'] or not set(old['inputs'])<=set(contract['inputs']):continue
                records=self.db.execute('SELECT identity,candidate FROM capabilities WHERE context=?',(context,)).fetchall()
                for identity,candidate_raw in records:
                    candidate=json.loads(candidate_raw)
                    if candidate['hash']!=artifact or not self.library.eligible(identity,'typed_table',context):continue
                    if sha(candidate['files'])!=artifact or compile_checked(dag,old['inputs'],old['key'],old['value'])!=candidate['files']['solution.py']:raise ValueError('historical DAG integrity')
                    seeds.append(dag);break
        return AdaptiveSynthesizer(seeds)
