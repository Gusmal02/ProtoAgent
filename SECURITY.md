# Security policy and model of trust

Experimental local SDK for **trusted host Python and controlled SQLite files**.
Do not expose this SDK as an unauthenticated public web service. No arbitrary
plugins/untrusted Python are supported in-process. `-I` is import isolation,
not an OS sandbox. Host-issued grants must not be offered as actor tools.

The host owns process/file permissions, credentials, trusted verifiers, current
entity/policy and native transaction boundaries. Model output, library memory,
hashes and historical approvals never create authority. An artifact hash binds
content but does not prove that an untrusted report tells the truth.

Completion callbacks are registered by trusted host code. They expose proofs
for a goal+revision+artifact+request and help the explicit completion policy
choose a terminal action; they do NOT grant execution permission. Session
freezes these inputs for replay. The native effect revalidates current authority
and candidate approval. Never fill such callbacks from raw LLM claims.

Admission/revocation/entity boundaries, replay collisions, stale proofs, budget,
path traversal and serialization are mandatory regression targets. SQLite
effect+receipt guarantees do not extend automatically to HTTP or services with
no durable idempotency/status endpoint. Unknown outcomes remain uncertain.

Do not put tokens, API keys or real customer data in examples, checkpoints or
public reports. A hash-chain journal detects changes, but a host administrator
able to rewrite its database is outside its tamper-resistance boundary. Encryption
and immutable external audit storage are not supplied by this release.

## Reporting

No private contact address has been designated. Until a repository with private
vulnerability reporting is configured, report privately to the project owner
through your existing direct channel. Do not post secrets or exploitable details
in a public issue. Include version/hash, bounded synthetic reproducer, affected
trust boundary and expected/actual effects. No authorization to test real networks.

Dependency versions/metadata are inventoried by release qualification. Offline
review is **not** a current CVE/advisory scan; operators must review vulnerability
advisories before deploying. No claim of pentesting coverage or ransomware rescue.
