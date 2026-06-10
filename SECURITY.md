# Security policy

`resilience-kit` is a backend resilience library — its surface includes an
SSRF guard, field-level crypto, and stateful concurrency primitives (circuit
breaker / throttle / cache). Vulnerabilities in any of those are taken
seriously.

## Supported versions

| Version | Status |
|---|---|
| `0.1.x` | ✅ active — security fixes released as patch versions |
| `< 0.1` (pre-release) | ❌ unsupported — upgrade to `0.1.x` |

`0.1.0rc1` and any later pre-release are covered by the same policy as
`0.1.x` until `0.1.0` final ships, at which point pre-releases are
unsupported.

## Reporting a vulnerability

**Do not open a public GitHub issue.** Report privately via GitHub Security
Advisories:

> <https://github.com/prajwalmahajan101/resilience-kit/security/advisories/new>

Include:

- A minimal reproduction (a failing test, a script, or the affected commit
  + decorator stack).
- The kit version (`python -c "import resilience_kit; print(resilience_kit.__version__)"`)
  and Python version.
- Which extras are installed (`pip show resilience-kit`).
- The expected vs observed behaviour, and your assessment of impact.

Expect a first response within 5 business days. Once a fix is staged, an
advisory is published with credit (unless you ask otherwise) and a CVE is
requested where appropriate.

## What's in scope

- **SSRF guard bypass** — validate→connect TOCTOU (DNS rebinding),
  outbound allow-list escape, IP-family confusion, link-local / loopback /
  reserved-range bypasses.
- **Crypto misuse** — `FernetCipher` key-derivation regressions,
  decryption-error information leak, plaintext-vs-bytes confusion in field
  types (`EncryptedCharField`, `EncryptedString`).
- **Concurrency state corruption** — circuit-breaker, throttle, or cache
  invariants broken under concurrent access on `memory` or `redis`
  backends.
- **Audit-log injection / sanitizer bypass** — fields named in
  `redact_fields` leaking into sinks, sanitizer recursion crashes, audit
  decorators dropping or duplicating records under load.
- **Dependency CVEs** in pinned ranges (`httpx >=0.27,<0.29`,
  `redis-py >=5`, `pydantic`, `cryptography`).
- **DoS via protocol-violating third-party backend** — a malicious or
  buggy backend (entry-point shadowing per ADR 0004) crashing or
  deadlocking the kit's resolver / recovery monitor.

## What's out of scope

- Vulnerabilities in user-supplied backends, sinks, or sanitizers — those
  are the authors' responsibility. The kit's resolver chain is in scope
  for *how it loads them*, not for what they do.
- Misconfiguration (e.g. missing `field_encryption_key` in production,
  permissive SSRF allow-list `["*"]`) — these are footguns the kit aims
  to fail loud about; file an issue if a footgun is silent.
- Issues in downstream FastAPI / Django code outside
  `src/resilience_kit/adapters/`. Report those to the respective project.
- Theoretical timing attacks without a working PoC.
- Code-quality / lint findings without a security impact.
