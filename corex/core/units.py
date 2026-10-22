"""Formatting of reading values for display."""

from __future__ import annotations

from corex.core.model import Kind, Reading

_BYTE_STEPS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_bytes(value: float, per_second: bool = False) -> str:
    """1536 -> '1.5 KB'. Uses binary steps (1024) like most Linux tools."""
    v = float(value)
    step = 0
    while abs(v) >= 1024 and step < len(_BYTE_STEPS) - 1:
        v /= 1024
        step += 1
    unit = _BYTE_STEPS[step] + ("/s" if per_second else "")
    if step == 0:
        return f"{v:.0f} {unit}"
    return f"{v:.1f} {unit}" if v < 100 else f"{v:.0f} {unit}"


def format_value(kind: str, value: float | None, text: str | None = None) -> str:
    if kind == Kind.INFO:
        return text or "—"
    if value is None:
        return "—"
    if kind == Kind.RATE:
        return human_bytes(value, per_second=True)
    if kind == Kind.DATA:
        return human_bytes(value)
    if kind == Kind.TEMP:
        return f"{value:.0f} °C"
    if kind in (Kind.LOAD, Kind.FAN_PCT):
        return f"{value:.0f} %"
    if kind == Kind.FAN:
        return f"{value:.0f} RPM"
    if kind == Kind.CLOCK:
        return f"{value / 1000:.2f} GHz" if value >= 1000 else f"{value:.0f} MHz"
    if kind == Kind.VOLT:
        return f"{value:.3f} V"
    if kind == Kind.CURRENT:
        return f"{value:.2f} A"
    if kind == Kind.POWER:
        return f"{value:.1f} W" if value < 100 else f"{value:.0f} W"
    return f"{value:g}"


def format_reading(r: Reading) -> str:
    return format_value(r.kind, r.value, r.text)
