# API contract for v0.1

All host callbacks and database paths are trusted application code. Neither a
model nor a tool response may obtain arbitrary Python, SQL, grants or handlers.

## Sessions and tools

`GovernedRuntime` is the compatibility in-process governance API: its proofs,
receipt cache and TTL are not a durable distributed ledger. Do not transfer
Session/NativeToolStore guarantees to it merely because both share the SDK.

`create_session(path,id,budget=...,goal=...,seed=...,nodes=...)` creates a new
session; use `Session.resume(path,id,expected_version=...)` for an existing one.
`start`, `step(provider)`, `run(provider,max_steps=...)`, `pause`, `cancel`,
`checkpoint`, `complete(provider)`, `close` are lifecycle operations. `complete`
requires current `provider.verify_goal(goal)` and no pending intent. A trace's
reward or `actual_terminal` alone never substitutes for that verifier.

Provider contract: entity, observe(), legal_actions(), context_vector(),
state_key(), describe(observation), request_binding(action), perform(id,action)
and verify_goal(goal). Bindings and returned observations must be JSON/numeric
compatible, bounded and stable for a pending operation. The provider commits
effect and receipt atomically and authorizes NEW effects using current policy.

`Observation(entity,revision,features,context=(0,0,0),state=None,description={})`
requires at least three finite feature values. `ToolDefinition(name,kind,payload,
handler=...,available=...,score=...,artifact=...,agenda=...,completion=...)`
registers exactly one native handler or control callback. A handler returns
`ToolResult(features,reward=0,terminal=False,evidence={})`; kind describes the
actual capability, not a text prompt. `RegisteredProvider` adapts this registry
to Session. `ToolRequest` binds tool,entity,revision,payload,schema.

The supported kind values are exactly `observe`, `probe`, `execute`, `challenge`,
`draft`, `compose`, `schedule`, `cancel`, `delegate`; `act` is not a valid kind.
Callbacks: `payload(view: Observation) -> dict`,
`available(view) -> (bool, reason_string)`, `score(view) -> finite_float`,
`handler(operation_id: str, request: ToolRequest) -> ToolResult`.
The alternative `control(request: ToolRequest) -> dict` is for the registered
team-control route, not a native handler. `NativeToolStore.execute` callbacks
are `mutate(db: sqlite3.Connection, request: ToolRequest) -> ToolResult` and
`authorize(db, request) -> bool`; only the literal True authorizes a NEW effect.
Callbacks are ordinary trusted Python callables, not strings loaded from JSON.

`checkpoint()` returns a detached diagnostic mapping with `session_id`,
`version`, `used`, `budget`, `checksum`, `pending` (operation id or None), and
`status` (`ready`, `running`, `paused`, `cancelled`, `completed`, `exhausted`).
Read `used`/`budget` there rather than querying private Session tables.
`run()` returns `{'checkpoint': ..., 'results': [step_traces...]}`.
`Session.resume` starts a nonterminal existing session; it does not reset used
credits. A completed/cancelled/exhausted session cannot be resumed for new work.

Optional completion(view) callback returns None or exactly:
`entity,revision,goal_scope,artifact_hash,evidence_hashes`. Hashes are lowercase
SHA256; evidence list is nonempty. Available offers are bound to the native
request hash, frozen in Session, and supplied to the explicit completion policy.
No proof is fabricated from a string saying “accepted”. The native handler must
revalidate authority/approval immediately before committing. Existing pending
views lacking offers replay with an empty offer set. Abstain is not removed.

`NativeToolStore.execute(id,request,mutate=...,authorize=...)` provides local
SQLite atomic effect+receipt. Same id+binding returns receipt; collision/fence
fails. Historical receipt retrieval is not a new authorization. Domain adapters
can impose stricter replay authorization, as reducer_store does. Host-only
`read` is SELECT diagnostic SQL, never expose that method to an untrusted actor.

## Memory, tools and teams

`MemoryStore.put(body,entity=...,revision=...,purpose=...)` returns a
MemoryReference. `resolve(ref,entity=...,revision=...)` validates context and
integrity, not permission to use the referenced capability. `ReferencedProvider`
stores descriptions outside Session and returns diagnostic references.

`VerifiedToolMemory` is imported from `protoagent_framework.verified_tool_memory`.
Host verifies a module set containing runner.py, calls register_from_host with
family/contract/author/receipt/proof, recovers candidates, materializes in an
owned folder and revalidate_from_host for current context. `eligible` is a
library recommendation, **not** a TeamCoordinator artifact admission. Signature
in this wrapper is constant: recovery is contextual filtering, not a proven
semantic retrieval advantage. Distinct evidence is needed for reinforcement;
relabeling the same measurement does not create new support. No code is run
automatically when materializing.

TeamCoordinator registers members and issues current scoped grants from host.
RoleSession gives each actor a real motor/session, not shared hidden credentials.
`Collaboration(team,path,reviewers=(...))` supports command(token,entity,id,
action,task_id,payload) and separate inspect(token,entity,task_id). Request needs
goal,owner,acceptance,dependencies; owner accepts/submits artifact+evidence hashes;
independent reviewer passes/fails exact artifact. ACK != acceptance != approval.
Changing content invalidates its review. Permissions must be rechecked after
revocation, revision changes and restore. See examples/collaboration_data_ops.py.

## Error handling

ValueError/ReferenceError: malformed schema, collision, stale context or bound.
PermissionError/TeamError: current authority or protocol precondition denies.
SessionError: terminal/stale/corrupt session or unresolved pending state.
WorkspaceError: clone/export/integrity/lease problem. WorkBudgetExceeded and
StorageBudgetExceeded: stop admitting NEW work, retain evidence and reconcile.
Provider-specific uncertain outcomes are not ordinary retries. Do not catch all
exceptions and continue as success; persist diagnostic context without secrets.

Base modules use stdlib; Engine, numeric library and Session motor operations
need `[motor]`. No server runs on importing any of these APIs. Tools/LLM network
transports and generators are explicitly opt-in, not background daemons.
