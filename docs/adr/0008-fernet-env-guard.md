# 0008 — Fernet env-guard: refuse to start in prod without a key

Status: accepted  ·  Date: 2026-06-09  ·  Milestone: M3

## Context

`FernetCipher` round-trips field-level secrets (plaintext ↔ ciphertext)
for the SQLAlchemy `EncryptedString` (M5) and the Django
`EncryptedCharField` (M6). The Fernet key is derived from a dedicated
`field_encryption_key` setting — a single rotation point that is
deliberately separate from the application's general `secret_key` so
routine rotation of session secrets cannot accidentally corrupt
encrypted columns.

But what happens when `field_encryption_key` is not set? Three options:

1. Silently fall back to a hard-coded constant. Boots work everywhere
   but a prod misconfiguration encrypts with a known key — and the
   first key rotation corrupts every encrypted column irrecoverably.
2. Always raise. Local boots break for anyone who hasn't read the
   docs; dev velocity suffers.
3. Gate the behaviour on environment: prod refuses to start, dev/test
   warns and uses a known-insecure constant.

## Decision

Option 3. `CryptoSettings` carries an `environment: Literal["prod",
"dev", "test"]` field (default `"prod"`). `FernetCipher._fernet()`:

- If `field_encryption_key` is set → use it. Always.
- If unset + `environment="prod"` → raise `EncryptionConfigError` at
  the first `encrypt` / `decrypt` call, with the explicit hint that
  silent fallback is disabled to prevent data corruption on rotation.
- If unset + `environment in {"dev", "test"}` → log a one-time warning
  and derive the key from a hard-coded constant
  (`_DEV_FALLBACK_KEY`). The constant is **insecure on purpose** so it
  can never accidentally be a viable prod key.

## Update (v0.1.1, Lane B #B6) — key resolution: prefer a real Fernet key

The original derivation always ran the configured value through unsalted
SHA-256: `Fernet(b64encode(sha256(key_source)))`. That is secure only when
`field_encryption_key` is itself high-entropy random — which was never a
documented requirement. For human-chosen or config-file passphrases it is
brute-forceable (CWE-916).

`_fernet()` now resolves the key in two steps:

1. If `field_encryption_key` is already a valid Fernet key (32 url-safe
   base64 bytes, e.g. from `Fernet.generate_key()`), it is used **directly**.
   This is the recommended path and the one the docs now point at.
2. Otherwise the value is treated as a passphrase and SHA-256-derived as
   before — but this path is **deprecated** and emits a one-time warning.
   It is kept solely so data encrypted by earlier versions still decrypts;
   the derivation is byte-for-byte unchanged, so no migration is forced.

`CryptoSettings.field_encryption_key` also gained a validator that warns when
the value is a short passphrase (< 32 chars). Salted-KDF / Argon2 hardening
and key rotation are deliberately **not** done here — they arrive with
`MultiFernet` in Lane C (#C1). This change is non-breaking: existing
passphrase users keep working (with a nudge), and new deployments get the
direct-key path.

## Consequences

- Prod cannot silently encrypt with a guessable key. The failure is
  loud, immediate, and points at the exact env var to set
  (`RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY`).
- Local boots and CI still work without any setup; the warning is
  noisy enough to be visible if it ever shows up in a prod log
  pipeline.
- The `environment` setting joins `RESILIENCE_BACKEND="auto"` as the
  small set of "operate the kit's posture knobs" inputs the operator
  has to think about.
- Tradeoff: the env decision lives inside `CryptoSettings` rather than
  a global `ResilienceSettings.environment`. We resisted promoting it
  to a top-level field because it would push every subsystem to grow
  its own per-environment branch. If a second subsystem needs the
  same gate, revisit by introducing a top-level
  `ResilienceSettings.deployment_environment`.

## Usage

```bash
# Prod: required.
export RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY=...

# Local dev / CI: nothing required; warns once.
export RESILIENCE_CRYPTO__ENVIRONMENT=dev
```

```python
from resilience_kit import FernetCipher

token = FernetCipher.encrypt("alice@example.com")
plaintext = FernetCipher.decrypt(token)
```
