"""Reusable pieces: a tile with live value + sparkline, a sidebar entry."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from corex.app.poller import History
from corex.core.model import Kind, Snapshot
from corex.core.units import format_value
from corex.ui import theme

pg.setConfigOptions(antialias=True, background=None, foreground=theme.MUTED)

# second series of a shared tile (upload next to download, write next to read)
_SECOND_COLOR = "#f0a35e"


class Sparkline(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMenuEnabled(False)
        self.setMouseEnabled(False, False)
        self.hideButtons()
        self.setBackground(None)
        for axis in ("left", "bottom"):
            self.hideAxis(axis)
        self.getPlotItem().setContentsMargins(0, 0, 0, 0)
        self.setMinimumHeight(70)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._curves: list[pg.PlotDataItem] = []

    def set_series(self, colors: list[str]) -> None:
        self.clear()
        self._curves = []
        for i, c in enumerate(colors):
            pen = pg.mkPen(c, width=2)
            brush = theme.qcolor(c, 45) if i == 0 else None
            curve = self.plot([], [], pen=pen, fillLevel=0 if brush else None, brush=brush)
            self._curves.append(curve)

    def update_data(self, series: list[list[float]], kind: str) -> None:
        top = 0.0
        for curve, values in zip(self._curves, series):
            curve.setData(list(range(len(values))), values)
            if values:
                top = max(top, max(values))
        if kind in (Kind.LOAD, Kind.FAN_PCT):
            self.setYRange(0, 100, padding=0.02)
        elif kind == Kind.TEMP:
            lo = min((min(v) for v in series if v), default=0)
            self.setYRange(max(0, lo - 5), max(lo + 10, top + 5), padding=0)
        else:
            self.setYRange(0, max(top * 1.15, 1e-9), padding=0)
        self.setXRange(0, max(60, max((len(v) for v in series), default=0)), padding=0)


class Tile(QFrame):
    clicked = Signal(str)            # device id
    closed = Signal(str)             # first reading id (closable tiles only)

    def __init__(self, device_id: str, reading_ids: list[str], show_device: bool = False,
                 closable: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        if not closable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.device_id, self.reading_ids, self.show_device = device_id, reading_ids, show_device
        self._kind: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("muted")
        self.value = QLabel("—")
        self.value.setFont(theme.mono_font(19, bold=True))
        self.sub = QLabel()
        self.sub.setObjectName("muted")
        self.sub.setFont(theme.mono_font(9))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.title, 1)
        if closable:
            close = QToolButton()
            close.setIcon(theme.icon("close", theme.MUTED, 14))
            close.setAutoRaise(True)
            close.setFixedSize(22, 22)
            close.setStyleSheet("QToolButton { border: none; background: transparent; padding: 0; }"
                                f"QToolButton:hover {{ background: {theme.PANEL_HI}; border-radius: 4px; }}")
            close.setToolTip("Remove this chart")
            close.clicked.connect(lambda: self.closed.emit(self.reading_ids[0]))
            head.addWidget(close)
        lay.addLayout(head)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)
        self.chart = Sparkline()
        lay.addWidget(self.chart, 1)
        self.setMinimumWidth(230)
        self.setFixedHeight(196)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.device_id)
        super().mouseReleaseEvent(e)

    def refresh(self, snap: Snapshot, history: History) -> None:
        dev = snap.device(self.device_id)
        readings = [dev.reading(i) for i in self.reading_ids] if dev else []
        readings = [r for r in readings if r is not None]
        if not readings:
            self.value.setText("—")
            return
        first = readings[0]
        if self._kind != first.kind:
            self._kind = first.kind
            color = theme.KIND_COLORS.get(first.kind, theme.ACCENT)
            self.chart.set_series([color] + [_SECOND_COLOR] * (len(readings) - 1))

        if len(readings) == 1:
            title = _title(first.label, first.kind)
            self.title.setText(f"{dev.name} · {title}" if self.show_device else title)
            self.value.setText(format_value(first.kind, first.value, first.text))
            self.value.setStyleSheet(f"color: {theme.level_color(first.kind, first.value, first.id)}")
            if first.min is not None:
                self.sub.setText(f"min {format_value(first.kind, first.min)}   "
                                 f"max {format_value(first.kind, first.max)}")
        else:
            arrows = {"/down": "↓", "/up": "↑", "/read": "R", "/write": "W"}
            parts = []
            for r in readings:
                tag = next((a for s, a in arrows.items() if r.id.endswith(s)), r.label)
                parts.append(f"{tag} {format_value(r.kind, r.value)}")
            what = "Traffic" if first.id.endswith(("/down", "/up")) else "Read / write"
            self.title.setText(f"{dev.name} · {dev.detail.split(' · ')[-1] if dev.kind == 'storage' else dev.detail.split(' · ')[0]}"
                               if self.show_device else what)
            self.value.setText(parts[0])
            self.value.setStyleSheet(f"color: {theme.KIND_COLORS[Kind.RATE]}")
            self.sub.setText("   ".join(parts[1:]))
            self.sub.setStyleSheet(f"color: {_SECOND_COLOR}")
        self.chart.update_data([history.values(r.id) for r in readings], first.kind)


def _title(label: str, kind: str) -> str:
    names = {Kind.LOAD: "load", Kind.TEMP: "temperature", Kind.CLOCK: "clock", Kind.POWER: "power"}
    if kind in names and names[kind] not in label.lower() and label in ("Total", "GPU", "Average", "Load"):
        return f"{label} {names[kind]}" if label != "Load" else "Load"
    return label


class SidebarEntry(QWidget):
    """Icon, device name, detail line and live summary."""

    def __init__(self, icon_name: str, name: str, detail: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QWidget { background: transparent; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(theme.icon_pixmap(icon_name, theme.ACCENT, 22))
        ic.setFixedWidth(26)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.name = QLabel(name)
        self.name.setStyleSheet("font-weight: 600;")
        self.detail = QLabel(detail)
        self.detail.setObjectName("muted")
        self.detail.setStyleSheet("font-size: 8.5pt;")
        self.summary = QLabel()
        self.summary.setFont(theme.mono_font(9))
        for w in (self.name, self.detail, self.summary):
            w.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            col.addWidget(w)
        lay.addLayout(col, 1)
        self.detail.setVisible(bool(detail))
