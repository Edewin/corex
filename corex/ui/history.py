"""History window: one sensor over the last hour / day / week / month, from the recorder on disk."""

from __future__ import annotations

import math
import os
import time

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from corex.app.recorder import GAP_S, KEEP_DAYS, Recorder
from corex.core.model import Kind, UNITS
from corex.core.units import format_value, human_bytes
from corex.ui import theme

RANGES = (("Last hour", 3600), ("24 hours", 86400), ("7 days", 7 * 86400), ("30 days", 30 * 86400))


def _scale(kind: str, top: float) -> tuple[float, str]:
    """Divisor and unit for the value axis."""
    if kind in (Kind.RATE, Kind.DATA):
        steps = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while top >= 1024 and i < len(steps) - 1:
            top /= 1024
            i += 1
        return 1024.0 ** i, steps[i] + ("/s" if kind == Kind.RATE else "")
    return 1.0, UNITS.get(kind, "")


class HistoryDialog(QDialog):
    def __init__(self, recorder: Recorder, reading_id: str | None, keep_days: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("History")
        self.resize(1000, 620)
        self.recorder = recorder
        self.keep_days = keep_days
        self._range = RANGES[1][1]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self.sensor = QComboBox()
        self.sensor.setMinimumWidth(380)
        self.sensor.setMaxVisibleItems(25)
        items = sorted(recorder.sensors.items(), key=lambda kv: (kv[1][3], kv[1][1]))
        for rid, (_, label, kind, device) in items:
            self.sensor.addItem(f"{device} · {label}", rid)
        if reading_id is not None and self.sensor.findData(reading_id) >= 0:
            self.sensor.setCurrentIndex(self.sensor.findData(reading_id))
        self.sensor.currentIndexChanged.connect(self.redraw)
        top.addWidget(self.sensor)
        top.addStretch(1)
        group = QButtonGroup(self)
        for text, seconds in RANGES:
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setChecked(seconds == self._range)
            b.clicked.connect(lambda _=False, s=seconds: self._set_range(s))
            group.addButton(b)
            top.addWidget(b)
        lay.addLayout(top)

        self.summary = QLabel()
        self.summary.setObjectName("h2")
        lay.addWidget(self.summary)
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.plot.setBackground(theme.PANEL)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        for axis in ("left", "bottom"):
            self.plot.getAxis(axis).setTextPen(theme.MUTED)
            self.plot.getAxis(axis).setPen(theme.BORDER)
        self.plot.addLegend(offset=(10, 10), labelTextColor=theme.MUTED)
        lay.addWidget(self.plot, 1)
        self.empty = QLabel("No history for this range yet. CoreX records while it runs, also when only "
                            "the widget or the tray icon is shown.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Keep history for"))
        self.keep = QComboBox()
        for d in KEEP_DAYS:
            self.keep.addItem("1 year" if d == 365 else f"{d} days", d)
        self.keep.setCurrentIndex(max(0, self.keep.findData(keep_days)))
        self.keep.currentIndexChanged.connect(self._set_keep)
        bottom.addWidget(self.keep)
        self.disk = QLabel()
        self.disk.setObjectName("muted")
        bottom.addWidget(self.disk, 1)
        export = QPushButton("Export CSV…")
        menu = QMenu(export)
        menu.addAction("This sensor", lambda: self._export(all_sensors=False))
        menu.addAction("All sensors", lambda: self._export(all_sensors=True))
        export.setMenu(menu)
        bottom.addWidget(export)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        lay.addLayout(bottom)
        self.redraw()

    # ------------------------------------------------------------------
    def _set_range(self, seconds: int) -> None:
        self._range = seconds
        self.redraw()

    def _set_keep(self) -> None:
        self.keep_days = self.keep.currentData()
        self.recorder.set_keep_days(self.keep_days)
        self._show_disk()

    def _show_disk(self) -> None:
        self.disk.setText(f"   {human_bytes(self.recorder.disk_bytes())} on disk")

    def redraw(self) -> None:
        self._show_disk()
        self.plot.clear()
        rid = self.sensor.currentData()
        meta = self.recorder.sensors.get(rid) if rid else None
        ts, avg, top = self.recorder.series(rid, time.time() - self._range) if meta else ([], [], [])
        self.empty.setVisible(not ts)
        self.plot.setVisible(bool(ts))
        if not ts:
            self.summary.setText(self.sensor.currentText())
            return
        kind = meta[2]
        div, unit = _scale(kind, max(top))
        # break the lines where CoreX was not running
        xs, ya, yt = [], [], []
        for i, t in enumerate(ts):
            if i and t - ts[i - 1] > GAP_S:
                xs.append(t - 1)
                ya.append(math.nan)
                yt.append(math.nan)
            xs.append(t)
            ya.append(avg[i] / div)
            yt.append(top[i] / div)
        color = theme.KIND_COLORS.get(kind, theme.ACCENT)
        self.plot.plot(xs, yt, pen=pg.mkPen(theme.qcolor(color, 110), width=1), name="Highest each minute",
                       connect="finite")
        self.plot.plot(xs, ya, pen=pg.mkPen(color, width=2), name="Average", connect="finite")
        self.plot.setLabel("left", unit)
        now = time.time()
        self.plot.setXRange(now - self._range, now, padding=0.01)
        hi = max(range(len(top)), key=top.__getitem__)
        mean = sum(avg) / len(avg)
        when = time.strftime("%a %H:%M", time.localtime(ts[hi]))
        self.summary.setText(f"{self.sensor.currentText()}   ·   average {format_value(kind, mean)}   ·   "
                             f"highest {format_value(kind, top[hi])} on {when}")

    def _export(self, all_sensors: bool) -> None:
        rid = self.sensor.currentData()
        ids = list(self.recorder.sensors) if all_sensors else ([rid] if rid else [])
        if not ids:
            return
        name = "corex-history.csv" if all_sensors else "corex-" + self.sensor.currentText().replace(" · ", "-") \
            .replace(" ", "-").replace("/", "-").lower() + ".csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export history", os.path.join(os.path.expanduser("~"), name),
                                              "CSV (*.csv)")
        if path:
            rows = self.recorder.export_csv(path, time.time() - self._range, ids)
            self.disk.setText(f"   Exported {rows} minutes to {path}")
