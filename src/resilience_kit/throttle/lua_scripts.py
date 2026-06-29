"""Atomic Lua scripts for the Redis-backed throttle.

Two scripts:
  * :data:`SLIDING_WINDOW_LUA` — per-identifier sliding window using a
    sorted set; admits exactly ``limit`` events per ``window_seconds``.
  * :data:`FIXED_WINDOW_LUA` — global O(1) two-bucket weighted average,
    suitable for a single shared bucket across many keys.

Ported from
``fastapi_boilerplate/src/core/resilience/throttle/lua_scripts.py`` (and
``global_lua.py`` for the fixed-window variant), with two changes:

1. The sliding-window member id uses a deterministic per-key ``INCR``
   counter instead of ``math.random`` (the member id must stay unique
   and deterministic).
2. ``now`` is read from the **server** via ``redis.call('TIME')`` rather
   than passed in by the client. Two pods with NTP drift would otherwise
   compute different window cutoffs against the same sorted set,
   silently breaking the sliding-window invariant (over- or
   under-throttling the fleet).

Because ``TIME`` is a non-deterministic command, each script declares
``redis.replicate_commands()`` up front so writes after the ``TIME`` read
are accepted on Redis < 7 (verbatim replication). It is a harmless no-op
on Redis 7+ / Valkey 8 (effect replication is already the default).
"""

from __future__ import annotations

#: Version tag — bump in lockstep with any change.
THROTTLE_LUA_VERSION = "v3"

#: Per-identifier sliding window. Returns ``{allowed, count, ttl}``.
SLIDING_WINDOW_LUA = """\
redis.replicate_commands()
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000

local cutoff = now - window

redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)

if count >= limit then
    local ttl = redis.call('TTL', key)
    if ttl < 0 then ttl = window end
    return {0, count, ttl}
end

local seq = redis.call('INCR', key .. ':__seq')
redis.call('EXPIRE', key .. ':__seq', window)
redis.call('ZADD', key, now, tostring(now) .. ':' .. tostring(seq))
redis.call('EXPIRE', key, window)

return {1, count + 1, window}
"""

#: Global fixed-window with two-bucket weighted blend; O(1). Returns
#: ``{allowed, effective_count_ceil, remaining_window_seconds_ceil}``.
FIXED_WINDOW_LUA = """\
redis.replicate_commands()
local key_prefix = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000

local window_start = math.floor(now / window) * window
local window_position = (now - window_start) / window

local current_key  = key_prefix .. ':' .. tostring(math.floor(window_start))
local previous_key = key_prefix .. ':' .. tostring(math.floor(window_start - window))

local current_count  = tonumber(redis.call('GET', current_key)  or '0')
local previous_count = tonumber(redis.call('GET', previous_key) or '0')

local effective_count = current_count + previous_count * (1 - window_position)

if effective_count >= limit then
    local ttl = window - (now - window_start)
    return {0, math.ceil(effective_count), math.ceil(ttl)}
end

redis.call('INCR', current_key)
redis.call('EXPIRE', current_key, window * 2)

return {1, math.ceil(effective_count) + 1, math.ceil(window - (now - window_start))}
"""
