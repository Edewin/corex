"""
Immutable data model shared by the sensor engine and the UI.

The engine builds a fresh Snapshot on every tick and hands it to the UI
thread; nothing in a Snapshot is mutated afterwards, so it can be read
from any thread without locking.

Values are stored in base units (B, B/s, MHz, °C, RPM, V, W, A, %);
formatting for display lives in corex.core.units.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


class Kind:
    """Reading kinds; they decide units, colours and chart grouping."""
    TEMP = "temp"        # °C
    FAN = "fan"          # RPM
    FAN_PCT = "fan_pct"  # % (GPU fans report duty, not RPM)
    VOLT = "volt"        # V
    CURRENT = "current"  # A
    POWER = "power"      # W
    LOAD = "load"        # %
    CLOCK = "clock"      # MHz
    DATA = "data"        # bytes
    RATE = "rate"        # bytes per second
    INFO = "info"        # text only (IP address, link state, ...)


UNITS = {
    Kind.TEMP: "°C",
    Kind.FAN: "RPM",
    Kind.FAN_PCT: "%",
    Kind.VOLT: "V",
    Kind.CURRENT: "A",
    Kind.POWER: "W",
    Kind.LOAD: "%",
    Kind.CLOCK: "MHz",
    Kind.DATA: "B",
    Kind.RATE: "B/s",
    Kind.INFO: "",
}


class DeviceKind:
    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    BOARD = "board"
    BATTERY = "battery"
    SYSTEM = "system"


@dataclass(frozen=True)
class Reading:
    id: str                      # stable across runs, e.g. "cpu/load/total"
    label: str
    kind: str
    value: float | None = None   # None = not available this tick
    text: str | None = None      # for Kind.INFO
    min: float | None = None     # session minimum, filled in by the engine
    max: float | None = None     # session maximum, filled in by the engine

    @property
    def unit(self) -> str:
        return UNITS[self.kind]


@dataclass(frozen=True)
class Group:
    name: str
    readings: tuple[Reading, ...] = ()


@dataclass(frozen=True)
class Device:
    id: str                      # e.g. "cpu", "disk/nvme0n1", "net/eth0"
    name: str                    # "AMD Ryzen 5 5600"
    kind: str                    # DeviceKind
    detail: str = ""             # "NVMe SSD · 1 TB", "Wi-Fi · 866 Mbit/s"
    groups: tuple[Group, ...] = ()

    def reading(self, reading_id: str) -> Reading | None:
        for g in self.groups:
            for r in g.readings:
                if r.id == reading_id:
                    return r
        return None

    def with_groups(self, groups) -> Device:
        return replace(self, groups=tuple(g for g in groups if g.readings))


@dataclass(frozen=True)
class Snapshot:
    devices: tuple[Device, ...] = ()
    timestamp: float = 0.0       # wall clock, for display
    status: dict = field(default_factory=dict)   # backend name -> available

    def device(self, device_id: str) -> Device | None:
        for d in self.devices:
            if d.id == device_id:
                return d
        return None

    def reading(self, reading_id: str) -> Reading | None:
        for d in self.devices:
            r = d.reading(reading_id)
            if r is not None:
                return r
        return None

    def readings(self):
        for d in self.devices:
            for g in d.groups:
                yield from g.readings
