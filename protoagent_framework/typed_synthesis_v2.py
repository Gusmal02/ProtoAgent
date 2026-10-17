"""Expanded typed primitives + bounded beam search driven only by examples."""
import hashlib,time,re
from .typed_synthesis import apply as base_apply,compile_python as base_compile,canonical

def apply(rows,instruction,key,value):
    op,arg=instruction
    if op=='map_binary':
        # Binary composition of a column with itself, not a target program.
        fn={'+':lambda x:x+x,'-':lambda x:x-x,'*':lambda x:x*x}[arg]
        return [{**r,value:fn(r[value])} for r in rows]
    if op=='derive_gt':
        column,threshold=arg
        return [{**r,column:r[value]>threshold} for r in rows]
    if op=='group_reduce':
        groups={}
        for r in rows:groups.setdefault(r[key],[]).append(r[value])
        reducer={'count':len,'min':min,'max':max}[arg]
        return [{key:k,value:reducer(values)} for k,values in groups.items()]
    return base_apply(rows,instruction,key,value)

def compile_python(program,key,value):
    segments=[]
    for instruction in program:
        op,arg=instruction
        if op=='map_binary':segments.append(f'    rows = [dict(r, **{{{value!r}: r[{value!r}] {arg} r[{value!r}]}}) for r in rows]')
        elif op=='derive_gt':
            column,threshold=arg
            if not re.fullmatch('[a-zA-Z_][a-zA-Z_0-9]*',column):raise ValueError('column identifier')
            segments.append(f'    rows = [dict(r, **{{{column!r}: r[{value!r}] > {threshold}}}) for r in rows]')
        elif op=='group_reduce':
            reducer={'count':'len','min':'min','max':'max'}[arg]
            segments.extend(['    groups = {}','    for r in rows:',f'        groups.setdefault(r[{key!r}], []).append(r[{value!r}])',f'    rows = [{{{key!r}: k, {value!r}: {reducer}(values)}} for k, values in groups.items()]'])
        else:segments.extend(base_compile([instruction],key,value).splitlines()[2:-1])
    # Validate base identifiers even when program has only new operations.
    base_compile([],key,value)
    return '\n'.join(['def solve(rows):','    rows = [dict(row) for row in rows]']+segments+['    return rows',''])

def execute(program,rows,key,value):
    for instruction in program:rows=apply(rows,instruction,key,value)
    return rows

def distance(states,targets,key,value):
    total=0.
    for rows,target in zip(states,targets):
        total+=3*abs(len(rows)-len(target))
        for a,b in zip(rows,target):
            total+=2*(a.get(key)!=b.get(key))
            for column in set(a)|set(b):
                if column==key:continue
                if column not in a or column not in b:total+=3
                elif type(a[column]) is not type(b[column]):total+=2
                elif type(a[column]) is int:total+=min(abs(a[column]-b[column]),20)/20
                else:total+=float(a[column]!=b[column])
    return total

class TypedTableSynthesizerV2:
    def __init__(self,*,candidates=30000,row_operations=2000000,seconds=20,width=128):
        self.cap=candidates;self.row_cap=row_operations;self.seconds=seconds;self.width=width
        self.used=0;self.rows_used=0;self.rejections=0
    def synthesize(self,contract,examples):
        key,value=contract['key'],contract['value'];derived=contract.get('derived_columns',[])
        if key==value or len(derived)>2 or any(c in (key,value) for c in derived):raise ValueError('column schema')
        for col in [key,value]+derived:
            if type(col) is not str or not re.fullmatch('[a-zA-Z_][a-zA-Z_0-9]*',col):raise ValueError('identifier schema')
        for example in examples:
            for kind in ('input','output'):
                rows=example[kind]
                if type(rows) is not list or len(rows)>100:raise ValueError('table bound')
                for r in rows:
                    if not {key,value}<=set(r)<=set([key,value]+derived) or type(r[key]) is not str or type(r[value]) is not int or abs(r[value])>10000:raise ValueError('typed rows required')
                    if any(type(r[c]) is not bool for c in r if c in derived):raise ValueError('derived bool schema')
        actions=[('filter_gt',n) for n in (-1,0,1)]+[('filter_lt',n) for n in (0,1)]+[('scale',n) for n in (-1,2,3)]+[('offset',n) for n in (-1,1)]+[('group_sum',None),('unique',None),('sort',False),('sort',True)]+[('map_binary',op) for op in ('+','-','*')]+[('group_reduce',r) for r in ('count','min','max')]+[('derive_gt',(c,t)) for c in derived for t in (-1,0,1)]
        initial=[e['input'] for e in examples];targets=[e['output'] for e in examples];target=canonical(targets)
        frontier=[((),initial)];seen={canonical(initial)};began=time.monotonic()
        for depth in range(contract['max_depth']+1):
            following=[]
            for program,states in frontier:
                if canonical(states)==target:
                    source=compile_python(program,key,value)
                    return {'ir':list(program),'source':source,'hash':hashlib.sha256(source.encode()).hexdigest(),'candidates_total':self.used,'row_operations_total':self.rows_used,'rejected_total':self.rejections,'search':'bounded_example_guided_beam','beam_width':self.width}
                if depth==contract['max_depth']:continue
                for instruction in actions:
                    cost=sum(len(rows) for rows in states)
                    if self.used>=self.cap or self.rows_used+cost>self.row_cap or time.monotonic()-began>self.seconds:raise RuntimeError('bounded synthesis exhausted')
                    self.used+=1;self.rows_used+=cost
                    children=[apply(rows,instruction,key,value) for rows in states]
                    # Avoid integer blow-up from repeated multiplication.
                    if any(abs(r[value])>10**8 for rows in children for r in rows):continue
                    identity=canonical(children)
                    if identity!=target:self.rejections+=1
                    if identity not in seen:
                        seen.add(identity);following.append((program+(instruction,),children))
            if not following:break
            following.sort(key=lambda item:distance(item[1],targets,key,value))
            frontier=following[:self.width]
        # Beam pruning is not exhaustive: never claim no solution exists.
        raise RuntimeError('beam frontier exhausted without proof of impossibility')
