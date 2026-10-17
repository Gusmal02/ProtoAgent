"""Explicit local-workspace limits. No implicit deletion or process killing."""
from dataclasses import dataclass,asdict
from pathlib import Path

class StorageBudgetExceeded(RuntimeError):pass

@dataclass(frozen=True)
class RuntimeConfig:
    session_steps:int=100
    max_workspace_bytes:int=512*1024*1024
    reserve_bytes:int=16*1024*1024
    max_entries:int=10000
    def __post_init__(self):
        if type(self.session_steps) is not int or not 1<=self.session_steps<=100000:raise ValueError('session step budget')
        if any(type(v) is not int or v<=0 for v in (self.max_workspace_bytes,self.reserve_bytes)) or self.reserve_bytes>=self.max_workspace_bytes:raise ValueError('storage budget')
        if type(self.max_entries) is not int or not 1<=self.max_entries<=100000:raise ValueError('workspace entry budget')
    def to_dict(self):return asdict(self)
    def check_workspace_from_host(self,root):
        """Check before admitting NEW work; reserve is for durable pause/close.

        This is a boundary watchdog, not an atomic filesystem quota. All writers
        must cooperate; it cannot bound files written outside this workspace.
        Symlinks are rejected rather than following them outside the root.
        """
        root=Path(root).resolve();used=0;entries=0
        if not root.is_dir():raise ValueError('workspace directory required')
        pending=[root]
        while pending:
            directory=pending.pop()
            for path in directory.iterdir():
                entries+=1
                if entries>self.max_entries:raise StorageBudgetExceeded('workspace entry budget exhausted; retain evidence')
                if path.is_symlink() or path.is_junction():raise ValueError('workspace symlink/junction not supported')
                if path.is_dir():pending.append(path)
                elif path.is_file():used+=path.stat().st_size
                if used+self.reserve_bytes>=self.max_workspace_bytes:raise StorageBudgetExceeded('pause new work; retain journals and reconcile before resume')
        return {'used_bytes':used,'remaining_bytes':self.max_workspace_bytes-used,'reserve_bytes':self.reserve_bytes,'automatic_deletion':False}
