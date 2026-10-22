"""
Physical disks: activity from /proc/diskstats, space from the mounted
filesystems on their partitions (also through LVM / dm-crypt), and the
drive temperature from hwmon (nvme, drivetemp).
"""

from __future__ import annotations

import os
import re
from typing import Callable

from corex.core.hwmon import HwmonPool
from corex.core.model import Device, DeviceKind, Group, Kind, Reading
from corex.core.rates import RateTracker
from corex.core.sysfs import Roots, list_dir, read_int, read_text, real
from corex.core.units import human_bytes

_SKIP = re.compile(r"^(loop|ram|zram|sr|fd|dm-|md|nbd)\d*")
_PSEUDO_FS = {"tmpfs", "devtmpfs", "proc", "sysfs", "overlay", "squashfs", "cgroup2", "devpts", "fuse.portal"}


def _statvfs(path: str) -> tuple[int, int] | None:
    """(total, free) in bytes for the filesystem mounted at `path`."""
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    return st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize


class StorageSource:
    def __init__(self, roots: Roots, statvfs: Callable[[str], tuple[int, int] | None] = _statvfs,
                 resolve_dev: Callable[[str], str] = os.path.realpath):
        self.roots = roots
        self.rates = RateTracker()
        self.statvfs = statvfs
        self.resolve_dev = resolve_dev

    # -- discovery -------------------------------------------------------
    def _disks(self) -> list[str]:
        disks = []
        for name in list_dir(self.roots.s("block")):
            if _SKIP.match(name):
                continue
            if (read_int(self.roots.s("block", name, "size")) or 0) == 0:
                continue                       # empty card reader slot, etc.
            disks.append(name)
        return disks

    def _owner_disks(self, blockdev: str, disks: list[str]) -> set[str]:
        """Disk(s) holding a block device: sda1 -> {sda}; dm-0 -> disks of its slaves."""
        if blockdev in disks:
            return {blockdev}
        for disk in disks:
            if os.path.isdir(self.roots.s("block", disk, blockdev)):
                return {disk}
        slaves = list_dir(self.roots.s("block", blockdev, "slaves"))
        owners: set[str] = set()
        for s in slaves:
            owners |= self._owner_disks(s, disks)
        return owners

    def _mounts_by_disk(self, disks: list[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {d: [] for d in disks}
        seen_src: dict[str, str] = {}
        for line in (read_text(self.roots.p("mounts")) or "").splitlines():
            parts = line.split()
            if len(parts) < 3 or not parts[0].startswith("/dev/") or parts[2] in _PSEUDO_FS:
                continue
            src = os.path.basename(self.resolve_dev(parts[0]))
            mount = parts[1].replace("\\040", " ")
            # bind mounts / btrfs subvolumes: keep the shortest mount point of a device
            if src in seen_src and len(seen_src[src]) <= len(mount):
                continue
            seen_src[src] = mount
        for src, mount in seen_src.items():
            for disk in self._owner_disks(src, disks):
                out[disk].append(mount)
        return {d: sorted(m) for d, m in out.items()}

    # -- sampling --------------------------------------------------------
    def sample(self, now: float, pool: HwmonPool) -> list[Device]:
        disks = self._disks()
        stats = self._diskstats()
        mounts = self._mounts_by_disk(disks)
        devices = []
        for disk in disks:
            groups = []
            dev_path = real(self.roots.s("block", disk))
            temps = [r for chip in pool.take_by_device(dev_path) for r in chip.readings(Kind.TEMP)]
            if temps:
                groups.append(Group("Temperatures", tuple(temps)))

            if disk in stats:
                read_b, write_b, busy_ms = stats[disk]
                busy = self.rates.rate(f"{disk}/busy", busy_ms, now)
                groups.append(Group("Activity", (
                    Reading(f"disk/{disk}/busy", "Busy", Kind.LOAD, None if busy is None else min(100.0, busy / 10.0)),
                    Reading(f"disk/{disk}/read", "Read", Kind.RATE, self.rates.rate(f"{disk}/read", read_b, now)),
                    Reading(f"disk/{disk}/write", "Write", Kind.RATE, self.rates.rate(f"{disk}/write", write_b, now)),
                )))

            space = []
            for mount in mounts.get(disk, []):
                tf = self.statvfs(mount)
                if tf and tf[0] > 0:
                    total, free = tf
                    space.append(Reading(f"disk/{disk}/space{mount}", mount, Kind.LOAD, 100.0 * (total - free) / total))
                    space.append(Reading(f"disk/{disk}/free{mount}", f"{mount} free", Kind.DATA, free))
            if space:
                groups.append(Group("Space", tuple(space)))

            devices.append(Device(f"disk/{disk}", self._model(disk), DeviceKind.STORAGE,
                                  self._detail(disk)).with_groups(groups))
        return devices

    def _diskstats(self) -> dict[str, tuple[int, int, int]]:
        """name -> (bytes read, bytes written, ms spent doing I/O)."""
        out = {}
        for line in (read_text(self.roots.p("diskstats")) or "").splitlines():
            f = line.split()
            if len(f) >= 14:
                out[f[2]] = (int(f[5]) * 512, int(f[9]) * 512, int(f[12]))
        return out

    def _model(self, disk: str) -> str:
        model = read_text(self.roots.s("block", disk, "device", "model"))
        if model:
            return re.sub(r"\s+", " ", model)
        return disk

    def _detail(self, disk: str) -> str:
        if disk.startswith("nvme"):
            kind = "NVMe SSD"
        elif read_int(self.roots.s("block", disk, "removable")) == 1:
            kind = "Removable"
        elif read_int(self.roots.s("block", disk, "queue", "rotational")) == 1:
            kind = "HDD"
        else:
            kind = "SSD"
        size = (read_int(self.roots.s("block", disk, "size")) or 0) * 512
        return f"{kind} · {human_bytes(size)} · {disk}"
