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
    """Field-level Fernet crypto settings — primary impl lands in M3."""

    field_encryption_key: SecretStr | None = None


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

    model_config = SettingsConfigDict(
        env_prefix="RESILIENCE_",
        env_nested_delimiter="__",
        extra="ignore",
    )
