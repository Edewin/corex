"""
The sensor engine: one call to sample() reads every source once and
returns a new, immutable Snapshot. No sleeping inside: rates come from
the time between two calls.
"""

from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import replace

from corex.core.cpu import CpuSource
from corex.core.gpu import GpuSource
from corex.core.hwmon import HwmonChip, HwmonPool, read_chips
from corex.core.memory import MemorySource
from corex.core.model import Device, DeviceKind, Group, Kind, Snapshot
from corex.core.network import NetworkSource
from corex.core.storage import StorageSource
from corex.core.sysfs import Roots, read_text

RAM_TEMP_DRIVERS = ("jc42", "spd5118")

# Leftover hwmon chips: driver pattern -> device kind
_BOARD_CHIPS = ("nct6*", "it8*", "it87*", "w83*", "f71*", "asus*", "gigabyte_wmi", "dell_smm", "thinkpad",
                "nzxt*", "corsair*", "aquacomputer*", "applesmc")
_SYSTEM_NAMES = {"acpitz": "ACPI thermal zone", "pch_*": "Chipset (PCH)"}


class Engine:
    def __init__(self, roots: Roots | None = None, use_nvml: bool = True, labels: dict[str, str] | None = None,
                 **source_kwargs):
        self.roots = roots or Roots()
        self.cpu = CpuSource(self.roots)
        self.gpu = GpuSource(self.roots, use_nvml=use_nvml, **source_kwargs.get("gpu", {}))
        self.memory = MemorySource(self.roots)
        self.storage = StorageSource(self.roots, **source_kwargs.get("storage", {}))
        self.network = NetworkSource(self.roots, **source_kwargs.get("network", {}))
        self.labels = dict(labels or {})        # user renames: reading id -> label
        self._minmax: dict[str, tuple[float, float]] = {}
        self._board = self._board_name()

    # ------------------------------------------------------------------
    def sample(self, now: float | None = None) -> Snapshot:
        now = time.monotonic() if now is None else now
        chips = read_chips(self.roots)
        pool = HwmonPool(chips)

        devices: list[Device] = []
        devices += self.cpu.sample(now, pool)
        devices += self.gpu.sample(now, pool)
        mem = self.memory.sample(now, pool)
        ram_temps = [r for c in pool.take_by_name(*RAM_TEMP_DRIVERS) for r in c.readings(Kind.TEMP)]
        if mem and ram_temps:
            mem[0] = mem[0].with_groups((Group("Temperatures", tuple(ram_temps)),) + mem[0].groups)
        devices += mem
        devices += self.storage.sample(now, pool)
        devices += self.network.sample(now, pool)
        devices += self._leftovers(pool.remaining())

        devices = [self._finish(d) for d in devices]
        status = {"hwmon": bool(chips), "nvml": self.gpu.nvml_ok}
        return Snapshot(tuple(d for d in devices if d.groups), time.time(), status)

    def reset_minmax(self) -> None:
        self._minmax.clear()

    def close(self) -> None:
        self.gpu.close()

    # ------------------------------------------------------------------
    def _finish(self, device: Device) -> Device:
        """Apply user labels and session min/max to every reading."""
        groups = []
        for g in device.groups:
            readings = []
            for r in g.readings:
                label = self.labels.get(r.id, r.label)
                if r.value is None:
                    lo_hi = self._minmax.get(r.id)
                else:
                    lo, hi = self._minmax.get(r.id, (r.value, r.value))
                    lo_hi = (min(lo, r.value), max(hi, r.value))
                    self._minmax[r.id] = lo_hi
                readings.append(replace(r, label=label, min=lo_hi[0] if lo_hi else None,
                                        max=lo_hi[1] if lo_hi else None))
            groups.append(Group(g.name, tuple(readings)))
        return device.with_groups(groups)

    def _leftovers(self, chips: list[HwmonChip]) -> list[Device]:
        out = []
        for chip in chips:
            if not chip.groups:
                continue
            if any(fnmatch.fnmatch(chip.name, pat) for pat in _BOARD_CHIPS):
                out.append(Device(chip.id, self._board or "Motherboard", DeviceKind.BOARD, chip.name,
                                  tuple(chip.groups)))
                continue
            name = next((n for pat, n in _SYSTEM_NAMES.items() if fnmatch.fnmatch(chip.name, pat)), chip.name)
            out.append(Device(chip.id, name, DeviceKind.SYSTEM, chip.name, tuple(chip.groups)))
        return out

    def _board_name(self) -> str | None:
        dmi = self.roots.s("class", "dmi", "id")
        vendor = read_text(os.path.join(dmi, "board_vendor")) or ""
        name = read_text(os.path.join(dmi, "board_name")) or ""
        junk = {"", "Default string", "To be filled by O.E.M.", "System Product Name"}
        if name in junk:
            return None
        for long, short in (("ASUSTeK COMPUTER INC.", "ASUS"), ("Micro-Star International Co., Ltd.", "MSI"),
                            ("Gigabyte Technology Co., Ltd.", "Gigabyte"), ("ASRock", "ASRock")):
            if vendor.startswith(long):
                vendor = short
        return f"{vendor} {name}".strip() if vendor not in junk else name


__all__ = ["Engine", "DeviceKind"]
