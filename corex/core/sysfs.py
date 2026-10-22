"""
Small helpers to read /proc and /sys.

Every source receives a Roots object instead of hard-coding "/proc" and
"/sys", so the tests can point it at a fake tree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Roots:
    proc: str = "/proc"
    sys: str = "/sys"

    def p(self, *parts: str) -> str:
        return os.path.join(self.proc, *parts)

    def s(self, *parts: str) -> str:
        return os.path.join(self.sys, *parts)


def read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def read_int(path: str) -> int | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None


def list_dir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def real(path: str) -> str | None:
    """Resolved path of a sysfs symlink, or None when it does not exist."""
    if not os.path.exists(path):
        return None
    return os.path.realpath(path)
