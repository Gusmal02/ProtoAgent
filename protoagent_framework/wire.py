"""Strict versioned JSON. Deserialized evidence is never enrolled as trusted."""
import json
from dataclasses import asdict
from .api import ContractError, API_VERSION
from .contracts import QuerySpec, ActionSpec

def dumps(request):
    if type(request) not in (QuerySpec,ActionSpec): raise ContractError('unsupported wire type')
    return json.dumps({'schema_version':API_VERSION,'kind':type(request).__name__,'request':asdict(request)},
                      sort_keys=True,allow_nan=False)

def loads(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ContractError('duplicate JSON key')
            result[key]=value
        return result
    if not isinstance(raw,str) or len(raw)>65536: raise ContractError('wire budget exceeded')
    try: envelope=json.loads(raw,object_pairs_hook=unique)
    except (ValueError,TypeError) as error: raise ContractError('invalid JSON') from error
    if (type(envelope) is not dict or set(envelope)!= {'schema_version','kind','request'} or
        envelope['schema_version']!=API_VERSION): raise ContractError('incompatible schema')
    if type(envelope['kind']) is not str: raise ContractError('invalid request kind')
    cls={'QuerySpec':QuerySpec,'ActionSpec':ActionSpec}.get(envelope['kind'])
    value=envelope['request']
    if cls is None or type(value) is not dict: raise ContractError('unsupported proposal')
    common={'connector','operation','entity'}
    fields=common|({'parameters'} if cls is QuerySpec else {'evidence_ids','reversible'})
    if set(value)!=fields: raise ContractError('unknown or missing fields')
    if any(type(value[k]) is not str or not 1<=len(value[k])<=256 for k in common):
        raise ContractError('invalid identifier')
    if cls is QuerySpec:
        params=value['parameters']
        if (type(params) is not list or len(params)>32 or any(type(p) is not list or len(p)!=2 or
            any(type(x) is not str or len(x)>256 for x in p) for p in params) or
            len({p[0] for p in params})!=len(params)): raise ContractError('invalid parameters')
        value['parameters']=tuple(tuple(p) for p in params)
    else:
        ids=value['evidence_ids']
        if (type(value['reversible']) is not bool or type(ids) is not list or len(ids)>32 or
            any(type(i) is not str or not 1<=len(i)<=256 for i in ids) or len(ids)!=len(set(ids))):
            raise ContractError('invalid action fields')
        value['evidence_ids']=tuple(ids)
    return cls(**value)
