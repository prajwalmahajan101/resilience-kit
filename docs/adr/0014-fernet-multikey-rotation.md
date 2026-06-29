# 0014 — Field-crypto key rotation via MultiFernet

Status: accepted  ·  Date: 2026-06-29  ·  Milestone: v0.2.0 (Lane C #C1)

## Context

v0.1 field crypto (`FernetCipher`, ADR-0008, #B6) wraps a single
`cryptography.fernet.Fernet` keyed from `settings.crypto.field_encryption_key`.
A single key makes rotation a stop-the-world operation: to retire a key you
must re-encrypt every stored column under the new key in one shot, with no
window where both keys are valid. Any compliance regime that mandates periodic
key rotation (PCI-DSS, ISO 27001, SOC 2) is effectively disqualified.

`cryptography` already ships `MultiFernet`, which decrypts a token by trying an
ordered list of `Fernet` instances and encrypts with the first. That is exactly
the primitive needed for graceful rotation: add the new key as primary, keep
the old key for decrypt-only, migrate ciphertext lazily or in a batch, then
drop the old key once nothing references it.

## Decision

- Key material is an **ordered list**, `settings.crypto.field_encryption_keys`
  (primary first; trailing keys are decrypt-only). `FernetCipher` builds a
  `MultiFernet` from it: encrypt uses the primary, decrypt tries each in turn.
- The singular `field_encryption_key` is kept as a **deprecated alias** for one
  minor cycle. When only the singular is set it becomes the sole key (with a
  `DeprecationWarning`); when both are set the list wins. `CryptoSettings.ordered_keys()`
  owns this resolution so the policy lives in one place.
- **No explicit per-token key-version prefix.** The KNOWN-ISSUES sketch
  suggested tagging each token with a key version; this is redundant. A Fernet
  token already carries a version byte and timestamp, and `MultiFernet` decrypts
  by trialing keys — adding our own prefix would duplicate that machinery,
  break interop with a bare `Fernet`/`MultiFernet`, and is not needed to know
  "which key wrote this" for rotation (rotation re-encrypts under the primary
  regardless).
- `FernetCipher.rotate(token)` delegates to `MultiFernet.rotate`: it decrypts
  with whichever configured key wrote the token and re-encrypts under the
  primary, without exposing plaintext. This is the migration primitive an
  operator runs over stored ciphertext after introducing a new primary.
- The `#B6` raw-key-vs-passphrase resolution (`_resolve_fernet_key`) is applied
  per key, so legacy SHA-256-derived passphrase keys remain decryptable inside
  the list.

## Consequences

- Rotation is now a documented, zero-downtime runbook (`docs/key-rotation.md`):
  prepend new primary → deploy → migrate ciphertext via `rotate()` → drop the
  retired key.
- Non-breaking: existing single-key deployments keep working via the deprecated
  alias; the dev fallback and prod env-guard are unchanged.
- A token written under a key that has been dropped from the list is no longer
  decryptable — the runbook's ordering (migrate *before* dropping) is the
  safeguard, and `rotate()`/`decrypt` raise `DecryptionError` if violated.
- HKDF/Argon2 salted derivation for low-entropy passphrases is still **not**
  implemented; the kit's position remains "supply a real Fernet key." That work,
  if it lands, is independent of rotation and would get its own ADR.

## Usage

```python
# Settings (env), primary first:
#   RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEYS=["<new-key>", "<old-key>"]
from resilience_kit.crypto import FernetCipher

# Existing ciphertext written under <old-key> still decrypts:
plaintext = FernetCipher.decrypt(old_token)

# New writes use <new-key>:
fresh = FernetCipher.encrypt("secret")

# Migrate an old token onto the new primary without seeing plaintext:
migrated = FernetCipher.rotate(old_token)
```

See `docs/key-rotation.md` for the full operator runbook.
