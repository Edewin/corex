"""The floating always-on-top widget."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QGridLayout, QLabel, QMenu, QVBoxLayout, QWidget

from corex.core.model import Kind, Snapshot
from corex.core.units import format_value
from corex.ui import theme

OPACITIES = (1.0, 0.92, 0.8, 0.65)


class _Bar(QWidget):
    """Thin horizontal bar for percentages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 5)
        self.value, self.color = 0.0, theme.ACCENT

    def set(self, value: float | None, color: str) -> None:
        self.value, self.color = max(0.0, min(100.0, value or 0.0)), color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(self.rect(), 2.5, 2.5)
        p.setBrush(QColor(self.color))
        p.drawRoundedRect(QRectF(0, 0, self.width() * self.value / 100.0, self.height()), 2.5, 2.5)


class Overlay(QWidget):
    open_dashboard = Signal()
    choose_values = Signal()
    hide_requested = Signal()
    quit_requested = Signal()
    opacity_changed = Signal(float)
    moved = Signal(int, int)

    def __init__(self, opacity: float = 0.92):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("CoreX widget")
        self.reading_ids: list[str] = []
        self._rows: dict[str, tuple[QLabel, QLabel, _Bar]] = {}
        self._drag: QPoint | None = None
        self._opacity = opacity
        self.setWindowOpacity(opacity)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(6)
        head = QLabel(f"<span style='color:{theme.ACCENT}; font-weight:700'>Core</span>"
                      f"<span style='font-weight:700'>X</span>")
        outer.addWidget(head)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(5)
        outer.addLayout(self.grid)
        self.empty = QLabel("Right-click › Choose values…")
        self.empty.setObjectName("muted")
        outer.addWidget(self.empty)
        self.setToolTip("Drag to move · double-click to open CoreX · right-click for options")

    # -- content -----------------------------------------------------------
    def set_readings(self, ids: list[str]) -> None:
        self.reading_ids = list(ids)
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._rows.clear()
        for row, rid in enumerate(self.reading_ids):
            name, value, bar = QLabel(), QLabel("—"), _Bar()
            name.setObjectName("muted")
            value.setFont(theme.mono_font(10, bold=True))
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setMinimumWidth(92)
            self.grid.addWidget(name, row, 0)
            self.grid.addWidget(value, row, 1)
            self.grid.addWidget(bar, row, 2, Qt.AlignmentFlag.AlignVCenter)
            self._rows[rid] = (name, value, bar)
        self.empty.setVisible(not self.reading_ids)
        self.adjustSize()

    def on_snapshot(self, snap: Snapshot) -> None:
        for rid, (name, value, bar) in self._rows.items():
            dev = next((d for d in snap.devices if d.reading(rid)), None)
            r = dev.reading(rid) if dev else None
            if r is None:
                value.setText("—")
                bar.setVisible(False)
                continue
            name.setText(_short_name(dev.kind, dev.name, r.label, r.kind))
            value.setText(format_value(r.kind, r.value, r.text))
            color = theme.level_color(r.kind, r.value, r.id)
            value.setStyleSheet(f"color: {color}")
            pct = r.kind in (Kind.LOAD, Kind.FAN_PCT)
            bar.setVisible(pct)
            if pct:
                bar.set(r.value, theme.KIND_COLORS[Kind.LOAD] if color == theme.TEXT else color)
        self.adjustSize()

    def showEvent(self, e):
        super().showEvent(e)
        self.adjustSize()
        if QGuiApplication.screenAt(self.frameGeometry().center()) is None:   # saved spot is off every screen
            screen = QGuiApplication.primaryScreen()
            if screen:
                area = screen.availableGeometry()
                self.move(area.right() - self.width() - 24, area.top() + 24)

    def restyle(self) -> None:
        """Colours changed (theme switch)."""
        self.update()

    # -- painting & mouse --------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        p.fillPath(path, QColor(theme.BG))
        p.setPen(QColor(theme.BORDER))
        p.drawPath(path)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.moved.emit(self.x(), self.y())

    def mouseDoubleClickEvent(self, e):
        self.open_dashboard.emit()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        if QGuiApplication.platformName() == "wayland":
            # native Wayland lets no window place itself or stay above the others
            menu.addSection("Wayland: the widget cannot stay on top or keep its place")
        menu.addAction("Open CoreX", self.open_dashboard.emit)
        menu.addAction("Choose values…", self.choose_values.emit)
        sub = menu.addMenu("Opacity")
        group = QActionGroup(sub)
        for o in OPACITIES:
            a = QAction(f"{o:.0%}", sub, checkable=True, checked=abs(o - self._opacity) < 0.01)
            a.triggered.connect(lambda _=False, o=o: self._set_opacity(o))
            group.addAction(a)
            sub.addAction(a)
        menu.addSeparator()
        menu.addAction("Hide widget", self.hide_requested.emit)
        menu.addAction("Quit CoreX", self.quit_requested.emit)
        menu.exec(e.globalPos())

    def _set_opacity(self, o: float) -> None:
        self._opacity = o
        self.setWindowOpacity(o)
        self.opacity_changed.emit(o)


_KIND_SUFFIX = {Kind.TEMP: " temp", Kind.CLOCK: " clock", Kind.POWER: " power", Kind.DATA: " used"}
_ARROWS = {"Download": "↓", "Upload": "↑", "Read": "read", "Write": "write"}


def _short_name(device_kind: str, device_name: str, label: str, kind: str = "") -> str:
    """'CPU', 'CPU temp', 'GPU', 'RAM', 'Ethernet ↓' ... short enough for the widget."""
    prefix = {"cpu": "CPU", "gpu": "GPU", "memory": "RAM"}.get(device_kind) or device_name.split(" · ")[0]
    if label in _ARROWS:
        return f"{prefix} {_ARROWS[label]}"
    if label in {"Total", "GPU", "Load", "Used", "Average", "Highest"}:
        return prefix + _KIND_SUFFIX.get(kind, "")
    return f"{prefix} {label}"
