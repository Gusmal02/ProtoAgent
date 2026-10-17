"""Lazy public facade for the actual packaged ProtoAgentV3 motor."""
from dataclasses import asdict
import threading

_RNG_LOCK=threading.RLock()

def numeric_encoder(observation):
    import torch
    return torch.as_tensor(observation[:3],dtype=torch.float32)

class Engine:
    def __init__(self, *, seed=881, nodes=12, config=None):
        import torch
        from .motor.core.agent_proto_v3 import ProtoAgentV3, ProtoAgentV3Config
        from .motor.core.field import ResonantField
        if not 4<=nodes<=256: raise ValueError('nodes outside resource budget')
        # Use local initialization RNG without perturbing other sessions.
        with torch.random.fork_rng():
            torch.manual_seed(seed)
            edges=torch.tensor([(i,(i+1)%nodes) for i in range(nodes)]+
                               [((i+1)%nodes,i) for i in range(nodes)]).t()
            field=ResonantField(nodes,edges,omega_std=.05)
        options=dict(use_sandbox=False,enable_contextual_memory=True,
                     enable_subconscious=True,enable_curiosity=True,
                     enable_action_context_memory=True,enable_action_context_arbitration=True)
        options.update(config or {})
        if options.get('use_sandbox'): raise ValueError('durable session cannot replay speculative real effects')
        import numpy as np
        with _RNG_LOCK, torch.random.fork_rng():
            previous=np.random.get_state()
            try:
                self.agent=ProtoAgentV3(field,numeric_encoder,ProtoAgentV3Config(**options))
                self.rng=torch.get_rng_state(); self.numpy_rng=np.random.get_state()
            finally: np.random.set_state(previous)
        self.steps=0
    def step(self, environment):
        import torch
        import numpy as np
        with _RNG_LOCK, torch.random.fork_rng():
            previous=np.random.get_state()
            torch.set_rng_state(self.rng); np.random.set_state(self.numpy_rng)
            try:
                result=self.agent.step(environment,self.steps)
                self.rng=torch.get_rng_state(); self.numpy_rng=np.random.get_state()
            finally: np.random.set_state(previous)
        self.steps+=1
        self.agent.trace.clear()
        return result
    def snapshot(self):
        from .state_codec import dumps
        # Local motor gate is not host authority and is never restored.
        state={k:v for k,v in self.agent.__dict__.items() if k not in ('encoder','execution_gate','trace')}
        return dumps({'schema':1,'steps':self.steps,'agent':state,
                      'rng':self.rng,'numpy_rng':self.numpy_rng})
    @classmethod
    def restore(cls, raw):
        from .state_codec import loads
        from .motor.core.protoagent_v3_governance import ExecutionGate
        data=loads(raw)
        if data['schema']!=1 or type(data['steps']) is not int or data['steps']<0:
            raise ValueError('invalid motor checkpoint')
        from .motor.core.agent_proto_v3 import ProtoAgentV3
        engine=cls.__new__(cls)
        engine.agent=ProtoAgentV3.__new__(ProtoAgentV3)
        engine.agent.__dict__.update(data['agent'])
        engine.agent.encoder=numeric_encoder; engine.agent.trace=[]
        engine.agent.execution_gate=ExecutionGate(mode=engine.agent.cfg.operating_mode)
        engine.steps=data['steps']
        engine.rng=data['rng']; engine.numpy_rng=data['numpy_rng']
        return engine
