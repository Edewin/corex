"""RAM and swap from /proc/meminfo."""

from __future__ import annotations

from corex.core.model import Device, DeviceKind, Group, Kind, Reading
from corex.core.sysfs import Roots, read_text
from corex.core.units import human_bytes


def _parse_meminfo(text: str) -> dict[str, int]:
    """Values in bytes."""
    out = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            factor = 1024 if len(parts) > 1 and parts[1] == "kB" else 1
            out[key.strip()] = int(parts[0]) * factor
    return out


class MemorySource:
    def __init__(self, roots: Roots):
        self.roots = roots

    def sample(self, now: float, pool) -> list[Device]:
        info = _parse_meminfo(read_text(self.roots.p("meminfo")) or "")
        total = info.get("MemTotal")
        if not total:
            return []
        available = info.get("MemAvailable", info.get("MemFree", 0))
        used = total - available
        ram = [
            Reading("mem/ram/load", "Load", Kind.LOAD, 100.0 * used / total),
            Reading("mem/ram/used", "Used", Kind.DATA, used),
            Reading("mem/ram/available", "Available", Kind.DATA, available),
            Reading("mem/ram/total", "Total", Kind.DATA, total),
        ]
        groups = [Group("RAM", tuple(ram))]

        swap_total = info.get("SwapTotal", 0)
        if swap_total:
            swap_used = swap_total - info.get("SwapFree", 0)
            groups.append(Group("Swap", (
                Reading("mem/swap/load", "Load", Kind.LOAD, 100.0 * swap_used / swap_total),
                Reading("mem/swap/used", "Used", Kind.DATA, swap_used),
                Reading("mem/swap/total", "Total", Kind.DATA, swap_total),
            )))
        return [Device("memory", "Memory", DeviceKind.MEMORY, human_bytes(total)).with_groups(groups)]
