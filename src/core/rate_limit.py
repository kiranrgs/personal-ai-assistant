"""Small in-process sliding-window rate limiter (per key, e.g. client IP or
email). Good enough for a single uvicorn worker; for multiple workers/hosts
put a shared limiter (reverse proxy / Redis) in front as well.
"""
from __future__ import annotations

import threading
import time
from collections import deque

_MAX_KEYS = 50_000


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Records an attempt for `key`; returns False if it's over the limit."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            if len(self._events) > _MAX_KEYS:
                self._prune(cutoff)
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True

    def _prune(self, cutoff: float) -> None:
        for k in [k for k, v in self._events.items() if not v or v[-1] <= cutoff]:
            del self._events[k]
