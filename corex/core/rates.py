"""Turns monotonically increasing counters into per-second rates."""

from __future__ import annotations


class RateTracker:
    """
    Remembers the previous value of each counter and the time it was read.

    The rate is (difference) / (real elapsed time) between two ticks, so it
    stays correct whatever the polling interval is or however late a tick
    runs. The first sample of a counter has no rate yet (None).
    """

    def __init__(self) -> None:
        self._prev: dict[str, tuple[float, float]] = {}

    def rate(self, key: str, counter: float, now: float) -> float | None:
        prev = self._prev.get(key)
        self._prev[key] = (counter, now)
        if prev is None:
            return None
        delta, elapsed = counter - prev[0], now - prev[1]
        if elapsed <= 0 or delta < 0:      # counter reset / wrapped / clock oddity
            return None
        return delta / elapsed

    def delta(self, key: str, counter: float) -> float | None:
        """Plain difference since the previous tick (used for /proc/stat jiffies)."""
        prev = self._prev.get(key)
        self._prev[key] = (counter, 0.0)
        if prev is None:
            return None
        d = counter - prev[0]
        return d if d >= 0 else None
