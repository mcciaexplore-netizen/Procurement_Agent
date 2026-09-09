"""Small dependency-free operational controls for the modular monolith."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import monotonic


def configured_origins(value: str | None) -> list[str]:
    """Parse a deployment-supplied, explicit CORS allow-list."""
    origins = [origin.strip().rstrip("/") for origin in (value or "").split(",") if origin.strip()]
    return origins or ["http://localhost:3000"]


@dataclass(frozen=True, slots=True)
class Readiness:
    sources: int
    active_sources: int
    offers: int


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("rate limiter limit and window must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        with self._lock:
            requests = self._requests[key]
            while requests and current - requests[0] >= self.window_seconds:
                requests.popleft()
            if len(requests) >= self.limit:
                return False
            requests.append(current)
            return True


class DailyRequestQuota:
    """A per-process hard cap for an external provider's calendar-day requests."""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("daily quota limit must be positive")
        self.limit = limit
        self._usage: dict[str, tuple[str, int]] = {}
        self._lock = Lock()

    def consume(self, key: str, now: datetime | None = None) -> bool:
        day = (now or datetime.now(UTC)).date().isoformat()
        with self._lock:
            recorded_day, count = self._usage.get(key, (day, 0))
            if recorded_day != day:
                count = 0
            if count >= self.limit:
                return False
            self._usage[key] = (day, count + 1)
            return True
