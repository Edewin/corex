"""
Network interfaces: traffic from /proc/net/dev (rates from the real time
between ticks), link state and speed from sysfs, IPv4 address, Wi-Fi
signal and SSID. Only physical interfaces are shown (not lo, docker,
bridges, veth, VPN tunnels) so traffic is not counted twice.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess

from corex.core.model import Device, DeviceKind, Group, Kind, Reading
from corex.core.rates import RateTracker
from corex.core.sysfs import Roots, list_dir, read_int, read_text, real

_SLOW_REFRESH_S = 10.0     # IP address / SSID do not change every second


def _ipv4_addresses() -> dict[str, str]:
    try:
        import psutil
    except ImportError:
        return {}
    out = {}
    for iface, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET:
                out[iface] = a.address
                break
    return out


def _ssid(iface: str) -> str | None:
    if not shutil.which("iw"):
        return None
    try:
        res = subprocess.run(["iw", "dev", iface, "link"], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in res.stdout.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            return line[5:].strip()
    return None


class NetworkSource:
    def __init__(self, roots: Roots, ipv4=_ipv4_addresses, ssid=_ssid):
        self.roots = roots
        self.rates = RateTracker()
        self._ipv4_fn, self._ssid_fn = ipv4, ssid
        self._slow_at = -1e9
        self._ipv4: dict[str, str] = {}
        self._ssids: dict[str, str | None] = {}

    def _interfaces(self) -> list[str]:
        base = self.roots.s("class", "net")
        return [i for i in list_dir(base) if i != "lo" and os.path.exists(os.path.join(base, i, "device"))]

    def _is_wifi(self, iface: str) -> bool:
        base = self.roots.s("class", "net", iface)
        return os.path.isdir(os.path.join(base, "wireless")) or os.path.exists(os.path.join(base, "phy80211"))

    def _counters(self) -> dict[str, tuple[int, int]]:
        out = {}
        for line in (read_text(self.roots.p("net", "dev")) or "").splitlines()[2:]:
            name, _, rest = line.partition(":")
            f = rest.split()
            if len(f) >= 9:
                out[name.strip()] = (int(f[0]), int(f[8]))
        return out

    def _signal(self) -> dict[str, float]:
        """Link quality from /proc/net/wireless, as % of the usual 70 maximum."""
        out = {}
        for line in (read_text(self.roots.p("net", "wireless")) or "").splitlines()[2:]:
            name, _, rest = line.partition(":")
            f = rest.split()
            if len(f) >= 2:
                try:
                    out[name.strip()] = max(0.0, min(100.0, float(f[1].rstrip(".")) / 70.0 * 100.0))
                except ValueError:
                    pass
        return out

    def sample(self, now: float, pool) -> list[Device]:
        ifaces = self._interfaces()
        if now - self._slow_at >= _SLOW_REFRESH_S:
            self._slow_at = now
            self._ipv4 = self._ipv4_fn()
            self._ssids = {i: self._ssid_fn(i) for i in ifaces if self._is_wifi(i)}
        counters = self._counters()
        signal = self._signal()
        devices = []
        for iface in ifaces:
            wifi = self._is_wifi(iface)
            base = self.roots.s("class", "net", iface)
            up = read_text(os.path.join(base, "operstate")) == "up"
            speed = read_int(os.path.join(base, "speed")) if up else None
            speed = speed if speed and speed > 0 else None

            groups = []
            temps = [r for c in pool.take_by_device(real(os.path.join(base, "device"))) for r in c.readings(Kind.TEMP)]
            if temps:
                groups.append(Group("Temperatures", tuple(temps)))
            if iface in counters:
                rx, tx = counters[iface]
                groups.append(Group("Traffic", (
                    Reading(f"net/{iface}/down", "Download", Kind.RATE, self.rates.rate(f"{iface}/rx", rx, now)),
                    Reading(f"net/{iface}/up", "Upload", Kind.RATE, self.rates.rate(f"{iface}/tx", tx, now)),
                    Reading(f"net/{iface}/rx_total", "Downloaded", Kind.DATA, rx),
                    Reading(f"net/{iface}/tx_total", "Uploaded", Kind.DATA, tx),
                )))
            link = ("Connected" if up else "Disconnected") + (f" · {_speed(speed)}" if speed else "")
            status = [Reading(f"net/{iface}/link", "Link", Kind.INFO, text=link)]
            if self._ipv4.get(iface):
                status.append(Reading(f"net/{iface}/ipv4", "IPv4", Kind.INFO, text=self._ipv4[iface]))
            if wifi:
                if self._ssids.get(iface):
                    status.append(Reading(f"net/{iface}/ssid", "Network", Kind.INFO, text=self._ssids[iface]))
                if iface in signal:
                    status.append(Reading(f"net/{iface}/signal", "Signal", Kind.LOAD, signal[iface]))
            groups.append(Group("Status", tuple(status)))

            name = "Wi-Fi" if wifi else "Ethernet"
            detail = iface + (f" · {_speed(speed)}" if speed else "")
            devices.append(Device(f"net/{iface}", name, DeviceKind.NETWORK, detail).with_groups(groups))
        return devices


def _speed(mbit: int) -> str:
    return f"{mbit / 1000:g} Gbit/s" if mbit >= 1000 else f"{mbit} Mbit/s"

