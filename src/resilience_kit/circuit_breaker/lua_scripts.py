"""Atomic Lua script for the Redis circuit breaker.

State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED) and per-attempt
mutations all happen inside one ``EVALSHA`` round-trip — no read/modify/
write race across workers. TTL is refreshed on every write so a quiet
service's state self-expires.

The script is versioned. Bumping :data:`BREAKER_LUA_VERSION` invalidates
caller SHA caches and forces a fresh ``SCRIPT LOAD`` on next call.
"""

from __future__ import annotations

#: Version tag — bump in lockstep with any change to the script body.
BREAKER_LUA_VERSION = "v1"

#: The script itself. Ported verbatim from
#: ``fastapi_boilerplate/src/core/resilience/circuit_breaker/redis_impl.py``.
# ruff: noqa: E501 — Lua bodies follow upstream formatting; do not wrap.
BREAKER_LUA = """\
local key = KEYS[1]
local action = ARGV[1]
local failure_threshold = tonumber(ARGV[2])
local success_threshold = tonumber(ARGV[3])
local recovery_timeout = tonumber(ARGV[4])
local now = tonumber(ARGV[5])
local ttl = math.ceil(recovery_timeout * 10)

local function read_state()
    local vals = redis.call('HMGET', key, 'state', 'failure_count', 'success_count', 'last_failure')
    local state = vals[1] or 'closed'
    local fc = tonumber(vals[2]) or 0
    local sc = tonumber(vals[3]) or 0
    local lf = tonumber(vals[4]) or 0
    return state, fc, sc, lf
end

local function write_state(state, fc, sc, lf)
    redis.call('HMSET', key, 'state', state, 'failure_count', fc, 'success_count', sc, 'last_failure', lf)
    redis.call('EXPIRE', key, ttl)
end

local state, fc, sc, lf = read_state()

if state == 'open' and (now - lf) >= recovery_timeout then
    state = 'half_open'
    sc = 0
    write_state(state, fc, sc, lf)
end

if action == 'is_available' then
    if state == 'open' then
        local remaining = recovery_timeout - (now - lf)
        if remaining < 0 then remaining = 0 end
        return {0, state, tostring(remaining)}
    end
    return {1, state, '0'}

elseif action == 'record_success' then
    if state == 'half_open' then
        sc = sc + 1
        if sc >= success_threshold then
            state = 'closed'
            fc = 0
        end
    elseif state == 'closed' then
        fc = 0
    end
    write_state(state, fc, sc, lf)
    return {1, state, '0'}

elseif action == 'record_failure' then
    fc = fc + 1
    lf = now
    if state == 'half_open' then
        state = 'open'
    elseif state == 'closed' and fc >= failure_threshold then
        state = 'open'
    end
    write_state(state, fc, sc, lf)
    local remaining = 0
    if state == 'open' then
        remaining = recovery_timeout
    end
    return {1, state, tostring(remaining)}

elseif action == 'reset' then
    redis.call('DEL', key)
    return {1, 'closed', '0'}

elseif action == 'get_stats' then
    return {state, tostring(fc), tostring(sc), tostring(lf)}
end

return {0, 'error', '0'}
"""
