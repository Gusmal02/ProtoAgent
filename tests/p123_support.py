"""Public test fixture; oracle is evaluator-only, never passed to constructor."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
from protoagent_framework.code_generator import sha
from protoagent_framework.project_editing import check_source,check_project


BASE = {
    'transforms.py': 'def unchanged():\n    return "preserved"\n\ndef transform(inputs):\n    return inputs["sales"]\n',
    'validation.py': 'def marker():\n    return "preserved"\n\ndef validate_inputs(inputs):\n    if type(inputs) is not dict: raise ValueError("mapping")\n',
    'cli.py': 'import json,sys\nfrom transforms import transform\nfrom validation import validate_inputs\n\ndef main():\n    value=json.load(sys.stdin)\n    validate_inputs(value)\n    print(json.dumps(transform(value)))\n\nif __name__=="__main__": main()\n'
}


def oracle(inputs, include_zero=False):
    results=[]
    for name in ('sales','returns'):
        seen=set();totals={}
        for row in inputs[name]:
            identity=(row['group'],row['amount'])
            if identity in seen:continue
            seen.add(identity)
            if row['amount']>0 or include_zero and name=='sales' and row['amount']==0:
                totals[row['group']]=totals.get(row['group'],0)+row['amount']
        results.append(totals)
    return [{'group':k,'amount':results[0][k]-results[1].get(k,0)} for k in sorted(results[0])]


def samples(seed,count):
    rng=random.Random(seed);values=[]
    for _ in range(count):
        value={}
        for name in ('sales','returns'):
            table=[{'group':rng.choice(['A','B','C']),'amount':rng.randint(-2,4)} for _ in range(rng.randint(0,6))]
            if table:table.append(dict(table[0]))
            value[name]=table
        values.append(value)
    return values


def challenges():
    return [
        {'sales':[{'group':'A','amount':3}], 'returns':[{'group':'A','amount':-1}]},
        {'sales':[{'group':'A','amount':0}], 'returns':[]},
        {'sales':[], 'returns':[{'group':'B','amount':2}]},
        {'sales':[{'group':'B','amount':1},{'group':'B','amount':1},{'group':'A','amount':2}],
         'returns':[{'group':'B','amount':1},{'group':'B','amount':1}]}
    ]


def contract(project=False,include_zero=False):
    data=samples(10104,10)
    result={'key':'group','value':'amount','inputs':['sales','returns'],'branch_depth':3,
            'goal':'Reconcile unique positive sales and positive returns by group; sorted report. '+('Include zero-valued sales groups.' if include_zero else 'Exclude zero-valued sales groups.'),
            'examples':[{'input':v,'output':oracle(v,include_zero)} for v in data]}
    if project:result['project_files']=copy.deepcopy(BASE)
    return result


def security(candidate,c):
    try:
        if sha(candidate['files'])!=candidate['hash']:raise ValueError('candidate hash')
        if 'project_files' in c:check_project(c['project_files'],candidate['files'])
        else:
            if set(candidate['files'])!={'solution.py'}:raise ValueError('file manifest')
            check_source(candidate['files']['solution.py'])
        return {'accepted':True,'scope':'trusted_compiler_subset_not_OS_sandbox'}
    except (ValueError,PermissionError,SyntaxError) as exc:
        return {'accepted':False,'reason':str(exc)}


def execute(candidate,c,values,root):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    for name,source in candidate['files'].items():(root/name).write_text(source,encoding='utf8')
    worker=Path(__file__).with_name('p123_worker.py')
    config={'inputs':values,'source':str(root/'solution.py'),'folder':str(root),'project':'project_files' in c}
    proc=subprocess.run([sys.executable,'-I','-B',str(worker)],input=json.dumps(config),capture_output=True,text=True,timeout=20)
    if proc.returncode:raise RuntimeError('candidate execution:'+proc.stderr[-1500:])
    return json.loads(proc.stdout)


def qa_factory(root,include_zero=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);calls=[]
    values=samples(10104,10)+challenges()
    def qa(candidate,c):
        safe=security(candidate,c)
        if not safe['accepted']:return safe
        outputs=execute(candidate,c,values,root/('call-'+str(len(calls))))
        calls.append(candidate['hash'])
        for value,actual in zip(values,outputs):
            expected=oracle(value,include_zero)
            if actual!=expected:return {'accepted':False,'counterexample':{'input':value,'output':expected},'observed':actual}
        return {'accepted':True,'development_cases':len(values),'hash':candidate['hash']}
    return qa,calls
