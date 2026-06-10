"""Settings schema for ``resilience_kit``.

Implements LLD §10. Loaded from env with prefix ``RESILIENCE_`` and nested
delimiter ``__`` (e.g. ``RESILIENCE_DEFAULTS__RETRY__MAX_ATTEMPTS=5``), or
from a caller-supplied :class:`~resilience_kit.runtime.SettingsSource`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetryDefaults(BaseModel):
    """Default retry policy applied when a service has no override."""

    max_attempts: int = 3
    wait_min: float = 1.0
    wait_max: float = 10.0
    exponential_base: float = 2.0
    jitter: Literal["none", "full", "decorrelated"] = "decorrelated"


class BreakerDefaults(BaseModel):
    """Default circuit-breaker policy applied when a service has no override."""

    fail_max: int = 5
    reset_timeout: float = 30.0
    success_threshold: int = 2


class ThrottleDefaults(BaseModel):
    """Default throttle policy applied when a route has no scope override."""

    auth_rate: str = "5/min"


class Defaults(BaseModel):
    """Bundle of per-subsystem default policies."""

    retry: RetryDefaults = Field(default_factory=RetryDefaults)
    circuit_breaker: BreakerDefaults = Field(default_factory=BreakerDefaults)
    throttle: ThrottleDefaults = Field(default_factory=ThrottleDefaults)


class SSRFSettings(BaseModel):
    """SSRF guard settings — primary impl lands in M3."""

    block_private_ips: bool = True
    outbound_allowlist: list[str] = Field(default_factory=lambda: ["*"])


class CryptoSettings(BaseModel):
    """Field-level Fernet crypto settings (LLD §10).

    ``environment`` gates the "refuse to start without a key" guard. The
    default ``"prod"`` means a missing ``field_encryption_key`` is a
    configuration error; ``"dev"`` / ``"test"`` fall back to a static
    well-known dev key with a one-time warning so local boots work.
    """

    field_encryption_key: SecretStr | None = None
    environment: Literal["prod", "dev", "test"] = "prod"


class RecoverySettings(BaseModel):
    """Recovery-monitor settings (LLD §8).

    Production default polls every 10 s with a 3-success stable window;
    tests inject smaller values via the settings-source indirection.
    """

    probe_interval_seconds: float = 10.0
    stable_window_successes: int = 3
    ping_alias: str = "default"


class AuditSettings(BaseModel):
    """Audit (``api_log``) settings — primary impl lands in M4."""

    sink: str = "stdlib_logging"
    sanitizer: str = "default"
    redact_fields: list[str] = Field(
        default_factory=lambda: ["password", "token", "secret", "authorization"],
    )
    queue_size: int = 10_000
    batch_max: int = 100
    batch_interval_ms: int = 50


class ResilienceSettings(BaseSettings):
    """Top-level settings model.

    Concrete backends arrive in later milestones. At M1 the model is fully
    typed so callers can write code against its shape, even though only the
    ``defaults`` block has runtime effect.
    """

    backend: Literal["auto", "memory", "redis", "pybreaker"] = "auto"
    redis_url: str | None = None
    metrics_sink: str = "noop"
    defaults: Defaults = Field(default_factory=Defaults)
    ssrf: SSRFSettings = Field(default_factory=SSRFSettings)
    crypto: CryptoSettings = Field(default_factory=CryptoSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    recovery: RecoverySettings = Field(default_factory=RecoverySettings)

    model_config = SettingsConfigDict(
        env_prefix="RESILIENCE_",
        env_nested_delimiter="__",
        # Fail loud on unknown top-level keys in dict-shaped inputs
        # (Django settings.RESILIENCE = {...}, programmatic
        # model_validate(...), JSON config files). Typos such as
        # "CIRCUIT_BREAKER_CONFIG" or "deafults" now raise ValidationError
        # instead of being silently dropped.
        #
        # NOTE: pydantic-settings filters unknown RESILIENCE_*-prefixed
        # env vars at the EnvSettingsSource layer — they never reach the
        # model, so extra="forbid" does not catch env-var typos. Tracked
        # as a follow-up; the dict-level fix still resolves the Django
        # adapter path that bites first in practice.
        extra="forbid",
    )
