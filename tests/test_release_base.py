import json,sqlite3,tempfile,unittest
from pathlib import Path
from protoagent_framework import MemoryStore,MemoryReference,ReferenceError,RuntimeWorkspace,WorkspaceError,NativeToolStore,ToolRequest,ToolResult
from protoagent_framework.reducer_store import HostAuthority,ReducerStore
from protoagent_framework.runtime_config import RuntimeConfig,StorageBudgetExceeded
from protoagent_framework.work_budget import WorkBudget,WorkBudgetExceeded
from protoagent_framework.checkpoint_storage import pack,unpack

class BaseChecks(unittest.TestCase):
    def test_limits_preserve_files_and_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'journal';p.write_bytes(b'0'*100)
            with self.assertRaises(StorageBudgetExceeded):RuntimeConfig(max_workspace_bytes=150,reserve_bytes=60).check_workspace_from_host(root)
            self.assertEqual(p.read_bytes(),b'0'*100)
            budget=WorkBudget(root/'budget.sqlite',limit=2);budget.reserve(2);budget.close()
            budget=WorkBudget(root/'budget.sqlite',limit=2)
            try:
                with self.assertRaises(WorkBudgetExceeded):budget.reserve()
                self.assertEqual(budget.status()['used'],2)
            finally:budget.close()
    def test_reference_context_integrity_and_restore(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);live=root/'live';live.mkdir();memory=MemoryStore(live/'memory.sqlite')
            try:
                ref=memory.put({'x':1},entity='A',revision=0)
                with self.assertRaises(ReferenceError):memory.resolve(ref,entity='B',revision=0)
                workspace=RuntimeWorkspace(live);workspace.register_sqlite('memory',live/'memory.sqlite');workspace.export_bundle(root/'bundle')
                clone=RuntimeWorkspace.restore_clone(root/'bundle',root/'clone');copied=MemoryStore(clone.root/'memory.sqlite')
                try:self.assertEqual(copied.resolve(ref,entity='A',revision=0),{'x':1})
                finally:copied.close()
                with self.assertRaises(WorkspaceError):RuntimeWorkspace.restore_clone(root/'bundle',live)
                (root/'bundle'/'memory.sqlite').write_bytes(b'corrupt')
                with self.assertRaises(WorkspaceError):RuntimeWorkspace.restore_clone(root/'bundle',root/'corrupt-clone')
            finally:memory.close()
    def test_backup_revokes_reducer_grants_not_live(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);live=root/'live';live.mkdir();path=live/'state.sqlite'
            host=HostAuthority(str(path));token=host.grant('operator','A');host.initialize('A','x',10)
            workspace=RuntimeWorkspace(live);workspace.register_sqlite('state',path);workspace.export_bundle(root/'bundle')
            clone=RuntimeWorkspace.restore_clone(root/'bundle',root/'clone')
            with self.assertRaises(PermissionError):ReducerStore(str(clone.root/'state.sqlite')).report(token,'A')
            self.assertEqual(ReducerStore(str(path)).report(token,'A'),{'x':10})
    def test_native_replay_binding_and_fence(self):
        with tempfile.TemporaryDirectory() as d:
            store=NativeToolStore(Path(d)/'n',initialize=lambda db:db.execute('CREATE TABLE counts(n)'))
            request=ToolRequest('write','A',0,{})
            def effect(db,r):db.execute('INSERT INTO counts VALUES(1)');return ToolResult((1,0,0))
            try:
                for _ in range(2):store.execute('one',request,mutate=effect,authorize=lambda d,r:True)
                self.assertEqual(store.read('SELECT count(*) FROM counts'),[(1,)])
                with self.assertRaises(ValueError):store.execute('one',ToolRequest('write','B',0,{}),mutate=effect,authorize=lambda d,r:True)
                store.fence('late','A')
                with self.assertRaises(ValueError):store.execute('late',request,mutate=effect,authorize=lambda d,r:True)
            finally:store.close()
    def test_checkpoint_corruption_legacy_and_compression(self):
        raw=b'{"history":'+b'"'+b'x'*10000+b'"}'
        self.assertEqual(unpack(pack(raw)),raw);self.assertEqual(unpack(b'{"schema":1}'),b'{"schema":1}')
        with self.assertRaises(Exception):unpack(pack(raw)+b'extra')
    def test_reducer_input_replay_and_revocation(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'n');host=HostAuthority(path);t=host.grant('actor','A');host.initialize('A','k',3);store=ReducerStore(path)
            reduce=lambda x,op,y:x-y
            self.assertEqual(store.apply(reduce,t,'A','one','k','sale',2),1)
            self.assertEqual(store.apply(reduce,t,'A','one','k','sale',2),1)
            with self.assertRaises(ValueError):store.apply(reduce,t,'A','two','k','sale',2)
            with self.assertRaises(ValueError):store.apply(reduce,t,'A','one','k','sale',1)
            host.revoke(t)
            with self.assertRaises(PermissionError):store.apply(reduce,t,'A','one','k','sale',2)

if __name__=='__main__':unittest.main()
