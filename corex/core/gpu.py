"""
Graphics cards.

* NVIDIA through NVML (nvidia-ml-py), initialised once for the whole run.
* AMD (amdgpu) and Intel through /sys/class/drm, with temperatures, fan
  and power from the card's hwmon chip.
"""

from __future__ import annotations

import os
import re

from corex.core.hwmon import HwmonPool
from corex.core.model import Device, DeviceKind, Group, Kind, Reading
from corex.core.sysfs import Roots, list_dir, read_int, read_text, real

_VENDORS = {"0x1002": "AMD", "0x8086": "Intel", "0x10de": "NVIDIA"}
_PCI_IDS = ("/usr/share/hwdata/pci.ids", "/usr/share/misc/pci.ids", "/usr/share/pci.ids")


def pci_device_name(vendor: str, device: str, paths=_PCI_IDS) -> str | None:
    """Marketing name from pci.ids: ('0x1002', '0x73bf') -> 'Radeon RX 6800/6800 XT / 6900 XT'."""
    v, d = vendor.lower().removeprefix("0x"), device.lower().removeprefix("0x")
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                in_vendor = False
                for line in f:
                    if not line.strip() or line.startswith("#"):
                        continue
                    if not line.startswith("\t"):
                        if in_vendor:
                            return None           # left the vendor block without a match
                        in_vendor = line[:4].lower() == v
                    elif in_vendor and not line.startswith("\t\t") and line[1:5].lower() == d:
                        name = line[5:].strip()
                        m = re.search(r"\[(.+)\]", name)
                        return m.group(1) if m else name
        except OSError:
            continue
    return None


class _Nvml:
    """Lazy NVML wrapper; every query is optional because consumer cards hide some."""

    def __init__(self):
        self.ok = False
        self.nv = None
        try:
            import pynvml as nv
            nv.nvmlInit()
            self.nv = nv
            self.handles = [nv.nvmlDeviceGetHandleByIndex(i) for i in range(nv.nvmlDeviceGetCount())]
            self.ok = True
        except Exception:                 # library missing, no driver, no GPU
            self.handles = []

    def _q(self, fn, *args):
        try:
            return fn(*args)
        except Exception:
            return None

    def devices(self) -> list[Device]:
        nv, out = self.nv, []
        for i, h in enumerate(self.handles):
            name = self._q(nv.nvmlDeviceGetName, h) or f"NVIDIA GPU {i}"
            if isinstance(name, bytes):
                name = name.decode()
            name = name.removeprefix("NVIDIA ").strip()
            p = f"gpu/nv{i}"
            temp = self._q(nv.nvmlDeviceGetTemperature, h, nv.NVML_TEMPERATURE_GPU)
            util = self._q(nv.nvmlDeviceGetUtilizationRates, h)
            mem = self._q(nv.nvmlDeviceGetMemoryInfo, h)
            power = self._q(nv.nvmlDeviceGetPowerUsage, h)
            limit = self._q(nv.nvmlDeviceGetEnforcedPowerLimit, h)
            fan = self._q(nv.nvmlDeviceGetFanSpeed, h)
            gclk = self._q(nv.nvmlDeviceGetClockInfo, h, nv.NVML_CLOCK_GRAPHICS)
            mclk = self._q(nv.nvmlDeviceGetClockInfo, h, nv.NVML_CLOCK_MEM)

            groups = []
            if temp is not None:
                groups.append(Group("Temperatures", (Reading(f"{p}/temp", "GPU", Kind.TEMP, float(temp)),)))
            load = []
            if util is not None:
                load.append(Reading(f"{p}/load", "GPU", Kind.LOAD, float(util.gpu)))
                load.append(Reading(f"{p}/load_mem_ctrl", "Memory controller", Kind.LOAD, float(util.memory)))
            if mem is not None and mem.total:
                load.append(Reading(f"{p}/vram_load", "VRAM", Kind.LOAD, 100.0 * mem.used / mem.total))
            groups.append(Group("Load", tuple(load)))
            if mem is not None:
                groups.append(Group("Memory", (
                    Reading(f"{p}/vram_used", "VRAM used", Kind.DATA, float(mem.used)),
                    Reading(f"{p}/vram_total", "VRAM total", Kind.DATA, float(mem.total)),
                )))
            pw = []
            if power is not None:
                pw.append(Reading(f"{p}/power", "Board power", Kind.POWER, power / 1000.0))
            if limit:
                pw.append(Reading(f"{p}/power_limit", "Power limit", Kind.POWER, limit / 1000.0))
            groups.append(Group("Power", tuple(pw)))
            clocks = []
            if gclk:
                clocks.append(Reading(f"{p}/clock_core", "Core", Kind.CLOCK, float(gclk)))
            if mclk:
                clocks.append(Reading(f"{p}/clock_mem", "Memory", Kind.CLOCK, float(mclk)))
            groups.append(Group("Clocks", tuple(clocks)))
            if fan is not None:
                groups.append(Group("Fans", (Reading(f"{p}/fan", "Fan", Kind.FAN_PCT, float(fan)),)))
            out.append(Device(p, name, DeviceKind.GPU, "NVIDIA · NVML").with_groups(groups))
        return out

    def close(self):
        if self.ok:
            self._q(self.nv.nvmlShutdown)
            self.ok = False


