"""Recoverable search and finite multi-input table DAG construction."""
import json,hashlib,time
from .typed_synthesis import canonical
from .typed_synthesis_v2 import TypedTableSynthesizerV2,apply,distance,compile_python

class RecoveringTableSynthesizer:
    """Iterative widening: abandoned beam paths can be regenerated, costs retained."""
    def __init__(self,*,candidates=200000,row_operations=12000000,seconds=20):
        self.cap=candidates;self.row_cap=row_operations;self.seconds=seconds
        self.used=0;self.rows_used=0;self.rejections=0;self.restarts=[]
    def synthesize(self,contract,examples):
        began=time.monotonic()
        for width in (32,128,512,2048):
            search=TypedTableSynthesizerV2(candidates=self.cap,row_operations=self.row_cap,seconds=max(.001,self.seconds-(time.monotonic()-began)),width=width)
            search.used=self.used;search.rows_used=self.rows_used;search.rejections=self.rejections
            try:
                result=search.synthesize(contract,examples)
                result['recovery_widths']=self.restarts+[width];return result
            except RuntimeError as exc:
                self.restarts.append(width)
                if 'beam frontier' not in str(exc):raise
            finally:self.used=search.used;self.rows_used=search.rows_used;self.rejections=search.rejections
        raise RuntimeError('recoverable frontier exhausted without impossibility proof')

def binary(left,right,operation,key,value):
    if operation=='concat':return [dict(r) for r in left+right]
    if len({r[key] for r in left})!=len(left) or len({r[key] for r in right})!=len(right):raise ValueError('join requires unique keys; group or deduplicate first')
    indexed={r[key]:r[value] for r in right}
    if operation=='join_subtract':return [{key:r[key],value:r[value]-indexed.get(r[key],0)} for r in left]
    if operation=='join_add':return [{key:r[key],value:r[value]+indexed.get(r[key],0)} for r in left]
    raise ValueError('binary operator')

def evaluate(expr,inputs,key,value):
    if expr[0]=='input':return inputs[expr[1]]
    if expr[0]=='unary':return apply(evaluate(expr[2],inputs,key,value),expr[1],key,value)
    return binary(evaluate(expr[2],inputs,key,value),evaluate(expr[3],inputs,key,value),expr[1],key,value)

def compile_dag(expr,key,value):
    lines=['def solve(inputs):'];cache={};counter=0
    def emit(node):
        nonlocal counter
        token=canonical(node)
        if token in cache:return cache[token]
        if node[0]=='input':
            var=f't{counter}';counter+=1;lines.append(f'    {var} = [dict(r) for r in inputs[{node[1]!r}]]')
        elif node[0]=='unary':
            parent=emit(node[2]);var=f't{counter}';counter+=1
            lines.append(f'    rows = {parent}')
            lines.extend(compile_python([node[1]],key,value).splitlines()[2:-1]);lines.append(f'    {var} = rows')
        else:
            left=emit(node[2]);right=emit(node[3]);var=f't{counter}';counter+=1
            if node[1]=='concat':lines.append(f'    {var} = [dict(r) for r in {left} + {right}]')
            else:
                sign='-' if node[1]=='join_subtract' else '+'
                lines.append('    indexed = {r['+repr(key)+']:r['+repr(value)+'] for r in '+right+'}')
                lines.append(f'    {var} = [{{{key!r}:r[{key!r}], {value!r}:r[{value!r}] {sign} indexed.get(r[{key!r}],0)}} for r in {left}]')
        cache[token]=var;return var
    result=emit(expr);return '\n'.join(lines+[f'    return {result}',''])

class MultiInputSynthesizer:
    """Typed bottom-up DAG search with dependency/opcode diversity; no target route."""
    def __init__(self,*,candidates=200000,row_operations=12000000,seconds=20,width=256):
        self.cap=candidates;self.row_cap=row_operations;self.seconds=seconds;self.width=width
        self.used=0;self.rows_used=0;self.rejections=0
    def synthesize(self,contract,examples):
        key,value=contract['key'],contract['value'];names=contract['inputs']
        if not 2<=len(names)<=3:raise ValueError('two or three inputs required')
        for example in examples:
            if set(example['input'])!=set(names):raise ValueError('input schema')
            for rows in list(example['input'].values())+[example['output']]:
                if type(rows) is not list or len(rows)>100 or any(set(r)!={key,value} or type(r[key]) is not str or type(r[value]) is not int for r in rows):raise ValueError('typed table schema')
        targets=[e['output'] for e in examples];target=canonical(targets);began=time.monotonic()
        actions=[('filter_gt',n) for n in (-1,0,1)]+[('filter_lt',0),('scale',-1),('scale',2),('scale',3),('offset',-1),('offset',1),('unique',None),('group_sum',None),('sort',False),('sort',True)]
        pools={0:[]};seen=set()
        for name in names:
            states=[e['input'][name] for e in examples]
            pools[0].append((('input',name),states,frozenset([name]),'input'))
        def candidate(expr,states,deps,family):
            cost=sum(len(rows) for rows in states)
            if self.used>=self.cap or self.rows_used+cost>self.row_cap or time.monotonic()-began>self.seconds:raise RuntimeError('bounded synthesis exhausted')
            self.used+=1;self.rows_used+=cost
            if any(len(rows)>100 or any(abs(r[value])>10**8 for r in rows) for rows in states):return None
            identity=canonical(states)
            if identity==target:
                source=compile_dag(expr,key,value)
                return {'dag':expr,'source':source,'hash':hashlib.sha256(source.encode()).hexdigest(),'candidates_total':self.used,'row_operations_total':self.rows_used}
            self.rejections+=1
            token=(deps,identity)
            if token not in seen:seen.add(token);following.append((expr,states,deps,family))
            return None
        for depth in range(1,contract['max_depth']+1):
            following=[]
            for expr,states,deps,_ in pools.get(depth-1,[]):
                for instruction in actions:
                    result=candidate(('unary',instruction,expr),[apply(rows,instruction,key,value) for rows in states],deps,instruction[0])
                    if result:return result
            for left_cost in range(depth):
                right_cost=depth-1-left_cost
                # All binary depths considered; bounded alternatives on BOTH
                # branches, grouped by input provenance rather than target labels.
                def shortlist(pool):
                    groups={}
                    for item in pool:
                        group=groups.setdefault(item[2],[])
                        if len(group)<4:group.append(item)
                    return [item for group in groups.values() for item in group]
                for left,ls,ld,_ in shortlist(pools.get(left_cost,[])):
                    for right,rs,rd,_ in shortlist(pools.get(right_cost,[])):
                        if ld==rd:continue
                        for op in ('concat','join_subtract','join_add'):
                            try:states=[binary(a,b,op,key,value) for a,b in zip(ls,rs)]
                            except ValueError:continue
                            result=candidate(('binary',op,left,right),states,ld|rd,op)
                            if result:return result
            if not following:pools[depth]=[];continue
            following.sort(key=lambda item:distance(item[1],targets,key,value))
            # Reserve representation of each dependency/operator family before
            # filling remaining slots by example discrepancy.
            buckets={}
            for item in following:buckets.setdefault((item[2],item[3]),[]).append(item)
            selected=[]
            for values in buckets.values():selected.extend(values[:max(1,self.width//max(1,len(buckets)))])
            pools[depth]=sorted(selected,key=lambda item:distance(item[1],targets,key,value))[:self.width]
        raise RuntimeError('multi-input frontier exhausted without impossibility proof')
