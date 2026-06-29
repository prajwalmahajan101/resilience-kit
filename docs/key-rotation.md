# Field-encryption key rotation

`resilience-kit` encrypts field-level secrets (via `EncryptedString` /
`EncryptedCharField`) with `FernetCipher`, backed by
`cryptography.fernet.MultiFernet`. Because the key material is an *ordered list*
(`settings.crypto.field_encryption_keys`, primary first), you can rotate keys
with **zero downtime** and **no stop-the-world re-encrypt**.

See [ADR-0014](./adr/0014-fernet-multikey-rotation.md) for the design rationale.

## Model

- **Encryption** always uses the **primary** key (first in the list).
- **Decryption** tries each key in order, so ciphertext written under any
  still-listed key decrypts.
- `FernetCipher.rotate(token)` decrypts a token under whatever key wrote it and
  re-encrypts it under the current primary — without exposing plaintext.

## Generating a key

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())   # 44 url-safe-base64 chars
```

Always supply a real Fernet key. A short passphrase falls back to the
deprecated, unsalted SHA-256 derivation (#B6) and emits a warning.

## Runbook — rotating from K1 to K2

The ordering is the safeguard: **introduce the new key, migrate, then drop the
old one.** Never drop a key while ciphertext written under it still exists.

### 1. Add the new key as primary, keep the old for decrypt

```bash
# env (primary first):
RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEYS=["<K2>", "<K1>"]
```

Deploy. From this point:
- new writes are encrypted under **K2**,
- existing **K1** ciphertext still decrypts (K1 is still listed).

### 2. Migrate stored ciphertext onto K2

Re-encrypt each stored value with `rotate()`. Example for a SQLAlchemy column:

```python
from resilience_kit.crypto import FernetCipher

for row in session.query(Model).yield_per(1000):
    # `_field` is the raw stored token (bypass the TypeDecorator).
    token = row.__dict__["secret_field"]
    if token:
        row.secret_field = FernetCipher.rotate(token)
    session.commit()
```

Run this as a management command / batch job. It is idempotent: a token already
under K2 simply re-encrypts under K2 again.

### 3. Drop the retired key

Once **no** ciphertext references K1 (migration complete and verified):

```bash
RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEYS=["<K2>"]
```

Deploy. K1 is now fully retired.

## Migrating off a legacy passphrase / SHA-256 key

If you were on the pre-#B6 singular passphrase (`field_encryption_key`):

1. Generate a real Fernet key `K_new`.
2. Set `field_encryption_keys=["<K_new>", "<old-passphrase>"]`. The old
   passphrase is still resolved through the deprecated SHA-256 path for
   decrypt, so existing data is readable while new data uses `K_new`.
3. Run the `rotate()` migration (step 2 above).
4. Drop the passphrase: `field_encryption_keys=["<K_new>"]`.

## Gotchas

- **Don't drop a key before migrating.** A token under a dropped key raises
  `DecryptionError`.
- The cipher is cached per process (`functools.lru_cache`). Changing keys
  requires a redeploy / process restart (or `reset_fernet_cache()` in tests).
- The deprecated singular `field_encryption_key` still works for one minor
  cycle but emits a `DeprecationWarning`; migrate to the list form.
