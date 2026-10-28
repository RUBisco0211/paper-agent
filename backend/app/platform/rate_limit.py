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

if tok_rate > 0 and tokens > tok_cap then
  -- More than the bucket can ever hold: waiting is pointless.
  return "-1"
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
        """Block until one request costing ``tokens`` may proceed.

        Raises ``ValueError`` when the request is larger than the bucket can
        ever hold: such a call would wait forever and hold the caller's thread.
        """
        if not self._request_rate and not self._token_rate:
            return
        if self._token_rate and tokens > self._token_cap:
            raise ValueError(
                f"请求需要 {tokens:g} tokens，超过每分钟额度 {self._token_cap:g}"
            )
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
            if wait < 0:  # the script's "cannot ever be satisfied"
                raise ValueError("请求超出限流额度")
            if wait <= 0:
                return
            self._sleep(min(wait, 1.0))


#: BPE tokenizers spend far fewer characters per token on CJK than on Latin
#: text, so one flat ratio is wrong in one direction or the other.
#:
#: The CJK ratio is deliberately below the ~1.5 characters per token that
#: bge-m3's tokenizer averages on prose: underestimating would let a batch slip
#: past the meter and earn a 429 on the provider side, while overestimating only
#: makes this process wait a little longer.
_LATIN_CHARS_PER_TOKEN = 4.0
_CJK_CHARS_PER_TOKEN = 1.0


def estimate_tokens(text: str | int) -> int:
    """Rough token estimate for metering; embedding pricing is token-based.

    Counted pessimistically within each script: overestimating only makes the
    caller wait, underestimating earns a 429 from the provider. A bare number is
    read as a count of Latin characters.
    """
    if isinstance(text, int):
        return max(1, math.ceil(text / _LATIN_CHARS_PER_TOKEN))
    cjk = sum(1 for char in text if _is_cjk(char))
    latin = len(text) - cjk
    tokens = cjk / _CJK_CHARS_PER_TOKEN + latin / _LATIN_CHARS_PER_TOKEN
    return max(1, math.ceil(tokens))


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF  # CJK unified ideographs
        or 0x3400 <= code <= 0x4DBF
        or 0x3040 <= code <= 0x30FF  # kana
        or 0xAC00 <= code <= 0xD7AF  # hangul
    )
