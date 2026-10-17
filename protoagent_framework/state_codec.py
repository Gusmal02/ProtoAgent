"""Data-only motor checkpoints. No pickle, eval, arbitrary modules or callables.

Checkpoint files belong to the trusted host, not to agents/plugins. Hashes detect
accidental corruption; they do not authorize untrusted checkpoint uploads.
"""
import importlib
import json
from functools import lru_cache
from importlib.resources import files

MAX_BYTES=16*1024*1024

@lru_cache(maxsize=1)
def _modules():
    manifest=json.loads(files('protoagent_framework.motor').joinpath('sources.json').read_text())
    return {'protoagent_framework.motor.'+name for name in manifest}

@lru_cache(maxsize=1)
def _runtime():
    import numpy as np
    import torch
    allowed={name:getattr(torch,name) for name in ('float32','float64','int64','int32','uint8','bool')}
    return np,torch,allowed

def encode(value):
    return _encode(value,*_runtime()[:2])

def _encode(value,np,torch):
    if value is None or type(value) in (bool,int,float,str): return value
    # Histories contain many small plain dict/list/tuple records. Keep exactly
    # the old tagged wire representation, but don't dispatch scalar keys/items
    # through tensor/array/module checks for every historical record.
    if isinstance(value,dict):
        return {'$':'dict','items':[[k if k is None or type(k) in (bool,int,float,str) else _encode(k,np,torch),
            v if v is None or type(v) in (bool,int,float,str) else _encode(v,np,torch)] for k,v in value.items()]}
    if isinstance(value,(list,tuple,set,frozenset)):
        return {'$':type(value).__name__,'items':[x if x is None or type(x) in (bool,int,float,str)
            else _encode(x,np,torch) for x in value]}
    if isinstance(value,np.generic): return _encode(value.item(),np,torch)
    if isinstance(value,torch.Tensor):
        return {'$':'tensor','dtype':str(value.dtype).split('.')[-1],
                'data':value.detach().cpu().tolist()}
    if isinstance(value,np.ndarray):
        if value.dtype.kind not in 'biuf': raise ValueError('non-numeric array')
        return {'$':'array','dtype':str(value.dtype),'data':value.tolist()}
    cls=type(value)
    if cls.__module__ not in _modules() or not hasattr(value,'__dict__'):
        raise ValueError('checkpoint contains unsupported type '+cls.__module__+'.'+cls.__name__)
    return {'$':'object','module':cls.__module__,'name':cls.__name__,'state':_encode(value.__dict__,np,torch)}

def decode(value):
    return _decode(value,*_runtime())

def _decode(value,np,torch,allowed):
    if not isinstance(value,dict): return value
    tag=value.get('$')
    if tag=='tensor':
        return torch.tensor(value['data'],dtype=allowed[value['dtype']])
    if tag=='array':
        dtype=np.dtype(value['dtype'])
        if dtype.kind not in 'biuf': raise ValueError('non-numeric array')
        return np.array(value['data'],dtype=dtype)
    if tag in ('list','tuple','set','frozenset'):
        return {'list':list,'tuple':tuple,'set':set,'frozenset':frozenset}[tag](_decode(x,np,torch,allowed) for x in value['items'])
    if tag=='dict': return {k if not isinstance(k,dict) else _decode(k,np,torch,allowed):
        v if not isinstance(v,dict) else _decode(v,np,torch,allowed) for k,v in value['items']}
    if tag=='object':
        if value['module'] not in _modules() or value['name'].startswith('_'):
            raise ValueError('checkpoint class not allowed')
        cls=getattr(importlib.import_module(value['module']),value['name'])
        if not isinstance(cls,type) or cls.__module__!=value['module']:
            raise ValueError('checkpoint class origin mismatch')
        obj=cls.__new__(cls); obj.__dict__.update(_decode(value['state'],np,torch,allowed)); return obj
    raise ValueError('unknown checkpoint tag')

def dumps(value):
    raw=json.dumps(encode(value),allow_nan=False,separators=(',',':')).encode()
    if len(raw)>MAX_BYTES: raise ValueError('checkpoint size budget exceeded')
    return raw

def loads(raw):
    if len(raw)>MAX_BYTES: raise ValueError('checkpoint size budget exceeded')
    return decode(json.loads(raw))
