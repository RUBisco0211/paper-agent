"""A shared token bucket for a remote API that meters requests and volume.

Two limits usually apply at once — requests per minute and tokens per minute —
and whichever runs out first decides the pace. Callers take capacity before each
call instead of collecting 429s from the provider.

The bucket lives in Redis because the limit belongs to the API key, not to a
process: two workers each holding a private bucket would together spend twice
the allowance.
"""

from __future__ import annotations

import math
import time

from redis import Redis
from redis.exceptions import RedisError

#: Refill both counters, then take one request and `tokens` if they suffice.
#: Returns the number of seconds the caller should wait (0 means it may go).
_ACQUIRE = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local req_rate = tonumber(ARGV[2])
local req_cap = tonumber(ARGV[3])
local tok_rate = tonumber(ARGV[4])
local tok_cap = tonumber(ARGV[5])
local tokens = tonumber(ARGV[6])

local state = redis.call('HMGET', key, 'requests', 'tokens', 'at')
local requests = tonumber(state[1])
local available = tonumber(state[2])
local at = tonumber(state[3])
if requests == nil then
  requests = req_cap
  available = tok_cap
  at = now
end

local elapsed = math.max(0, now - at)
if req_rate > 0 then
  requests = math.min(req_cap, requests + elapsed * req_rate)
end
if tok_rate > 0 then
  available = math.min(tok_cap, available + elapsed * tok_rate)
end

local wait = 0
if req_rate > 0 and requests < 1 then
  wait = math.max(wait, (1 - requests) / req_rate)
end
if tok_rate > 0 and available < tokens then
  wait = math.max(wait, (tokens - available) / tok_rate)
end

if wait > 0 then
  redis.call('HSET', key, 'requests', requests, 'tokens', available, 'at', now)
  redis.call('EXPIRE', key, 120)
  return tostring(wait)
end

if req_rate > 0 then requests = requests - 1 end
if tok_rate > 0 then available = available - tokens end
redis.call('HSET', key, 'requests', requests, 'tokens', available, 'at', now)
redis.call('EXPIRE', key, 120)
return "0"
"""


class TokenBucket:
    """Meter one API key across every process that shares the Redis instance.

    ``requests_per_minute`` or ``tokens_per_minute`` set to 0 disables that half
    of the limit, which is what a self-hosted service needs.
    """

    def __init__(
        self,
        *,
        client: Redis,
        name: str,
        requests_per_minute: float = 0,
        tokens_per_minute: float = 0,
        clock=time.time,
        sleep=time.sleep,
    ) -> None:
        self._client = client
        self._key = f"ratelimit:{name}"
        self._request_rate = (requests_per_minute or 0) / 60
        self._token_rate = (tokens_per_minute or 0) / 60
        self._request_cap = max(1.0, requests_per_minute or 0)
        self._token_cap = max(1.0, tokens_per_minute or 0)
        self._clock = clock
        self._sleep = sleep

    def acquire(self, *, tokens: float = 0) -> None:
        """Block until one request costing ``tokens`` may proceed."""
        if not self._request_rate and not self._token_rate:
            return
        while True:
            try:
                verdict = self._client.eval(
                    _ACQUIRE,
                    1,
                    self._key,
                    self._clock(),
                    self._request_rate,
                    self._request_cap,
                    self._token_rate,
                    self._token_cap,
                    tokens,
                )
            except RedisError:
                # Losing the meter must not lose the work: proceed and let the
                # provider answer with its own 429 if we really are over.
                return
            wait = float(verdict)
            if wait <= 0:
                return
            self._sleep(min(wait, 1.0))


def estimate_tokens(chars: int) -> int:
    """Rough token estimate for metering; embedding pricing is token-based.

    Text is counted pessimistically at three characters per token: overshooting
    the provider's own accounting would earn a 429, undershooting only slows us
    down.
    """
    return max(1, math.ceil(chars / 3))
