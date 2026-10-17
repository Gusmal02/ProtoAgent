"""Typed public tool/provider bridge. Handlers are trusted host code, not plugins."""
from dataclasses import dataclass,field,asdict
import hashlib
import json
import math
from .memory_store import canonical

@dataclass(frozen=True)
class Observation:
    entity:str
    revision:int
    features:tuple
    context:tuple=(0.,0.,0.)
    state:object=None
    description:dict=field(default_factory=dict)
    def __post_init__(self):
        object.__setattr__(self,'features',tuple(self.features));object.__setattr__(self,'context',tuple(self.context))
        if not self.entity or type(self.revision) is not int or self.revision<0:raise ValueError('observation context')
        if len(self.features)<3 or len(self.context)!=3 or not all(math.isfinite(float(x)) for x in self.features+self.context):raise ValueError('numeric observation requires finite features>=3/context3')
        canonical(self.description);canonical(self.state)

@dataclass(frozen=True)
class ToolRequest:
    tool:str
    entity:str
    revision:int
    payload:dict
    schema:int=1
    def to_dict(self):return asdict(self)

@dataclass(frozen=True)
class ResourceRequest:
    resource:str
    reason:str
    def to_dict(self):return asdict(self)

@dataclass(frozen=True)
class ToolResult:
    features:tuple
    reward:float=0.
    terminal:bool=False
    evidence:dict=field(default_factory=dict)
    resource_request:ResourceRequest|None=None
    def __post_init__(self):
        object.__setattr__(self,'features',tuple(self.features))
        if len(self.features)<3 or not all(math.isfinite(float(x)) for x in self.features) or not math.isfinite(float(self.reward)):raise ValueError('nonfinite tool result')
        if type(self.terminal) is not bool:raise ValueError('terminal must be boolean')
        canonical(self.evidence)
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,value):
        value=dict(value);value['features']=tuple(value['features'])
        if value.get('resource_request'):value['resource_request']=ResourceRequest(**value['resource_request'])
        return cls(**value)

@dataclass(frozen=True)
class ToolDefinition:
    name:str
    kind:str
    payload:object
    handler:object=None
    available:object=lambda view:(True,'available')
    score:object=lambda view:0.
    control:object=None
    schema:int=1
    artifact:object=None
    agenda:object=None
    completion:object=None
    def __post_init__(self):
        if not self.name or self.kind not in ('observe','probe','execute','challenge','draft','compose','schedule','cancel','delegate'):raise ValueError('tool definition')
        if (self.handler is None)==(self.control is None):raise ValueError('declare exactly one native handler or control callback')
        if not all(callable(x) for x in (self.payload,self.available,self.score,self.handler or self.control)):raise ValueError('tool callbacks must be callable')
        if any(x is not None and not callable(x) for x in (self.artifact,self.agenda)):raise ValueError('artifact/agenda bindings must be callbacks')
        if self.completion is not None and not callable(self.completion):raise ValueError('completion must be a trusted callback')

class ToolRegistry:
    def __init__(self,definitions):
        self.tools={}
        for spec in definitions:
            identity=int(hashlib.sha256(spec.name.encode()).hexdigest()[:7],16)
            if identity in self.tools or any(s.name==spec.name for s in self.tools.values()):raise ValueError('tool identity collision')
            self.tools[identity]=spec
        if not self.tools:raise ValueError('empty tool registry')
    def manifest(self):return {str(i):{'name':s.name,'kind':s.kind,'schema':s.schema} for i,s in self.tools.items()}
    def identifier(self,name):return next(i for i,s in self.tools.items() if s.name==name)

