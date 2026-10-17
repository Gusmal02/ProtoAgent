# ProtoAgent Framework

Experimental local Python framework for motor-driven decisions, durable
sessions, verified tools, contextual memory and role collaboration.
**No LLM required. Licensed under Apache-2.0.**

Candidate **0.1.0rc3**, locally qualified on CPython3.12 Windows x64.
Linux is a CI target, not yet a qualified result. This repository contains the
audited SDK source closure, not the research workspace or private data.

## Get started

```console
python -m venv .venv
# Activate your environment, then:
python -m pip install ".[motor]"
python examples/local_counter.py --workspace ./counter-demo
python examples/referenced_data.py --workspace ./data-demo
python examples/collaboration_data_ops.py --workspace ./team-demo
```

Use a new workspace for each example. Base install `pip install .` needs no
numerical dependencies. Motor/library operations need `[motor]`. No API key.

## Documentation

- [Installation and scope](framework/distribution/README.md)
- [API contracts](framework/distribution/API.md)
- [Recovery and resources](framework/distribution/RECOVERY.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](framework/distribution/CHANGELOG.md)

## Regression gate

```console
python -m pip install build
python -m build
# Install the wheel in a separate environment with [motor], then:
python -I tools/release_gate.py --wheel <wheel-path> --output <new-report-folder>
```

GitHub Actions checks clean Windows/Linux installations, base and motor profiles.
Local rc3 passed18 full tests,13 base tests,273 governance checks per profile
and the public examples. An assisted independent consumer verified completion,
nonterminal reopening, budget, replay and revocation. These are bounded local
results, not production SLOs or claims of general intelligence.

Trusted host Python and cooperating SQLite only: no hostile plugins or OS
sandbox. Evidence/hashes never grant authority. Remote providers, unrestricted
programming and continuous production operation remain experimental/unqualified.
Third-party dependencies retain their licenses. See [LICENSE](LICENSE) and
[NOTICE](NOTICE) for the SDK and bundled motor/library source closure.
