"""Runs the engine on a worker thread at a fixed rhythm."""

from __future__ import annotations

import threading
import time
import traceback
from collections import deque

from PySide6.QtCore import QThread, Signal

from corex.core.engine import Engine
from corex.core.model import Snapshot


class Poller(QThread):
    snapshot = Signal(object)          # Snapshot
    failed = Signal(str)

    def __init__(self, engine: Engine, interval_s: float = 1.0, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._interval = interval_s
        self._stop = threading.Event()
        self._wake = threading.Event()

    def set_interval(self, seconds: float) -> None:
        self._interval = seconds
        self._wake.set()               # apply now, do not wait for the old interval

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.wait(3000)

    def run(self) -> None:
        next_at = time.monotonic()
        while not self._stop.is_set():
            try:
                snap = self.engine.sample()
                self.snapshot.emit(snap)
            except Exception:          # a broken sensor must not kill the thread
                self.failed.emit(traceback.format_exc(limit=3))
            next_at += self._interval
            delay = next_at - time.monotonic()
            if delay < 0:              # fell behind (suspend, slow disk): restart the rhythm
                next_at, delay = time.monotonic(), 0
            self._wake.wait(delay)
            if self._wake.is_set():
                self._wake.clear()
                next_at = time.monotonic()
        self.engine.close()


class History:
    """Last N values of every numeric reading, fed from the GUI thread."""

    def __init__(self, length: int = 300):
        self.length = length
        self._data: dict[str, deque] = {}
        self.latest: Snapshot | None = None

    def add(self, snap: Snapshot) -> None:
        self.latest = snap
        for r in snap.readings():
            if r.value is not None:
                self._data.setdefault(r.id, deque(maxlen=self.length)).append(r.value)

    def values(self, reading_id: str) -> list[float]:
        return list(self._data.get(reading_id, ()))

    def clear(self) -> None:
        self._data.clear()
