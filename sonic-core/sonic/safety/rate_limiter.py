"""
SONIC-REDA — Target-Safe Egress Rate Limiter & Concurrency Throttler
=====================================================================
Protects target infrastructure and maintains scope compliance through:
    - Token Bucket rate limiting per target domain/IP
    - Global concurrency throttling
    - Adaptive backoff on HTTP 429 / 503 responses (Circuit Breaker)
    - Anti-DoS safeguards ensuring non-disruptive testing
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TargetBucket:
    """Token bucket state for a single target domain/host."""
    rate: float  # Tokens added per second (RPS)
    capacity: float  # Maximum burst capacity
    tokens: float
    last_update: float = field(default_factory=time.monotonic)
    backoff_multiplier: float = 1.0
    active_connections: int = 0
    max_concurrent: int = 5


class EgressRateLimiter:
    """
    Manages rate limiting and concurrency across all active agents and tools.
    """

    def __init__(self, default_rps: float = 15.0, default_burst: float = 30.0, max_concurrent: int = 5):
        self.default_rps = default_rps
        self.default_burst = default_burst
        self.max_concurrent = max_concurrent
        self.buckets: dict[str, TargetBucket] = {}
        self._lock = asyncio.Lock()

    def _get_bucket(self, target_host: str) -> TargetBucket:
        # Caller MUST hold self._lock — all mutations go through acquire/release,
        # which take the lock, so this lookup is always race-free.
        if target_host not in self.buckets:
            self.buckets[target_host] = TargetBucket(
                rate=self.default_rps,
                capacity=self.default_burst,
                tokens=self.default_burst,
                max_concurrent=self.max_concurrent,
            )
        return self.buckets[target_host]

    async def acquire(self, target_host: str, tokens_needed: float = 1.0) -> None:
        """
        Wait until sufficient tokens are available and concurrency is under limits.
        """
        while True:
            async with self._lock:
                bucket = self._get_bucket(target_host)
                now = time.monotonic()
                elapsed = now - bucket.last_update
                bucket.last_update = now

                # Add tokens based on time elapsed and backoff
                effective_rate = bucket.rate / bucket.backoff_multiplier
                bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * effective_rate)

                if bucket.tokens >= tokens_needed and bucket.active_connections < bucket.max_concurrent:
                    bucket.tokens -= tokens_needed
                    bucket.active_connections += 1
                    return

                # Calculate wait time
                needed = tokens_needed - bucket.tokens
                wait_seconds = max(0.05, needed / effective_rate if effective_rate > 0 else 0.5)

            await asyncio.sleep(wait_seconds)

    async def release(self, target_host: str, status_code: int | None = None) -> None:
        """
        Release an active connection and adjust adaptive backoff based on server response.
        """
        async with self._lock:
            bucket = self._get_bucket(target_host)
            bucket.active_connections = max(0, bucket.active_connections - 1)

            if status_code in [429, 503, 504]:
                # Server is overloaded -> increase backoff multiplier
                bucket.backoff_multiplier = min(8.0, bucket.backoff_multiplier * 2.0)
                logger.warning(
                    "target_rate_limit_backoff",
                    target=target_host,
                    status=status_code,
                    multiplier=bucket.backoff_multiplier,
                )
            elif status_code and 200 <= status_code < 300:
                # Gradual recovery
                bucket.backoff_multiplier = max(1.0, bucket.backoff_multiplier * 0.9)


# Global singleton
_rate_limiter: EgressRateLimiter | None = None


def get_rate_limiter() -> EgressRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = EgressRateLimiter()
    return _rate_limiter
