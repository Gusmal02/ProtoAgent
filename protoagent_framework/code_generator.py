"""Pluggable code generators. Generation is not admission or execution."""
import ast,hashlib,json,itertools

def sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class TransportCodeGenerator:
    """Use an injected durable transport; no credentials or automatic retries.

    Transport.submit must persist intent/budget before dispatch and block uncertain
    calls. Returned code is inert data until an independent verifier admits it.
    """
    def __init__(self,transport):self.transport=transport
    def generate(self,identity,contract,feedback):
        document={'contents':[{'role':'user','parts':[{'text':json.dumps({'task':contract,'feedback':feedback,'output':'JSON object with files: mapping relative .py paths to Python source. No secrets or hidden tests.'})}]}],
                  'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':4096}}
        response=self.transport.submit(identity,document)
        if 'candidates' in response:
            response=json.loads(response['candidates'][0]['content']['parts'][0]['text'])
        return validate_candidate(response,'external_model')

def validate_candidate(response,author):
    files=response.get('files') if type(response) is dict else None
    if type(files) is not dict or not 1<=len(files)<=8:raise ValueError('files schema')
    for name,source in files.items():
        if type(name) is not str or not name.endswith('.py') or '/' in name or '\\' in name or ':' in name or name.startswith('.'):raise ValueError('flat relative Python path required')
        if type(source) is not str or len(source.encode())>65536:raise ValueError('source budget')
        ast.parse(source) # Syntax only: not execution and not a security verdict.
    return {'files':files,'hash':sha(files),'author':author,'admitted':False}

class BoundedExpressionGenerator:
    """Native finite synthesis from examples; not unrestricted Python synthesis.

    Fixed grammar: x, integer constants -2..2, +,-,*. No task-specific template,
    no eval/exec. Charge every candidate/sample evaluation, including failures.
    """
    def __init__(self,*,evaluations=50000):
        if type(evaluations) is not int or not 1<=evaluations<=100000:raise ValueError('search budget')
        self.limit=evaluations
    def generate(self,identity,contract,feedback):
        samples=contract.get('examples')
        if type(samples) is not list or not 1<=len(samples)<=32:raise ValueError('finite integer examples required')
        if any(type(p) is not list or len(p)!=2 or any(type(v) is not int or abs(v)>1000 for v in p) for p in samples):raise ValueError('sample domain')
        atoms=[('x',tuple(p[0] for p in samples))]+[(str(c),tuple(c for _ in samples)) for c in range(-2,3)]
        target=tuple(p[1] for p in samples);used=0;pool=list(atoms);seen=set()
        for depth in range(3):
            candidates=list(atoms) if depth==0 else itertools.chain.from_iterable(
                ((f'({a}{op}{b})',tuple(fn(x,y) for x,y in zip(av,bv))) for op,fn in (('+',lambda x,y:x+y),('-',lambda x,y:x-y),('*',lambda x,y:x*y)))
                for a,av in tuple(pool) for b,bv in atoms)
            added=[]
            for expression,values in candidates:
                used+=len(samples)
                if used>self.limit:raise RuntimeError('native synthesis budget exhausted')
                if values in seen:continue
                seen.add(values)
                if values==target:
                    result=validate_candidate({'files':{'solution.py':'def solve(x):\n    return '+expression+'\n'}},'native_finite_enumerator')
                    result.update(search_evaluations=used,grammar='integer_expression_v1',identity=identity)
                    return result
                if max(map(abs,values))<=100000:added.append((expression,values))
            pool.extend(added)
        raise RuntimeError('no candidate in finite grammar')
