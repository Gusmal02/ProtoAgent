"""Independent imperative evaluator; never passed as a synthesis primitive."""
import random


def expected(inputs,kind):
    maps=[]
    for name in ('sales','returns'):
        seen=set();totals={}
        for row in inputs[name]:
            pair=(row['group'],row['amount'])
            if pair in seen:continue
            seen.add(pair)
            if row['amount']>0:totals[row['group']]=totals.get(row['group'],0)+row['amount']
        maps.append(totals)
    report=[{'group':k,'amount':maps[0][k]-maps[1].get(k,0)} for k in sorted(maps[0])]
    if kind=='append':return sorted(report+[dict(r) for r in inputs['extra']],key=lambda r:r['group'])
    extra={}
    for row in inputs['extra']:extra[row['group']]=extra.get(row['group'],0)+row['amount']
    for row in report:row['amount']+=(1 if kind=='add' else -1)*extra.get(row['group'],0)
    return report


def samples(seed,count):
    rng=random.Random(seed);values=[]
    for _ in range(count):
        value={name:[{'group':rng.choice(['A','B','C']),'amount':rng.randint(-2,4)} for _ in range(rng.randrange(6))] for name in ('sales','returns','extra')}
        for name in ('sales','returns'):
            if value[name]:value[name].append(dict(value[name][0]))
        values.append(value)
    return values


def contract(kind):
    values=samples(95001,8)+[
        {'sales':[{'group':'A','amount':3}],'returns':[],'extra':[{'group':'A','amount':1},{'group':'A','amount':2}]},
        {'sales':[],'returns':[],'extra':[{'group':'Z','amount':2}]},
        {'sales':[{'group':'A','amount':0}],'returns':[],'extra':[]},
        {'sales':[{'group':'A','amount':2}],'returns':[{'group':'A','amount':-1}],'extra':[{'group':'A','amount':-2}]}
    ]
    goals={'add':'Add all signed adjustments grouped by account to the unique positive net report; retain net-report accounts only.',
           'subtract':'Subtract all signed reserves grouped by account from the unique positive net report; retain net-report accounts only.',
           'append':'Append every extra row to the unique positive net report, preserve extra duplicates, then sort by account.'}
    return {'inputs':['sales','returns','extra'],'key':'group','value':'amount','goal':goals[kind],
            'examples':[{'input':v,'output':expected(v,kind)} for v in values]}
