"""Cooperatively locked multi-SQLite snapshots; clone-only restore.

All mutating participants must use this workspace lease. External HTTP effects
and uncooperative writers are not covered. Restores never overwrite live state.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

class WorkspaceError(RuntimeError):pass

def _name(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):raise WorkspaceError('invalid resource name')
    return name

def _write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:
        json.dump(value,stream,sort_keys=True,indent=2);stream.flush();os.fsync(stream.fileno())

class RuntimeWorkspace:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock();self._depth=0
        manifest=self.root/'resources.json'
        self.resources=json.loads(manifest.read_text()) if manifest.exists() else {}
    def register_sqlite(self,name,path):
        _name(name);path=Path(path).resolve()
        try:relative=path.relative_to(self.root)
        except ValueError:raise WorkspaceError('resource must be inside workspace')
        if len(relative.parts)!=1 or not path.is_file():raise WorkspaceError('register an existing top-level SQLite file')
        with self.lease():
            manifest=self.root/'resources.json'
            self.resources=json.loads(manifest.read_text()) if manifest.exists() else {}
            if name in self.resources and self.resources[name]!=relative.name:raise WorkspaceError('resource mapping changed')
            self.resources[name]=relative.name
            temporary=self.root/('resources-'+str(time.time_ns())+'.next')
            _write(temporary,self.resources);temporary.replace(manifest)
    @contextmanager
    def lease(self,timeout=10):
        with self._lock:
            if self._depth:
                self._depth+=1
                try:yield self
                finally:self._depth-=1
                return
            path=self.root/'.workspace.lock';stream=path.open('a+b')
            if path.stat().st_size==0:stream.write(b'0');stream.flush()
            began=time.monotonic()
            while True:
                try:
                    stream.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic()-began>=timeout:stream.close();raise WorkspaceError('workspace busy')
                    time.sleep(.02)
            self._depth=1
            try:yield self
            finally:
                self._depth=0;stream.seek(0)
                if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
                stream.close()
    def step(self,actor,provider):
        with self.lease():return actor.step(provider)
    def export_bundle(self,destination):
        destination=Path(destination).resolve()
        if destination.exists():raise WorkspaceError('bundle destination must not exist')
        destination.mkdir(parents=True)
        manifest={'schema':1,'resources':{},'authority_restored':False,'scope':'cooperatively locked SQLite snapshot; clone only'}
        try:
            with self.lease():
                registry=self.root/'resources.json'
                self.resources=json.loads(registry.read_text()) if registry.exists() else {}
                for name,relative in self.resources.items():
                    source=self.root/relative;copy=destination/(name+'.sqlite')
                    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(copy)
                    try:
                        src.backup(dst)
                        tables={r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        if 'grants' in tables:
                            columns={r[1] for r in dst.execute('PRAGMA table_info(grants)')}
                            if {'hash','team','actor','revoked'}<=columns:dst.execute('UPDATE grants SET revoked=1')
                            elif {'token','actor','tenant','enabled'}<=columns:dst.execute('UPDATE grants SET enabled=0')
                            else:raise WorkspaceError('unknown grants schema; no authority-preserving export')
                        if 'grant_delivery' in tables:dst.execute('DELETE FROM grant_delivery')
                        if 'artifacts' in tables:dst.execute("UPDATE artifacts SET status='candidate',verification=NULL WHERE status='active'")
                        # Generation authority is a separate permission ledger.
                        # Preserve responses/proofs and consumed budget, not the
                        # permission to dispatch/admit after restoring a clone.
                        if 'authority' in tables and {'actor','entity','revision','enabled'}<={r[1] for r in dst.execute('PRAGMA table_info(authority)')}:
                            dst.execute('UPDATE authority SET enabled=0')
                            if 'intents' in tables:dst.execute("UPDATE intents SET state='verified' WHERE state='admitted'")
                            if 'admissions' in tables:dst.execute('DELETE FROM admissions')
                        dst.commit()
                        if dst.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise WorkspaceError('snapshot SQLite corrupt')
                    finally:src.close();dst.close()
                    with copy.open('r+b') as handle:os.fsync(handle.fileno())
                    manifest['resources'][name]={'file':copy.name,'original_file':relative,'sha256':hashlib.sha256(copy.read_bytes()).hexdigest()}
                _write(destination/'manifest.json',manifest)
            return manifest
        except BaseException:
            # Keep incomplete evidence, never present it as an accepted backup.
            _write(destination/'incomplete.json',{'accepted':False});raise
    @classmethod
    def restore_clone(cls,bundle,destination):
        bundle=Path(bundle).resolve();destination=Path(destination).resolve()
        if destination.exists():raise WorkspaceError('cannot overwrite a live workspace')
        manifest=json.loads((bundle/'manifest.json').read_text())
        if manifest.get('schema')!=1 or manifest.get('authority_restored') is not False:raise WorkspaceError('bundle schema/authority')
        validated=[]
        originals=set()
        for name,meta in manifest['resources'].items():
            _name(name)
            if Path(meta['file']).name!=meta['file'] or Path(meta['original_file']).name!=meta['original_file']:raise WorkspaceError('bundle path traversal')
            for filename in (meta['file'],meta['original_file']):
                if filename in ('.','..') or any(c in filename for c in '/\\:'):raise WorkspaceError('bundle path traversal')
            if meta['original_file'] in originals:raise WorkspaceError('duplicate destination')
            originals.add(meta['original_file'])
            path=(bundle/meta['file']).resolve()
            if path.parent!=bundle or hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise WorkspaceError('bundle integrity failure')
            validated.append((name,meta,path))
        destination.mkdir(parents=True)
        mappings={}
        for name,meta,path in validated:
            target=destination/meta['original_file']
            with target.open('xb') as handle:handle.write(path.read_bytes());handle.flush();os.fsync(handle.fileno())
            mappings[name]=target.name
        _write(destination/'resources.json',mappings)
        _write(destination/'restore.json',{'authority_restored':False,'new_host_grants_required':True,'artifact_reverification_required':True,'source_manifest_sha256':hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()})
        return cls(destination)