def _current_dpm_mhz(path: str) -> float | None:
    """amdgpu pp_dpm_sclk: the line ending in '*' is the active level ('1: 2400Mhz *')."""
    for line in (read_text(path) or "").splitlines():
        if line.rstrip().endswith("*"):
            m = re.search(r"(\d+)\s*Mhz", line, re.IGNORECASE)
            if m:
                return float(m.group(1))
    return None


class GpuSource:
    def __init__(self, roots: Roots, use_nvml: bool = True, pci_ids=_PCI_IDS):
        self.roots = roots
        self.pci_ids = pci_ids
        self.nvml = _Nvml() if use_nvml else None
        self._names: dict[str, str] = {}

    @property
    def nvml_ok(self) -> bool:
        return bool(self.nvml and self.nvml.ok)

    def close(self):
        if self.nvml:
            self.nvml.close()

    def sample(self, now: float, pool: HwmonPool) -> list[Device]:
        devices = self.nvml.devices() if self.nvml_ok else []
        base = self.roots.s("class", "drm")
        for card in list_dir(base):
            if not re.fullmatch(r"card\d+", card):
                continue
            dev = os.path.join(base, card, "device")
            vendor = read_text(os.path.join(dev, "vendor"))
            if vendor not in _VENDORS or (vendor == "0x10de" and self.nvml_ok):
                continue
            devices.append(self._sysfs_card(card, dev, vendor, pool))
        return devices

    def _name(self, card: str, dev: str, vendor: str) -> str:
        if card not in self._names:
            device_id = read_text(os.path.join(dev, "device")) or ""
            nice = pci_device_name(vendor, device_id, self.pci_ids)
            self._names[card] = nice or f"{_VENDORS[vendor]} GPU"
        return self._names[card]

    def _sysfs_card(self, card: str, dev: str, vendor: str, pool: HwmonPool) -> Device:
        p = f"gpu/{card}"
        chips = pool.take_by_device(real(dev))
        groups = []
        hw = [r for c in chips for r in c.readings()]
        temps = [r for r in hw if r.kind == Kind.TEMP]
        if temps:
            groups.append(Group("Temperatures", tuple(temps)))

        load = []
        busy = read_int(os.path.join(dev, "gpu_busy_percent"))
        if busy is not None:
            load.append(Reading(f"{p}/load", "GPU", Kind.LOAD, float(busy)))
        used = read_int(os.path.join(dev, "mem_info_vram_used"))
        total = read_int(os.path.join(dev, "mem_info_vram_total"))
        if used is not None and total:
            load.append(Reading(f"{p}/vram_load", "VRAM", Kind.LOAD, 100.0 * used / total))
        groups.append(Group("Load", tuple(load)))
        if used is not None and total:
            groups.append(Group("Memory", (
                Reading(f"{p}/vram_used", "VRAM used", Kind.DATA, float(used)),
                Reading(f"{p}/vram_total", "VRAM total", Kind.DATA, float(total)),
            )))
        groups.append(Group("Power", tuple(r for r in hw if r.kind == Kind.POWER)))

        clocks = []
        sclk = _current_dpm_mhz(os.path.join(dev, "pp_dpm_sclk"))
        mclk = _current_dpm_mhz(os.path.join(dev, "pp_dpm_mclk"))
        if sclk is None:                                     # Intel i915
            i915 = read_int(os.path.join(base_card(dev), "gt_cur_freq_mhz"))
            sclk = float(i915) if i915 else None
        if sclk:
            clocks.append(Reading(f"{p}/clock_core", "Core", Kind.CLOCK, sclk))
        if mclk:
            clocks.append(Reading(f"{p}/clock_mem", "Memory", Kind.CLOCK, mclk))
        groups.append(Group("Clocks", tuple(clocks)))
        groups.append(Group("Fans", tuple(r for r in hw if r.kind == Kind.FAN)))
        groups.append(Group("Voltages", tuple(r for r in hw if r.kind == Kind.VOLT)))

        return Device(p, self._name(card, dev, vendor), DeviceKind.GPU,
                      f"{_VENDORS[vendor]} · {card}").with_groups(groups)


def base_card(dev: str) -> str:
    """/sys/class/drm/card0/device -> /sys/class/drm/card0"""
    return os.path.dirname(dev)
