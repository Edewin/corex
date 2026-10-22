"""CPU: name, load per thread, clocks, temperatures (from hwmon)."""

from __future__ import annotations

import re

from corex.core.hwmon import HwmonPool
from corex.core.model import Device, DeviceKind, Group, Kind, Reading
from corex.core.rates import RateTracker
from corex.core.sysfs import Roots, list_dir, read_int, read_text

CPU_TEMP_DRIVERS = ("k10temp", "coretemp", "zenpower")


def clean_cpu_name(model: str) -> str:
    """'Intel(R) Core(TM) i7-12700K CPU @ 3.60GHz' -> 'Intel Core i7-12700K'."""
    name = re.sub(r"\((R|TM|tm|r)\)", "", model)
    name = re.sub(r"\s*CPU\s*@\s*[\d.]+\s*GHz", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+\d+-Core Processor$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+Processor$", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip() or "CPU"


def _parse_cpuinfo(text: str) -> tuple[str, dict[int, float]]:
    """Model name and the 'cpu MHz' line of each logical CPU."""
    model, mhz, current = "CPU", {}, None
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "processor":
            current = int(value) if value.isdigit() else None
        elif key == "model name" and model == "CPU":
            model = value
        elif key == "cpu MHz" and current is not None:
            try:
                mhz[current] = float(value)
            except ValueError:
                pass
    return clean_cpu_name(model), mhz


def _parse_stat(text: str) -> dict[str, tuple[int, int]]:
    """{'cpu': (busy, total), 'cpu0': ...} in jiffies."""
    out = {}
    for line in text.splitlines():
        if not line.startswith("cpu"):
            break
        parts = line.split()
        nums = [int(x) for x in parts[1:]]
        nums += [0] * (10 - len(nums))
        user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice = nums[:10]
        # guest time is already counted inside user/nice
        total = user + nice + system + idle + iowait + irq + softirq + steal
        out[parts[0]] = (total - idle - iowait, total)
    return out


class CpuSource:
    def __init__(self, roots: Roots):
        self.roots = roots
        self.rates = RateTracker()
        self.name, _ = _parse_cpuinfo(read_text(roots.p("cpuinfo")) or "")

    def sample(self, now: float, pool: HwmonPool) -> list[Device]:
        groups: list[Group] = []

        temps = [r for chip in pool.take_by_name(*CPU_TEMP_DRIVERS) for g in chip.groups for r in g.readings]
        if temps:
            temp_r = [r for r in temps if r.kind == Kind.TEMP]
            other = [r for r in temps if r.kind != Kind.TEMP]
            groups.append(Group("Temperatures", tuple(temp_r)))
            if other:
                groups.append(Group("Power", tuple(other)))

        groups.append(Group("Load", tuple(self._load())))
        groups.append(Group("Clocks", tuple(self._clocks())))
        return [Device("cpu", self.name, DeviceKind.CPU, self._detail()).with_groups(groups)]

    def _load(self) -> list[Reading]:
        stat = _parse_stat(read_text(self.roots.p("stat")) or "")
        readings = []
        for key in sorted(stat, key=lambda k: -1 if k == "cpu" else int(k[3:])):
            busy, total = stat[key]
            d_busy = self.rates.delta(f"{key}/busy", busy)
            d_total = self.rates.delta(f"{key}/total", total)
            value = None
            if d_busy is not None and d_total:
                value = max(0.0, min(100.0, 100.0 * d_busy / d_total))
            if key == "cpu":
                readings.append(Reading("cpu/load/total", "Total", Kind.LOAD, value))
            else:
                n = key[3:]
                readings.append(Reading(f"cpu/load/{n}", f"Thread {n}", Kind.LOAD, value))
        return readings

    def _clocks(self) -> list[Reading]:
        base = self.roots.s("devices", "system", "cpu")
        mhz: dict[int, float] = {}
        for entry in list_dir(base):
            if re.fullmatch(r"cpu\d+", entry):
                khz = read_int(f"{base}/{entry}/cpufreq/scaling_cur_freq")
                if khz:
                    mhz[int(entry[3:])] = khz / 1000.0
        if not mhz:                                   # VMs / WSL: no cpufreq
            _, mhz = _parse_cpuinfo(read_text(self.roots.p("cpuinfo")) or "")
        if not mhz:
            return []
        values = [mhz[k] for k in sorted(mhz)]
        out = [
            Reading("cpu/clock/max", "Highest", Kind.CLOCK, max(values)),
            Reading("cpu/clock/avg", "Average", Kind.CLOCK, sum(values) / len(values)),
        ]
        out += [Reading(f"cpu/clock/{k}", f"Thread {k}", Kind.CLOCK, mhz[k]) for k in sorted(mhz)]
        return out

    def _detail(self) -> str:
        text = read_text(self.roots.p("cpuinfo")) or ""
        threads = sum(1 for line in text.splitlines() if line.startswith("processor"))
        cores = set()
        phys = core = None
        for line in text.splitlines():
            key, _, value = line.partition(":")
            key = key.strip()
            if key == "physical id":
                phys = value.strip()
            elif key == "core id":
                core = value.strip()
                cores.add((phys, core))
        if cores and threads and len(cores) != threads:
            return f"{len(cores)} cores · {threads} threads"
        return f"{threads} threads" if threads else ""
