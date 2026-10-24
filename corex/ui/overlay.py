"""The floating always-on-top widget, and the painter it shares with the widget editor."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath,
                           QPixmap)
from PySide6.QtWidgets import QApplication, QMenu, QToolTip, QWidget

from corex.app.settings import config_dir
from corex.core.model import DeviceKind, Kind, Snapshot
from corex.core.units import format_value
from corex.ui import theme

GRID = 8                       # snap step in the editor
MARGIN = 12                    # free space kept around the content when the size follows it
MIN_SIZE, MAX_SIZE = (60, 30), (1600, 1000)
TITLE = "title"                # item key of the "CoreX" heading
SIZES = {"S": 8, "M": 10, "L": 13, "XL": 18}                  # value font, points
SIZE_NAMES = (("S", "Small"), ("M", "Normal"), ("L", "Large"), ("XL", "Extra large"))
ICON_CHOICES = (("auto", "Automatic"), ("none", "None"),
                (DeviceKind.CPU, "Processor"), (DeviceKind.GPU, "Graphics card"), (DeviceKind.MEMORY, "Memory"),
                (DeviceKind.STORAGE, "Drive"), (DeviceKind.NETWORK, "Network"), (DeviceKind.BOARD, "Motherboard"),
                (DeviceKind.BATTERY, "Battery"), (Kind.TEMP, "Temperature"), (Kind.FAN, "Fan"),
                (Kind.LOAD, "Load"), (Kind.CLOCK, "Clock"), (Kind.POWER, "Power"), (Kind.VOLT, "Voltage"),
                (Kind.DATA, "Data"), (Kind.RATE, "Transfer"))
BACKGROUND_FILE = "widget-background.png"                       # copied into the config folder

DEFAULT_STYLE = {
    "layout": "auto",          # "auto" = stacked list, "free" = every item where the user put it
    "fit": True,               # size follows the content; False = width x height
    "width": 260, "height": 140,
    "background": 92,          # background opacity, %
    "image": "",               # file name inside the config folder, "" = none
    "image_opacity": 35,
    "title": True,
    "snap": True,
    "locked": False,
    "items": {},               # reading id / TITLE -> item options, see ITEM_DEFAULT
}
ITEM_DEFAULT = {"icon": "none", "size": "M", "name": True, "bar": True}       # + "x", "y" in the free layout

_ICON_NAMES = {k for k, _ in ICON_CHOICES}
# readings whose kind says more than their device does
_KIND_ICON = {Kind.TEMP: Kind.TEMP, Kind.FAN: Kind.FAN, Kind.FAN_PCT: Kind.FAN, Kind.POWER: Kind.POWER,
              Kind.CLOCK: Kind.CLOCK, Kind.VOLT: Kind.VOLT, Kind.CURRENT: Kind.CURRENT, Kind.RATE: Kind.RATE}


def normalize_style(raw, legacy_opacity: float = 0.92) -> dict:
    """A complete, valid style from whatever settings.json holds."""
    s = copy.deepcopy(DEFAULT_STYLE)
    if not isinstance(raw, dict) or not raw:
        s["background"] = round(max(0.0, min(1.0, legacy_opacity)) * 100)
        return s
    for key, default in DEFAULT_STYLE.items():
        v = raw.get(key, default)
        if isinstance(default, bool):
            s[key] = v if isinstance(v, bool) else default
        elif isinstance(default, int):
            s[key] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default
        elif isinstance(default, str):
            s[key] = v if isinstance(v, str) else default
    if s["layout"] not in ("auto", "free"):
        s["layout"] = "auto"
    s["width"] = max(MIN_SIZE[0], min(MAX_SIZE[0], s["width"]))
    s["height"] = max(MIN_SIZE[1], min(MAX_SIZE[1], s["height"]))
    s["background"] = max(0, min(100, s["background"]))
    s["image_opacity"] = max(0, min(100, s["image_opacity"]))
    s["image"] = s["image"] if s["image"] == BACKGROUND_FILE else ""
    items = raw.get("items")
    if isinstance(items, dict):
        s["items"] = {k: _item(v) for k, v in items.items() if isinstance(k, str) and isinstance(v, dict)}
    return s


def _item(raw: dict) -> dict:
    it = dict(ITEM_DEFAULT)
    if raw.get("icon") in _ICON_NAMES:
        it["icon"] = raw["icon"]
    if raw.get("size") in SIZES:
        it["size"] = raw["size"]
    for key in ("name", "bar"):
        if isinstance(raw.get(key), bool):
            it[key] = raw[key]
    for key, top in (("x", MAX_SIZE[0]), ("y", MAX_SIZE[1])):
        v = raw.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            it[key] = max(0, min(top, int(v)))
    return it


@dataclass
class Entry:
    """One value as the widget shows it."""
    id: str
    name: str
    value: str = "—"
    color: str = ""
    pct: float | None = None             # bar fill; None = no bar
    kind: str = ""
    icon: str = DeviceKind.SYSTEM        # what "Automatic" draws


def entries_from(snap: Snapshot | None, ids: list[str], names: dict[str, str]) -> list[Entry]:
    out = []
    for rid in ids:
        dev = next((d for d in snap.devices if d.reading(rid)), None) if snap else None
        r = dev.reading(rid) if dev else None
        if r is None:
            out.append(Entry(rid, names.get(rid, ""), color=theme.MUTED))
            continue
        name = names[rid] = _short_name(dev.kind, dev.name, r.label, r.kind)
        color = theme.level_color(r.kind, r.value, r.id)
        pct = max(0.0, min(100.0, r.value or 0.0)) if r.kind in (Kind.LOAD, Kind.FAN_PCT) else None
        out.append(Entry(rid, name, format_value(r.kind, r.value, r.text), color, pct, r.kind,
                         _KIND_ICON.get(r.kind, dev.kind)))
    return out


class Art:
    """Lays out and paints the widget: the same picture on the desktop and in the editor."""

    def __init__(self, style: dict):
        self.style = style
        self.entries: list[Entry] = []
        self._widest: dict[tuple[str, str], float] = {}         # (id, size) -> widest value seen, px
        self._icons: dict[tuple, QPixmap] = {}
        self._image: QPixmap | None = None
        self._image_name = None

    def opts(self, key: str) -> dict:
        return self.style["items"].get(key, ITEM_DEFAULT)

    def edit(self, key: str) -> dict:
        """The item's options, created on first change."""
        return self.style["items"].setdefault(key, dict(ITEM_DEFAULT))

    def keys(self) -> list[str]:
        return ([TITLE] if self.style["title"] else []) + [e.id for e in self.entries]

    def restyle(self) -> None:
        self._icons.clear()
        self._image_name = None

    # -- geometry ----------------------------------------------------------
    @staticmethod
    def _fonts(size: str) -> tuple[QFont, QFont]:
        pt = SIZES[size]
        name = QFont(QApplication.font())
        name.setPointSizeF(pt)
        return name, theme.mono_font(pt, bold=True)

    def _columns(self) -> tuple[float, float]:
        """Shared name and value widths, so the values line up."""
        name_w = val_w = 0.0
        for e in self.entries:
            o = self.opts(e.id)
            nf, vf = self._fonts(o["size"])
            if o["name"]:
                name_w = max(name_w, QFontMetricsF(nf).horizontalAdvance(e.name))
            vm = QFontMetricsF(vf)
            # digits as 8s: the box does not jump when 9 % becomes 10 %
            key = (e.id, o["size"])
            w = max(vm.horizontalAdvance("".join("8" if c.isdigit() else c for c in e.value)),
                    vm.horizontalAdvance("88 %"), self._widest.get(key, 0.0))
            self._widest[key] = w
            val_w = max(val_w, w)
        return name_w, val_w

    def _item_size(self, e: Entry, name_w: float, val_w: float) -> QSizeF:
        o = self.opts(e.id)
        nf, vf = self._fonts(o["size"])
        s = SIZES[o["size"]] / 10.0
        h = max(QFontMetricsF(vf).height(), QFontMetricsF(nf).height())
        w = val_w
        if o["icon"] != "none":
            w += h + 6 * s
        if o["name"]:
            w += name_w + 12 * s
        if o["bar"] and e.pct is not None:
            w += 10 * s + 46 * s
        return QSizeF(w, h)

    def _title_font(self) -> QFont:
        f = QFont(QApplication.font())
        f.setPointSizeF(SIZES[self.opts(TITLE)["size"]] * 1.05)
        f.setBold(True)
        return f

    def layout(self) -> tuple[dict[str, QRectF], QSizeF]:
        name_w, val_w = self._columns()
        sizes: dict[str, QSizeF] = {}
        if self.style["title"]:
            fm = QFontMetricsF(self._title_font())
            sizes[TITLE] = QSizeF(fm.horizontalAdvance("CoreX"), fm.height())
        for e in self.entries:
            sizes[e.id] = self._item_size(e, name_w, val_w)
        if not self.entries:
            fm = QFontMetricsF(QApplication.font())
            sizes[""] = QSizeF(fm.horizontalAdvance(_EMPTY), fm.height())    # the "choose values" hint

        rects: dict[str, QRectF] = {}
        free = self.style["layout"] == "free"
        y = 10.0
        for key, size in sizes.items():
            o = self.opts(key)
            if free and "x" in o and key:
                rects[key] = QRectF(QPointF(o["x"], o["y"]), size)
                continue
            if free:      # new value in a free layout: under everything else
                y = max([r.bottom() + 5 for r in rects.values()] + [10.0])
            rects[key] = QRectF(QPointF(14.0, y), size)
            y += size.height() + (6 if key == TITLE else 5)
        if not self.style["fit"]:
            return rects, QSizeF(self.style["width"], self.style["height"])
        right = max((r.right() for r in rects.values()), default=0.0)
        bottom = max((r.bottom() for r in rects.values()), default=0.0)
        pad_r, pad_b = (MARGIN, MARGIN) if free else (14, 12)
        return rects, QSizeF(max(MIN_SIZE[0], right + pad_r), max(MIN_SIZE[1], bottom + pad_b))

    # -- painting ----------------------------------------------------------
    def _icon(self, name: str, color: str, size: int) -> QPixmap:
        key = (name, color, size)
        if key not in self._icons:
            self._icons[key] = theme.icon_pixmap(name, color, size)
        return self._icons[key]

    def image(self) -> QPixmap | None:
        name = self.style["image"]
        if name != self._image_name:
            self._image_name = name
            pm = QPixmap(str(config_dir() / name)) if name else QPixmap()
            self._image = None if pm.isNull() else pm
        return self._image

    def paint(self, p: QPainter, rects: dict[str, QRectF], size: QSizeF) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(QPointF(0, 0), size).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        alpha = round(self.style["background"] * 2.55)
        if alpha:
            p.fillPath(path, theme.qcolor(theme.BG, alpha))
        img = self.image()
        if img is not None and self.style["image_opacity"]:
            p.save()
            p.setClipPath(path)
            p.setOpacity(self.style["image_opacity"] / 100)
            k = max(size.width() / img.width(), size.height() / img.height())       # cover, centred
            w, h = img.width() * k, img.height() * k
            p.drawPixmap(QRectF((size.width() - w) / 2, (size.height() - h) / 2, w, h), img, QRectF(img.rect()))
            p.restore()
        if alpha or img is not None:
            p.setPen(theme.qcolor(theme.BORDER, max(alpha, 110 if img is not None else 0)))
            p.drawPath(path)
        halo = alpha < 150          # text straight on the desktop: a soft outline keeps it readable

        for key, r in rects.items():
            if key == TITLE:
                p.setFont(self._title_font())
                core_w = QFontMetricsF(p.font()).horizontalAdvance("Core")
                _text(p, r, Qt.AlignmentFlag.AlignLeft, "Core", theme.ACCENT, halo)
                _text(p, r.adjusted(core_w, 0, 0, 0), Qt.AlignmentFlag.AlignLeft, "X", theme.TEXT, halo)
            elif key == "":
                p.setFont(QApplication.font())
                _text(p, r, Qt.AlignmentFlag.AlignLeft, _EMPTY, theme.MUTED, halo)
        name_w, val_w = self._columns()
        for e in self.entries:
            r = rects.get(e.id)
            if r is not None:
                self._paint_entry(p, e, r, name_w, val_w, halo)

    def _paint_entry(self, p: QPainter, e: Entry, r: QRectF, name_w: float, val_w: float, halo: bool) -> None:
        o = self.opts(e.id)
        nf, vf = self._fonts(o["size"])
        s = SIZES[o["size"]] / 10.0
        x, h = r.left(), r.height()
        mid = Qt.AlignmentFlag.AlignVCenter
        if o["icon"] != "none":
            name = e.icon if o["icon"] == "auto" else o["icon"]
            color = theme.KIND_COLORS.get(e.kind if e.kind != Kind.FAN_PCT else Kind.FAN, theme.ACCENT)
            side = round(h * 0.95)
            p.drawPixmap(QPointF(x, r.top() + (h - side) / 2), self._icon(name, color, side))
            x += h + 6 * s
        if o["name"]:
            p.setFont(nf)
            _text(p, QRectF(x, r.top(), name_w, h), Qt.AlignmentFlag.AlignLeft | mid, e.name,
                  theme.TEXT if halo else theme.MUTED, halo)
            x += name_w + 12 * s
        p.setFont(vf)
        _text(p, QRectF(x, r.top(), val_w, h), Qt.AlignmentFlag.AlignRight | mid, e.value,
              e.color or theme.TEXT, halo)
        x += val_w
        if o["bar"] and e.pct is not None:
            bar = QRectF(x + 10 * s, r.top() + (h - 5 * s) / 2, 46 * s, 5 * s)
            fill = theme.KIND_COLORS[Kind.LOAD] if e.color in ("", theme.TEXT) else e.color
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.BORDER))
            p.drawRoundedRect(bar, 2.5 * s, 2.5 * s)
            p.setBrush(QColor(fill))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * e.pct / 100.0, bar.height()),
                              2.5 * s, 2.5 * s)
            p.setBrush(Qt.BrushStyle.NoBrush)


