"""
Long-term history on disk: one row per minute with the average and the
highest value of every numeric reading, kept for `keep_days`.

~/.local/share/corex/history.db (XDG_DATA_HOME respected). A minute row
is a zlib-compressed JSON list [id, average, highest, id, ...], a few
hundred bytes even with a hundred sensors.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
import zlib
from pathlib import Path

from corex.core.model import Kind, Snapshot, UNITS

KEEP_DAYS = (7, 30, 90, 365)
GAP_S = 150          # two minute rows further apart than this were not recorded in between


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / "corex"


class Recorder:
    def __init__(self, path: Path | None = None, keep_days: int = 30):
        self.path = path or data_dir() / "history.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.keep_days = keep_days
        self.db = sqlite3.connect(self.path)
        self.db.execute("CREATE TABLE IF NOT EXISTS sensors (num INTEGER PRIMARY KEY, id TEXT UNIQUE, "
                        "label TEXT, kind TEXT, device TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS minutes (ts INTEGER PRIMARY KEY, data BLOB)")
        self.db.commit()
        # reading id -> [num, label, kind, device]
        self.sensors = {row[1]: [row[0], row[2], row[3], row[4]]
                        for row in self.db.execute("SELECT num, id, label, kind, device FROM sensors")}
        self._acc: dict[int, list[float]] = {}       # num -> [sum, count, highest]
        self._minute: int | None = None
        self._purged = 0.0

    # -- writing ------------------------------------------------------------
    def add(self, snap: Snapshot) -> None:
        minute = int(snap.timestamp // 60)
        if self._minute is not None and minute != self._minute:
            self.flush()
        self._minute = minute
        for d in snap.devices:
            for g in d.groups:
                for r in g.readings:
                    if r.value is None or r.kind == Kind.INFO:
                        continue
                    num = self._num(r.id, r.label, r.kind, d.name)
                    a = self._acc.get(num)
                    if a is None:
                        self._acc[num] = [r.value, 1, r.value]
                    else:
                        a[0] += r.value
                        a[1] += 1
                        a[2] = max(a[2], r.value)

    def _num(self, rid: str, label: str, kind: str, device: str) -> int:
        s = self.sensors.get(rid)
        if s is None:
            cur = self.db.execute("INSERT INTO sensors (id, label, kind, device) VALUES (?, ?, ?, ?)",
                                  (rid, label, kind, device))
            s = self.sensors[rid] = [cur.lastrowid, label, kind, device]
        elif s[1] != label or s[3] != device:            # renamed by the user
            self.db.execute("UPDATE sensors SET label = ?, device = ? WHERE num = ?", (label, device, s[0]))
            s[1], s[3] = label, device
        return s[0]

    def flush(self) -> None:
        if self.db is None:
            return
        if self._acc and self._minute is not None:
            self.db.execute("INSERT OR REPLACE INTO minutes (ts, data) VALUES (?, ?)",
                            (self._minute * 60, _pack(self._acc)))
            self._acc = {}
        now = time.time()
        if now - self._purged > 3600:
            self.db.execute("DELETE FROM minutes WHERE ts < ?", (int(now - self.keep_days * 86400),))
            self._purged = now
        self.db.commit()

    def set_keep_days(self, days: int) -> None:
        self.keep_days = days
        self._purged = 0.0
        self.flush()

    def close(self) -> None:
        if self.db is not None:
            self.flush()
            self.db.close()
            self.db = None

    # -- reading ------------------------------------------------------------
    def series(self, reading_id: str, since: float) -> tuple[list[float], list[float], list[float]]:
        """Times, averages and highest values per minute since `since` (current minute included)."""
        s = self.sensors.get(reading_id)
        if s is None:
            return [], [], []
        num = s[0]
        ts, avg, top = [], [], []
        rows = list(self.db.execute("SELECT ts, data FROM minutes WHERE ts >= ? ORDER BY ts", (int(since),)))
        if self._acc and self._minute is not None:
            rows.append((self._minute * 60, None))
        for t, blob in rows:
            if blob is None:
                a = self._acc.get(num)
                found = (a[0] / a[1], a[2]) if a else None
            else:
                flat = _unpack(blob)
                found = next(((flat[i + 1], flat[i + 2]) for i in range(0, len(flat), 3) if flat[i] == num), None)
            if found:
                ts.append(t + 30.0)                      # middle of the minute
                avg.append(found[0])
                top.append(found[1])
        return ts, avg, top

    def disk_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def export_csv(self, path: str, since: float, reading_ids: list[str]) -> int:
        """Average per minute, one column per sensor (one sensor: also its highest). Returns the row count."""
        self.flush()
        nums = [(rid, self.sensors[rid]) for rid in reading_ids if rid in self.sensors]
        single = len(nums) == 1
        header = ["time"]
        for _, (_, label, kind, device) in nums:
            unit = UNITS.get(kind, "")
            name = f"{device} · {label}" + (f" ({unit})" if unit else "")
            header += [name + " average", name + " highest"] if single else [name]
        rows = 0
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            for t, blob in self.db.execute("SELECT ts, data FROM minutes WHERE ts >= ? ORDER BY ts", (int(since),)):
                flat = _unpack(blob)
                values = {flat[i]: (flat[i + 1], flat[i + 2]) for i in range(0, len(flat), 3)}
                line = [time.strftime("%Y-%m-%d %H:%M", time.localtime(t))]
                for _, (num, *_rest) in nums:
                    v = values.get(num)
                    line += ([v[0], v[1]] if v else ["", ""]) if single else [v[0] if v else ""]
                w.writerow(line)
                rows += 1
        return rows


def _pack(acc: dict[int, list[float]]) -> bytes:
    flat = []
    for num, (total, count, top) in acc.items():
        flat += [num, round(total / count, 3), round(top, 3)]
    return zlib.compress(json.dumps(flat, separators=(",", ":")).encode())


def _unpack(blob: bytes) -> list:
    try:
        return json.loads(zlib.decompress(blob))
    except (zlib.error, ValueError):
        return []
