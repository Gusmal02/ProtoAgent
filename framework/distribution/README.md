# ProtoAgent Framework — 0.1 experimental release candidate

Local Python framework for motor-driven decisions, durable sessions, verified
tools, referenced memory and role collaboration. **No LLM required.**

Apache-2.0. Candidate `0.1.0rc3`; not a production service, arbitrary-code sandbox
or promise of general programming/intelligence. Release verdict and platform
qualification are separate from this guide. Historical dev results are not a
certificate for this wheel.

## Install

Supported release target: CPython3.12. Windows x64 is locally qualified only
when the release report says PASS; Linux3.12 is a CI target, not a claimed local
result. Other Python/OS combinations remain unqualified.

```console
python -m venv .venv
# Windows: .venv\Scripts\python ; Linux: .venv/bin/python
python -m pip install /path/to/protoagent_framework-0.1.0rc3-py3-none-any.whl
# Only if a motor/biblioteca example is needed:
python -m pip install "/path/to/protoagent_framework-0.1.0rc3-py3-none-any.whl[motor]"
```

Use the venv's Python for every command. Base SDK uses stdlib and does not load
Torch/NumPy merely by importing it. `[motor]` adds NumPy,Torch,NetworkX. Normal
installation may download dependencies; offline installation requires those
exact wheels in a local cache/wheelhouse. No API key is needed.

Run `python examples/local_counter.py --workspace <new-folder>` and
`python examples/referenced_data.py --workspace <another-new-folder>`
from the supplied source/example bundle, outside the research checkout. Do not
modify sys.path or import `core`, `f8_next` or private SQLite tables.

## API map

| Area | Public entry points | Trust boundary |
|---|---|---|
| Motor | `protoagent_framework.engine.Engine` | Optional numeric computation, not authority |
| Sessions | `Session`, `create_session`, `start/step/run/pause/resume/cancel/complete/close` | Host journal; goal verifier decides completion |
| Tools | `Observation`, `ToolDefinition`, `ToolRegistry`, `RegisteredProvider`, `ToolResult` | Host registers trusted handlers and proof callbacks |
| Effects | `NativeToolStore`, `DurableCounter` | Atomic effect+receipt only within cooperating local provider |
| Memory | `MemoryStore`, `MemoryReference` | Revalidate entity/revision; references are not grants |
| Teams | `TeamCoordinator`, `RoleSession` | Host-issued current grants, entity scope and shared budget |
| Collaboration | `collaboration.Collaboration` | Owner/dependency/reviewer protocol, not autonomous planning |
| Backup | `RuntimeWorkspace` | All writers must cooperate; clone never restores grants |
| Limits | `runtime_config.RuntimeConfig`, `ResourcePolicy` | Host watchdog; no automatic deletion or killing |

See API.md, SECURITY.md and RECOVERY.md in this bundle before writing adapters.
Finite generators, ProgrammingRuntime, typed synthesis and reducer_store are
**experimental opt-in modules**, not unrestricted Python synthesis. External
provider transport is experimental; uncertain HTTP results need reconciliation.

## Resource/lifecycle policy

Use bounded session steps and `RuntimeConfig` workspace quota checks before NEW
work. Default512MiB workspace limit with16MiB closing reserve. This watchdog is
not an atomic disk quota; all host writers must cooperate. No automatic GC.
Keep journals, evidence and failed proposals. Call `close()` in `finally`, or use
the runtime context manager where provided. Session/SQLite stores own no daemon
services. Your host owns worker cancellation, IAM, backups and disk monitoring.

`ResourcePolicy` defaults to start2.5GB/emergency2GB with hysteresis; it does not
terminate other applications. Laboratory low-RAM exceptions do not change this
deployment guidance. Measure your own load; small local tests are not SLOs.

## What is shipped

Wheel: SDK, closed motor dependency closure, referenced library and license/
notice. No datasets, keys, virtualenvs, experiments or running service. Source
bundle: same build inputs plus public docs/examples/tests/CI runner. Sources of
runtime library modules are explicitly included for rebuilding the wheel.

The first experimental release does not require E123, universal team superiority,
free Python coding or an8h campaign. No production or publication is authorized
by installation. Read CHANGELOG.md and the release report for known negatives.