class RegisteredProvider:
    def __init__(self,registry,observe,verify_goal,*,session=None):
        self.registry=registry;self.observer=observe;self.goal_verifier=verify_goal;self._frozen={}
        if session:
            pending=session.pending_operation_view_from_host()
            if pending:self._frozen=pending['view']['bindings']
        self.view=self.observer();self.entity=self.view.entity
    def legal_actions(self):return list(self.registry.tools)
    def action_kind(self,action):return self.registry.tools[action].kind
    def request_binding(self,action):
        if str(action) in self._frozen:
            value=self._frozen[str(action)];return value.get('native_request',value)
        spec=self.registry.tools[action];payload=spec.payload(self.view);canonical(payload)
        return ToolRequest(spec.name,self.entity,self.view.revision,payload,spec.schema).to_dict()
    def control_request(self,action):
        if str(action) in self._frozen:return self._frozen[str(action)].get('control_request')
        spec=self.registry.tools[action]
        if not spec.control:return None
        available,_=spec.available(self.view)
        return spec.control(ToolRequest(**self.request_binding(action))) if available else None
    def observe(self):
        import numpy as np
        return np.array(self.view.features,dtype=np.float32)
    def context_vector(self):return list(self.view.context)
    def state_key(self):return (self.entity,self.view.revision,hashlib.sha256(canonical(self.view.state).encode()).hexdigest())
    def describe(self,observation):
        return {'entity':self.entity,'revision':self.view.revision,'description':self.view.description,'tools':self.registry.manifest(),
            'availability':{str(i):s.available(self.view) for i,s in self.registry.tools.items()}}
    def deterministic_score(self,a):
        spec=self.registry.tools[a];available,_=spec.available(self.view)
        return float(spec.score(self.view)) if available else -.25
    def verified_completions(self):
        """Host-supplied goal proofs are decision inputs, never execution grants.

        Callbacks are trusted provider code, not fields parsed from a model.
        Current authorization must still be checked atomically by the handler.
        """
        offers=[]
        for action,spec in self.registry.tools.items():
            if spec.completion is None or not spec.available(self.view)[0]:continue
            proof=spec.completion(self.view)
            if proof is None:continue
            if type(proof) is not dict or set(proof)!={'entity','revision','goal_scope','artifact_hash','evidence_hashes'}:raise ValueError('completion proof schema')
            if proof['entity']!=self.entity or proof['revision']!=self.view.revision:raise ValueError('completion proof context')
            hashes=[proof['artifact_hash']]+proof['evidence_hashes'] if type(proof['evidence_hashes']) is list else []
            if len(hashes)<2 or any(type(h) is not str or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in hashes):raise ValueError('completion proof hashes')
            if type(proof['goal_scope']) is not str or not proof['goal_scope']:raise ValueError('completion goal scope')
            offers.append({'action':action,'request_hash':hashlib.sha256(canonical(self.request_binding(action)).encode()).hexdigest(),**proof})
        return offers
    def is_information_action(self,a):return self.action_kind(a) in ('observe','probe','challenge')
    def _requirement(self,a,name):
        if str(a) in self._frozen:return self._frozen[str(a)].get(name)
        callback=getattr(self.registry.tools[a],name)
        return callback(self.view) if callback else None
    def required_artifact(self,a):return self._requirement(a,'artifact')
    def required_agenda(self,a):return self._requirement(a,'agenda')
    def control_outcome(self,a,result):
        self.view=self.observer();self._frozen={}
        return self.observe(),-.25 if result.get('rejected') else 0.,False,{'entity':self.entity,'at_goal':False,'control_committed':result}
    def perform(self,operation,a):
        spec=self.registry.tools[a];available,reason=spec.available(self.observer())
        # A pending intent may already have committed. Its original binding must
        # reach the native receipt store, not become a fictitious rejection due
        # to the post-effect state. Native authorization still controls any NEW
        # effect; frozen memory never grants permission.
        if not available and str(a) not in self._frozen:
            return self.observe(),-.25,False,{'entity':self.entity,'at_goal':False,'action_rejected':True,'reason':reason}
        if spec.handler is None:raise ValueError('control tool reached native route')
        result=spec.handler(operation,ToolRequest(**self.request_binding(a)))
        if not isinstance(result,ToolResult):raise TypeError('handler must return ToolResult')
        self.view=self.observer();self._frozen={}
        import numpy as np
        evidence=dict(result.evidence);evidence['entity']=self.entity
        if result.resource_request:evidence.update(abstained=True,at_goal=False,resource_request=result.resource_request.to_dict())
        return np.array(result.features,dtype=np.float32),float(result.reward),bool(result.terminal),evidence
    def verify_goal(self,goal):return self.goal_verifier(goal) is True
