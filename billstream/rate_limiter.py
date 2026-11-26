"""Per-tenant thread-safe sliding-window rate limiter."""

from collections import deque
import math
import threading
import time
from typing import Deque, Dict, Optional, Tuple


class SlidingWindowRateLimiter:
    """Enforces requests-per-window limits independently for each tenant."""

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check_and_consume(
        self,
        tenant_id: str,
        limit: int,
        now: Optional[float] = None,
    ) -> Tuple[bool, int, int]:
        """Check whether a tenant may make a request and record it if allowed.

        Returns:
            (allowed, remaining_requests, retry_after_seconds)
        """
        ts = time.monotonic() if now is None else now
        cutoff = ts - self.window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(tenant_id, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                oldest = bucket[0]
                retry_after = max(1, int(math.ceil(self.window_seconds - (ts - oldest))))
                return False, 0, retry_after

            bucket.append(ts)
            remaining = max(0, limit - len(bucket))
            return True, remaining, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
