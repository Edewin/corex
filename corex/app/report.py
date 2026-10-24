"""System report: every device and value as plain text, ready to paste on a forum."""

from __future__ import annotations

import os
import time

from corex import __version__
from corex.core.model import Kind, Snapshot
from corex.core.units import format_value


def _os_name() -> str:
    # inside Flatpak the host's os-release is mounted under /run/host
    for path in ("/run/host/os-release", "/etc/os-release"):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            continue
    return "Linux"


def _uptime() -> str:
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            seconds = int(float(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return ""
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    return (f"{days} d " if days else "") + f"{hours} h {rest // 60} min"


def build(snap: Snapshot) -> str:
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(snap.timestamp or time.time()))
    lines = [f"CoreX {__version__} system report · {stamp}",
             f"System: {_os_name()} · Linux {os.uname().release}"]
    up = _uptime()
    if up:
        lines.append(f"Uptime: {up}")
    width = max((len(r.label) for r in snap.readings()), default=10) + 2
    for d in snap.devices:
        lines += ["", f"== {d.name}" + (f" ({d.detail})" if d.detail else "") + " =="]
        for g in d.groups:
            lines.append(g.name)
            for r in g.readings:
                value = format_value(r.kind, r.value, r.text)
                line = f"  {r.label.ljust(width)}{value:>12}"
                if r.kind != Kind.INFO and r.min is not None and r.max is not None:
                    line += f"   (min {format_value(r.kind, r.min)}, max {format_value(r.kind, r.max)})"
                lines.append(line)
    return "\n".join(lines) + "\n"
