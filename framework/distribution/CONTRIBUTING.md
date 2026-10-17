# Contributing

> La guía principal en español está en [CONTRIBUTING.md](../../CONTRIBUTING.md).

Use CPython3.12, an isolated environment and a synthetic local workspace.
The release source archive is deliberately smaller than the research monorepo.
Build with `python -m pip install build` then `python -m build`; install the
resulting wheel into a different venv before testing.

Run `python -I tools/release_gate.py --wheel <wheel> --output <new-directory>`
with `[motor]` dependencies installed. Tests are sequential. Keep failing
results; never change acceptance/budgets after inspecting a failure to make it
pass. Add a minimal regression for each fix, including a negative authority case.
Do not add network/API calls or automatic package publishing to regression CI.

Contributions are submitted under Apache-2.0. Preserve existing attribution and
third-party notices. State which code was written by a human/Codex/external
model, which decisions came from the motor, and which tests were host scripts.
Do not upload keys, private datasets, venvs, large DBs or model weights.

Changes to public schemas/authority/replay require compatibility notes and
installed-package tests. Changes to release scope require an explicit changelog.
No new benchmark campaign is needed for a documentation-only correction.
