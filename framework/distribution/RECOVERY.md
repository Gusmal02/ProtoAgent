# Recovery and operations

> Nota histórica en inglés. Para el recorrido en español, consulta
> [uso y recuperación](../../docs/USO.md#10-pausar-continuar-y-terminar-no-son-lo-mismo)
> y [arquitectura técnica](../../Technical.md#2-persistencia-y-fronteras-de-confianza).

1. Pause new work at a durable boundary. Retain every journal/resource database,
   pending identity, original request, evidence, version and consumed budget.
2. Use `pending_operation_view_from_host()` and
   `operation_receipts_from_host()` for diagnosis. These APIs return data, not
   authority. Never change a pending binding to retry a different operation.
3. For cooperating local providers, reopen with the SAME version/contract and
   resume Session. The original intent reaches the native receipt ledger; a
   committed effect must replay its receipt, not execute again.
4. An unknown external effect stays uncertain. Use reliable native status or
   explicit host reconciliation. Missing receipt does not prove no effect;
   no blind resend and no budget refund.
5. Cancel/abandon pending only after a native fence proves late effects cannot
   occur. Applied/unknown cannot be declared abandoned. Never kill unrelated
   applications; the host owns and identifies its worker processes.

`RuntimeWorkspace` must register ALL relevant SQLite participants; every writer
uses its lease. export_bundle creates a clone-only backup with hashes and strips
known grants/admissions. Unknown grant schemas fail closed. restore_clone rejects
live overwrite/traversal/corruption. Do not upload or restore untrusted bundles.
Restore never grants authority: issue fresh host grants and reverify artifacts.

Checkpoint wire schema1 and compressed/legacy JSON forms remain supported under
their limits; unsupported schema/types reject. Existing Session views without
completion offers use none. ProgrammingRuntime legacy pending attempts with no
actor/request binding are deliberately blocked for explicit reconciliation,
not guessed or resumed under fresh authority. Do not migrate a live frozen
campaign by replacing its wheel; back up first and test a separate clone.

Default RuntimeConfig is 100 steps,512MiB workspace and16MiB reserved for closing.
Check workspace before new admissions. This is a cooperative boundary watchdog,
not filesystem enforcement; a step can still grow data or exhaust disk. Monitor
free disk and checkpoint growth externally. No silent truncation/GC. Decide
retention explicitly before continuous service; immutable evidence is not
created merely by hashing a writable SQLite database.

Use try/finally close on Session, MemoryStore, TeamCoordinator, Collaboration,
NativeToolStore and VerifiedToolMemory. ProgrammingRuntime is also a context
manager and closes partial session construction on failure. None of these
objects owns or stops Claude/ChatGPT/MCP/other application processes. If your
integration starts workers, use timeouts and owned process handles/jobs, then
wait/reap them; do not kill a PID without checking identity/creation.

Small local regression metrics are not availability guarantees. The8h soak,
disk/retention SLO and production operations are separate, not started here.
