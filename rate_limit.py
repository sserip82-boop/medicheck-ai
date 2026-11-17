"""Lightweight process-local quota guard for a public demonstration.

NOT a reliable distributed abuse prevention mechanism. Configure provider quotas too.
"""
from collections import deque
from threading import Lock
from time import monotonic

class HourlyLimiter:
    def __init__(self, max_calls=60, window_seconds=3600):
        self.max_calls=max_calls
        self.window_seconds=window_seconds
        self.calls=deque()
        self.lock=Lock()

    def try_consume(self, now=None):
        t=monotonic() if now is None else now
        with self.lock:
            while self.calls and self.calls[0] <= t-self.window_seconds:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                return False
            self.calls.append(t)
            return True

# Shared among sessions in one Python process. Does not persist across restarts.
PUBLIC_LIMITER=HourlyLimiter(max_calls=60)