_EMPTY = "Right-click › Choose values…"


def _text(p: QPainter, r: QRectF, flags, text: str, color: str, halo: bool) -> None:
    if halo:
        p.setPen(theme.qcolor(theme.BG, 190))
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            p.drawText(r.translated(dx * 0.8, dy * 0.8), flags, text)
    p.setPen(QColor(color))
    p.drawText(r, flags, text)


class Overlay(QWidget):
    open_dashboard = Signal()
    choose_values = Signal()
    edit_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()
    style_changed = Signal()
    moved = Signal(int, int)

    def __init__(self, style: dict):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("CoreX widget")
        self.setMouseTracking(True)
        self.art = Art(style)
        self.reading_ids: list[str] = []
        self._names: dict[str, str] = {}
        self._snap: Snapshot | None = None
        self._rects: dict[str, QRectF] = {}
        self._drag: QPoint | None = None
        self._keys = QTimer(self, interval=120)              # Ctrl pressed while the mouse is over us?
        self._keys.timeout.connect(self._update_cursor)
        self.setToolTip("Ctrl + drag to move · double-click to open CoreX · right-click for options")
        self.relayout()

    # -- content -----------------------------------------------------------
    def set_readings(self, ids: list[str]) -> None:
        self.reading_ids = list(ids)
        self.art.entries = entries_from(self._snap, self.reading_ids, self._names)
        self.relayout()

    def on_snapshot(self, snap: Snapshot) -> None:
        self._snap = snap
        self.art.entries = entries_from(snap, self.reading_ids, self._names)
        self.relayout()

    def relayout(self) -> None:
        self._rects, size = self.art.layout()
        size = QSize(round(size.width()), round(size.height()))
        if size != self.size():
            self.setFixedSize(size)
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if QGuiApplication.screenAt(self.frameGeometry().center()) is None:   # saved spot is off every screen
            screen = QGuiApplication.primaryScreen()
            if screen:
                area = screen.availableGeometry()
                self.move(area.right() - self.width() - 24, area.top() + 24)

    def restyle(self) -> None:
        """Colours changed (theme switch)."""
        self.art.restyle()
        self.art.entries = entries_from(self._snap, self.reading_ids, self._names)
        self.relayout()

    # -- painting & mouse --------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        self.art.paint(p, self._rects, QSizeF(self.size()))

    def _movable(self, modifiers) -> bool:
        return bool(modifiers & Qt.KeyboardModifier.ControlModifier) and not self.art.style["locked"]

    def _update_cursor(self) -> None:
        if self._drag is not None or self._movable(QGuiApplication.queryKeyboardModifiers()):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()

    def enterEvent(self, e):
        self._keys.start()
        self._update_cursor()

    def leaveEvent(self, e):
        self._keys.stop()
        if self._drag is None:
            self.unsetCursor()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._movable(e.modifiers()):
            handle = self.windowHandle()
            if QGuiApplication.platformName() == "wayland" and handle and handle.startSystemMove():
                return        # the compositor moves it; Wayland never tells us where it ends up
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            hint = ("Position locked · right-click › Unlock position" if self.art.style["locked"] else
                    "Hold Ctrl and drag to move the widget")
            QToolTip.showText(e.globalPosition().toPoint(), hint, self)

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
        else:
            self._update_cursor()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self._update_cursor()
            self.moved.emit(self.x(), self.y())

    def mouseDoubleClickEvent(self, e):
        self.open_dashboard.emit()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        if QGuiApplication.platformName() == "wayland":
            # native Wayland lets no window place itself or stay above the others
            menu.addSection("Wayland: the widget cannot stay on top or keep its place")
        menu.addAction("Open CoreX", self.open_dashboard.emit)
        menu.addAction(theme.icon("widget", theme.TEXT, 16), "Edit widget…", self.edit_requested.emit)
        menu.addAction("Choose values…", self.choose_values.emit)
        lock = QAction("Lock position", menu, checkable=True, checked=self.art.style["locked"])
        lock.toggled.connect(self._set_locked)
        menu.addAction(lock)
        menu.addSeparator()
        menu.addAction("Hide widget", self.hide_requested.emit)
        menu.addAction("Quit CoreX", self.quit_requested.emit)
        menu.exec(e.globalPos())

    def _set_locked(self, on: bool) -> None:
        self.art.style["locked"] = on
        self.style_changed.emit()


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
