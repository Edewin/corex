"""A fake /proc + /sys tree so the engine can be tested without hardware."""

from __future__ import annotations

import os

import pytest

from corex.core.sysfs import Roots


class FakeSystem:
    def __init__(self, base):
        self.base = base
        self.roots = Roots(proc=str(base / "proc"), sys=str(base / "sys"))
        os.makedirs(self.roots.proc)
        os.makedirs(self.roots.sys)

    def write(self, path: str, text: str) -> str:
        """path like 'proc/stat' or 'sys/class/hwmon/hwmon0/name'."""
        full = self.base / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)
        return str(full)

    def mkdir(self, path: str) -> str:
        full = self.base / path
        full.mkdir(parents=True, exist_ok=True)
        return str(full)

    def link(self, path: str, target: str) -> None:
        """Symlink sys/<path> -> sys/<target> (both relative to the fake root)."""
        full = self.base / path
        full.parent.mkdir(parents=True, exist_ok=True)
        (self.base / target).mkdir(parents=True, exist_ok=True)
        os.symlink(self.base / target, full)

    def hwmon(self, index: int, name: str, device: str | None = None, **files: str) -> None:
        d = f"sys/class/hwmon/hwmon{index}"
        self.write(f"{d}/name", name)
        if device:
            self.link(f"{d}/device", device)
        for fname, value in files.items():
            self.write(f"{d}/{fname}", value)


@pytest.fixture
def fake(tmp_path):
    return FakeSystem(tmp_path)
