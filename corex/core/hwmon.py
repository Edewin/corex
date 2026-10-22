"""
Reads every chip under /sys/class/hwmon.

This is the same kernel interface lm-sensors reads, so no `sensors`
binary is needed (only the kernel drivers, which `sensors-detect` loads).

Each chip is "claimed" by the source it belongs to (CPU temperatures by
the CPU source, nvme/drivetemp by the storage source, amdgpu by the GPU
source); whatever is left becomes its own device (motherboard, ACPI, ...).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from corex.core.model import Group, Kind, Reading
from corex.core.sysfs import Roots, list_dir, read_int, read_text, real

_CHANNEL = re.compile(r"^(temp|fan|in|power|curr)(\d+)_(input|average|label)$")

# kind, group name, divisor to base unit, label prefix when the kernel gives none
_TYPES = {
    "temp":  (Kind.TEMP, "Temperatures", 1000.0, "Temperature"),
    "fan":   (Kind.FAN, "Fans", 1.0, "Fan"),
    "in":    (Kind.VOLT, "Voltages", 1000.0, "Voltage"),
    "power": (Kind.POWER, "Power", 1_000_000.0, "Power"),
    "curr":  (Kind.CURRENT, "Currents", 1000.0, "Current"),
}
_GROUP_ORDER = ("Temperatures", "Fans", "Power", "Voltages", "Currents")

# Kernel labels that are cryptic; anything not listed is shown as given.
_LABELS = {
    "Tctl": "CPU (Tctl)",
    "Tdie": "CPU (Tdie)",
    "PPT": "Package Power",
    "edge": "Edge",
    "junction": "Hotspot",
    "mem": "Memory",
    "vddgfx": "GFX Voltage",
    "vddnb": "SoC Voltage",
    "Composite": "Composite",
}


def _nice_label(raw: str) -> str:
    if raw in _LABELS:
        return _LABELS[raw]
    m = re.fullmatch(r"Tccd(\d+)", raw)
    if m:
        return f"CCD {m.group(1)}"
    m = re.fullmatch(r"Package id (\d+)", raw)
    if m:
        return "Package" if m.group(1) == "0" else f"Package {m.group(1)}"
    return raw


@dataclass
class HwmonChip:
    name: str                 # driver name: "k10temp", "nct6798", "amdgpu", ...
    id: str                   # stable id, independent of the hwmonN number
    device: str | None        # resolved path of the parent device, for matching
    groups: list[Group] = field(default_factory=list)

    def readings(self, kind: str | None = None) -> list[Reading]:
        return [r for g in self.groups for r in g.readings if kind is None or r.kind == kind]


def read_chips(roots: Roots) -> list[HwmonChip]:
    base = roots.s("class", "hwmon")
    chips = []
    seen_ids: set[str] = set()
    for entry in list_dir(base):
        path = os.path.join(base, entry)
        name = read_text(os.path.join(path, "name")) or entry
        device = real(os.path.join(path, "device"))
        chip_id = f"hwmon/{name}" + (f"@{os.path.basename(device)}" if device else f"@{entry}")
        if chip_id in seen_ids:           # same driver twice on one device (rare)
            chip_id = f"{chip_id}#{entry}"
        seen_ids.add(chip_id)
        chips.append(HwmonChip(name, chip_id, device, _read_groups(path, chip_id)))
    return chips


def _read_groups(path: str, chip_id: str) -> list[Group]:
    channels: dict[tuple[str, int], dict[str, str]] = {}
    for fname in list_dir(path):
        m = _CHANNEL.match(fname)
        if m:
            channels.setdefault((m.group(1), int(m.group(2))), {})[m.group(3)] = fname

    grouped: dict[str, list[Reading]] = {}
    for (ctype, num), files in sorted(channels.items()):
        kind, group, divisor, prefix = _TYPES[ctype]
        value_file = files.get("input") or files.get("average")
        if value_file is None:
            continue
        raw = read_int(os.path.join(path, value_file))
        if raw is None:
            continue                      # channel exists but cannot be read
        value = raw / divisor
        if kind == Kind.TEMP and not -60.0 < value < 250.0:
            continue                      # disconnected thermistor (-128, 255, ...)
        raw_label = read_text(os.path.join(path, files["label"])) if "label" in files else None
        label = _nice_label(raw_label) if raw_label else f"{prefix} {num}"
        grouped.setdefault(group, []).append(
            Reading(id=f"{chip_id}/{ctype}{num}", label=label, kind=kind, value=value)
        )
    return [Group(g, tuple(grouped[g])) for g in _GROUP_ORDER if g in grouped]


class HwmonPool:
    """The chips read this tick; sources take the ones that belong to them."""

    def __init__(self, chips: list[HwmonChip]):
        self._chips = list(chips)

    def take_by_name(self, *names: str) -> list[HwmonChip]:
        found = [c for c in self._chips if c.name in names]
        for c in found:
            self._chips.remove(c)
        return found

    def take_by_device(self, device_path: str | None) -> list[HwmonChip]:
        """
        Chips attached to `device_path` or to one of its ancestors.

        An NVMe drive's hwmon hangs off the controller (.../nvme/nvme0) while
        the disk is .../nvme/nvme0/nvme0n1; a SATA drive's drivetemp hangs off
        the SCSI device above .../block/sda; an amdgpu hwmon is on the PCI
        device itself.
        """
        if not device_path:
            return []
        found = [
            c for c in self._chips
            if c.device and (device_path == c.device or device_path.startswith(c.device + os.sep))
        ]
        for c in found:
            self._chips.remove(c)
        return found

    def remaining(self) -> list[HwmonChip]:
        return list(self._chips)
