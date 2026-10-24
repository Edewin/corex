"""Alerts: a threshold above and / or below on any reading, told through a desktop notification."""

from __future__ import annotations

import time

from corex.core.model import Kind, Snapshot
from corex.core.units import format_value

REPEAT_S = 300       # the same alert is told again at most every 5 minutes

# unit shown in the alert dialog and its factor from the base unit
_UNITS = {Kind.RATE: ("MB/s", 1e6), Kind.DATA: ("GB", 1e9)}


def dialog_unit(kind: str) -> tuple[str, float]:
    from corex.core.model import UNITS
    return _UNITS.get(kind, (UNITS.get(kind, ""), 1.0))


def broken(rule: dict, value: float | None) -> str | None:
    """'above' / 'below' when the value is past the rule, else None."""
    if value is None:
        return None
    above, below = rule.get("above"), rule.get("below")
    if above is not None and value > above:
        return "above"
    if below is not None and value < below:
        return "below"
    return None


class AlertWatcher:
    def __init__(self):
        self._told: dict[str, float] = {}

    def check(self, snap: Snapshot, rules: dict[str, dict], now: float | None = None):
        """Returns (ids over their threshold now, [(title, body) to tell])."""
        now = time.monotonic() if now is None else now
        over, tell = set(), []
        for rid, rule in rules.items():
            dev = next((d for d in snap.devices if d.reading(rid)), None)
            r = dev.reading(rid) if dev else None
            side = broken(rule, r.value if r else None)
            if side is None:
                continue
            over.add(rid)
            if now - self._told.get(rid, -1e9) >= REPEAT_S:
                self._told[rid] = now
                limit = format_value(r.kind, rule[side])
                tell.append((f"{dev.name} · {r.label}: {format_value(r.kind, r.value)}",
                             f"{'Above' if side == 'above' else 'Below'} your alert of {limit}"))
        return over, tell


def notify(title: str, body: str, tray=None) -> bool:
    """Desktop notification over D-Bus; the tray balloon when D-Bus cannot be reached."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            iface = QDBusInterface("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                                   "org.freedesktop.Notifications", bus)
            if iface.isValid():
                reply = iface.call("Notify", "CoreX", 0, "io.github.edewin.corex", title, body,
                                   [], {}, 8000)
                if not reply.errorName():
                    return True
    except Exception:            # no QtDBus in this build: fall back to the tray
        pass
    if tray is not None:
        tray.showMessage(title, body)
        return True
    return False
