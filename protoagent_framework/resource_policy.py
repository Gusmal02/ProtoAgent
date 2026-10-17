"""Pure RAM state machine: decimal GB, sustained low-memory and hysteresis.

No process termination or permissions here. Host supervisor must pause at a
durable boundary and log downtime; emergency termination needs reconciliation.
"""
from dataclasses import dataclass
import math

@dataclass
class ResourcePolicy:
    start_bytes:int=2_500_000_000
    emergency_bytes:int=2_000_000_000
    low_seconds:float=15.0
    recovery_seconds:float=30.0
    state:str='waiting_resources'
    low_since:float|None=None
    recovered_since:float|None=None
    last_sample:float|None=None

    def sample(self,available,now):
        if type(available) not in (int,float) or not math.isfinite(available) or available<0:
            raise ValueError('invalid available RAM')
        if not math.isfinite(now) or (self.last_sample is not None and now<self.last_sample):
            raise ValueError('non-monotonic resource clock')
        self.last_sample=now
        if self.state=='emergency_stop': return self.state
        if available<self.emergency_bytes:
            self.state='emergency_stop'; return self.state
        if self.state=='waiting_resources':
            if available>=self.start_bytes: self.state='running'
            return self.state
        if self.state=='running':
            if available<self.start_bytes:
                if self.low_since is None: self.low_since=now
                if now-self.low_since>=self.low_seconds:
                    self.state='pause_requested'; self.recovered_since=None
            else:self.low_since=None
            return self.state
        # A worker acknowledgment is separate; recovery alone never cancels an
        # outstanding pause request while an effect may still be in flight.
        if self.state=='paused':
            if available>=self.start_bytes:
                if self.recovered_since is None:self.recovered_since=now
                if now-self.recovered_since>=self.recovery_seconds:
                    self.state='running'; self.low_since=None; self.recovered_since=None
            else:self.recovered_since=None
        return self.state

    def acknowledge_pause(self):
        if self.state!='pause_requested':raise ValueError('pause not requested')
        self.state='paused'; self.recovered_since=None
