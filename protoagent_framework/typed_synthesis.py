"""Finite typed table synthesis, generic primitives, no LLM or task route."""
from collections import deque
import hashlib,json,re,time

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))

def apply(rows,instruction,key,value):
    op,arg=instruction
    if op=='filter_gt':return [dict(r) for r in rows if r[value]>arg]
    if op=='filter_lt':return [dict(r) for r in rows if r[value]<arg]
    if op=='scale':return [{**r,value:r[value]*arg} for r in rows]
    if op=='offset':return [{**r,value:r[value]+arg} for r in rows]
    if op=='sort':return sorted((dict(r) for r in rows),key=lambda r:(r[key],r[value]),reverse=arg)
    if op=='group_sum':
        sums={}
        for r in rows:sums[r[key]]=sums.get(r[key],0)+r[value]
        return [{key:k,value:v} for k,v in sums.items()]
    if op=='unique':
        out=[];seen=set()
        for r in rows:
            identity=(r[key],r[value])
            if identity not in seen:seen.add(identity);out.append(dict(r))
        return out
    raise ValueError('unknown typed operation')

def execute(program,rows,key,value):
    for instruction in program:rows=apply(rows,instruction,key,value)
    return rows

def compile_python(program,key,value):
    """Compile IR to stdlib-only Python; no source text from the task is pasted."""
    if not re.fullmatch('[a-zA-Z_][a-zA-Z_0-9]*',key) or not re.fullmatch('[a-zA-Z_][a-zA-Z_0-9]*',value):raise ValueError('identifier schema')
    lines=['def solve(rows):','    rows = [dict(row) for row in rows]']
    for op,arg in program:
        if op in ('filter_gt','filter_lt'):
            sign='>' if op=='filter_gt' else '<';lines.append(f'    rows = [r for r in rows if r[{value!r}] {sign} {arg!r}]')
        elif op in ('scale','offset'):
            sign='*' if op=='scale' else '+';lines.append(f'    rows = [dict(r, **{{{value!r}: r[{value!r}] {sign} {arg!r}}}) for r in rows]')
        elif op=='sort':lines.append(f'    rows = sorted(rows, key=lambda r: (r[{key!r}], r[{value!r}]), reverse={arg!r})')
        elif op=='group_sum':lines.extend(['    sums = {}','    for r in rows:',f'        sums[r[{key!r}]] = sums.get(r[{key!r}], 0) + r[{value!r}]',f'    rows = [{{{key!r}: k, {value!r}: v}} for k, v in sums.items()]'])
        elif op=='unique':lines.extend(['    seen = set()','    result = []','    for r in rows:',f'        identity = (r[{key!r}], r[{value!r}])','        if identity not in seen:','            seen.add(identity)','            result.append(r)','    rows = result'])
        else:raise ValueError('unknown IR opcode')
    return '\n'.join(lines+['    return rows',''])

class TypedTableSynthesizer:
    def __init__(self,*,candidates=30000,row_operations=2000000,seconds=20):
        self.cap=candidates;self.row_cap=row_operations;self.seconds=seconds
        self.used=0;self.rows_used=0;self.rejections=0
    def synthesize(self,contract,examples):
        key,value=contract['key'],contract['value']
        if key==value:raise ValueError('distinct columns required')
        for example in examples:
            for rows in (example['input'],example['output']):
                if type(rows) is not list or len(rows)>100:raise ValueError('table bound')
                if any(set(r)!={key,value} or type(r[key]) is not str or type(r[value]) is not int or abs(r[value])>10000 for r in rows):raise ValueError('typed rows required')
        # Vocabulary fixed across problems. No target plan or optimal ranking.
        actions=[('filter_gt',n) for n in (-1,0,1)]+[('filter_lt',n) for n in (0,1)]+[('scale',n) for n in (-1,2,3)]+[('offset',n) for n in (-1,1)]+[('group_sum',None),('unique',None),('sort',False),('sort',True)]
        start=[e['input'] for e in examples];target=canonical([e['output'] for e in examples])
        queue=deque([((),start)]);seen={canonical(start)};began=time.monotonic()
        while queue:
            program,states=queue.popleft()
            if canonical(states)==target:
                source=compile_python(program,key,value)
                return {'ir':list(program),'source':source,'hash':hashlib.sha256(source.encode()).hexdigest(),'candidates_total':self.used,'row_operations_total':self.rows_used,'rejected_total':self.rejections,'source_type':f'Table[{key}:str,{value}:int]','target_type':f'Table[{key}:str,{value}:int]'}
            if len(program)>=contract['max_depth']:continue
            for instruction in actions:
                cost=sum(len(rows) for rows in states)
                if self.used>=self.cap or self.rows_used+cost>self.row_cap or time.monotonic()-began>self.seconds:raise RuntimeError('bounded synthesis exhausted')
                self.used+=1;self.rows_used+=cost
                children=[apply(rows,instruction,key,value) for rows in states]
                fingerprint=canonical(children)
                if fingerprint!=target:self.rejections+=1
                if fingerprint not in seen:seen.add(fingerprint);queue.append((program+(instruction,),children))
        raise RuntimeError('no program in grammar')
