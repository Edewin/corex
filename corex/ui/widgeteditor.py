"""The widget editor: live preview to drag values around, plus the look of the widget."""

from __future__ import annotations

import copy

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from corex.app.settings import config_dir
from corex.ui import theme
from corex.ui.backgrounds import GalleryDialog
from corex.ui.overlay import (BACKGROUND_FILE, DEFAULT_STYLE, GRID, ICON_CHOICES, MARGIN, MAX_SIZE, MIN_SIZE,
                              SIZE_NAMES, TITLE, Overlay)

PAD = 32                       # desktop shown around the widget in the preview
HANDLE = 10                    # resize grip, px
GUIDE = 5                      # px: how close an edge comes before it sticks to another one
GUIDE_COLOR = "#ff5ad1"


class _Canvas(QWidget):
    """
    The widget drawn on a fake desktop. Drag values to place them (their edges
    stick to the other values), Shift + click or drag a box to pick several,
    drag the corner to resize.
    """
    selected = Signal(str)          # the value the side panel shows ("" = none)
    changed = Signal()

    def __init__(self, overlay: Overlay, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.art = overlay.art
        self.current = ""
        self.chosen: list[str] = []
        self._press: QPointF | None = None       # where a drag of the chosen values started
        self._start: dict[str, QRectF] = {}      # their places then
        self._band: QRectF | None = None         # box being dragged to pick values
        self._band_base: list[str] = []
        self._guides: list[tuple[str, float]] = []   # ("v", x) / ("h", y) lines shown while dragging
        self._resizing = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.refit()

    def refit(self) -> None:
        rects, size = self.art.layout()
        self._rects, self._size = rects, size
        self.chosen = [k for k in self.chosen if k in rects]
        if self.current not in rects:
            self.current = self.chosen[-1] if self.chosen else ""
        self.setMinimumSize(max(440, round(size.width()) + 2 * PAD), max(300, round(size.height()) + 2 * PAD))
        self.update()

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        sky = QLinearGradient(0, 0, self.width(), self.height())        # a wallpaper, so transparency shows
        sky.setColorAt(0, QColor("#2b5876"))
        sky.setColorAt(0.55, QColor("#4e4376"))
        sky.setColorAt(1, QColor("#c0603f"))
        p.fillRect(self.rect(), sky)
        p.translate(PAD, PAD)
        if self._press is not None and self.art.style["snap"]:
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.2))
            for x in range(0, round(self._size.width()) + 1, GRID):
                for y in range(0, round(self._size.height()) + 1, GRID):
                    p.drawPoint(x, y)
        self.art.paint(p, self._rects, self._size)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine))
        p.drawRect(QRectF(QPointF(0, 0), self._size).adjusted(-0.5, -0.5, 0.5, 0.5))
        for key in self.chosen:
            r = self._rects.get(key)
            if r is not None:
                p.setPen(QPen(QColor(theme.ACCENT), 2 if key == self.current else 1.2))
                p.drawRoundedRect(r.adjusted(-4, -3, 4, 3), 4, 4)
        p.setPen(QPen(QColor(GUIDE_COLOR), 1))
        for axis, v in self._guides:
            if axis == "v":
                p.drawLine(QPointF(v, -PAD / 2), QPointF(v, self._size.height() + PAD / 2))
            else:
                p.drawLine(QPointF(-PAD / 2, v), QPointF(self._size.width() + PAD / 2, v))
        if self._band is not None:
            fill = QColor(theme.ACCENT)
            fill.setAlpha(40)
            p.setBrush(fill)
            p.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
            p.drawRect(self._band.normalized())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawRect(self._handle())

    def _handle(self) -> QRectF:
        return QRectF(self._size.width() - HANDLE / 2, self._size.height() - HANDLE / 2, HANDLE, HANDLE)

    # -- selection ---------------------------------------------------------
    def _at(self, pos: QPointF) -> str | None:
        return next((k for k, r in self._rects.items() if k and r.adjusted(-4, -3, 4, 3).contains(pos)), None)

    def select(self, key: str) -> None:
        self.set_chosen([key] if key else [])

    def set_chosen(self, keys: list[str], current: str | None = None) -> None:
        current = current if current is not None else (keys[-1] if keys else "")
        if keys == self.chosen and current == self.current:
            return
        self.chosen, self.current = keys, current
        self.selected.emit(current)
        self.update()

    def values(self) -> list[str]:
        """Every value in the widget (not the title), in reading order: rows from the top, left to right."""
        keys = [k for k in self._rects if k and k != TITLE]
        return sorted(keys, key=lambda k: (round(self._rects[k].top() / GRID), self._rects[k].left()))

    # -- mouse & keys ------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position() - QPointF(PAD, PAD)
        if self._handle().adjusted(-4, -4, 4, 4).contains(pos):
            self._resizing = True
            return
        key = self._at(pos)
        adding = bool(e.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier))
        if key is None:
            self._band = QRectF(pos, pos)
            self._band_base = list(self.chosen) if adding else []
            if not adding:
                self.set_chosen([])
            return
        if adding and key in self.chosen:
            self.set_chosen([k for k in self.chosen if k != key])
            return
        if adding:
            self.set_chosen(self.chosen + [key], key)
        elif key not in self.chosen:
            self.set_chosen([key])
        else:
            self.set_chosen(self.chosen, key)
        self._to_free()
        self._press = pos
        self._start = {k: QRectF(self._rects[k]) for k in self.chosen}
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        pos = e.position() - QPointF(PAD, PAD)
        style = self.art.style
        if self._resizing:
            style["fit"] = False
            style["width"] = max(MIN_SIZE[0], min(MAX_SIZE[0], self._snap(pos.x())))
            style["height"] = max(MIN_SIZE[1], min(MAX_SIZE[1], self._snap(pos.y())))
            self.changed.emit()
        elif self._press is not None:
            dx, dy = self._place(pos - self._press)
            for key, r in self._start.items():
                it = self.art.edit(key)
                it["x"] = max(0, min(MAX_SIZE[0], round(r.x() + dx)))
                it["y"] = max(0, min(MAX_SIZE[1], round(r.y() + dy)))
            self.changed.emit()
        elif self._band is not None:
            self._band.setBottomRight(pos)
            box = self._band.normalized()
            inside = [k for k, r in self._rects.items() if k and box.intersects(r)]
            self.set_chosen(self._band_base + [k for k in inside if k not in self._band_base])
            self.update()
        elif self._handle().adjusted(-4, -4, 4, 4).contains(pos):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif self._at(pos):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        if self._press is not None and self.art.style["fit"]:
            tidy(self.art.style, self._rects)
            self.changed.emit()
        self._press = None
        self._band = None
        self._guides = []
        self._resizing = False
        self.unsetCursor()
        self.update()

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.StandardKey.SelectAll):
            self.set_chosen([k for k in self._rects if k])
            return
        if e.key() == Qt.Key.Key_Escape and self.chosen:
            self.set_chosen([])
            return
        step = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        d = step.get(e.key())
        if d is None or not self.chosen:
            return super().keyPressEvent(e)
        n = GRID if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        self._to_free()
        for key in self.chosen:
            it = self.art.edit(key)
            it["x"] = max(0, it["x"] + d[0] * n)
            it["y"] = max(0, it["y"] + d[1] * n)
        self.changed.emit()

    def _snap(self, v: float) -> int:
        return round(v / GRID) * GRID if self.art.style["snap"] else round(v)

    def _place(self, d: QPointF) -> tuple[float, float]:
        """
        Offset for the dragged values: an edge or middle that comes within GUIDE
        of another value's (or the widget's) sticks to it and shows a guide;
        otherwise the grid, when it is on.
        """
        group = QRectF()
        for r in self._start.values():
            group = group.united(r)
        moved = group.translated(d)
        others = [r for k, r in self._rects.items() if k and k not in self.chosen]
        w, h = self._size.width(), self._size.height()
        fit = self.art.style["fit"]
        xs = [v for r in others for v in (r.left(), r.right(), r.center().x())] + \
             ([MARGIN] if fit else [MARGIN, w - MARGIN, w / 2])
        ys = [v for r in others for v in (r.top(), r.bottom(), r.center().y())] + \
             ([MARGIN] if fit else [MARGIN, h - MARGIN, h / 2])
        self._guides = []
        out = []
        for axis, mine, targets, start, delta in (
                ("v", (moved.left(), moved.right(), moved.center().x()), xs, group.left(), d.x()),
                ("h", (moved.top(), moved.bottom(), moved.center().y()), ys, group.top(), d.y())):
            best = min(((abs(t - m), t - m, t) for m in mine for t in targets), default=None)
            if best is not None and best[0] <= GUIDE:
                out.append(delta + best[1])
                self._guides.append((axis, best[2]))
            else:
                out.append(self._snap(start + delta) - start)
        return out[0], out[1]

    def _to_free(self) -> None:
        """First drag: every item keeps the place the list layout gave it."""
        if self.art.style["layout"] == "free":
            return
        self.art.style["layout"] = "free"
        for key, r in self._rects.items():
            if key:
                it = self.art.edit(key)
                it["x"], it["y"] = round(r.x()), round(r.y())

    # -- aligning ----------------------------------------------------------
    def align(self, how: str) -> None:
        """left / right / top edges of the chosen values, or even vertical spacing ("spread")."""
        rects = {k: self._rects[k] for k in self.chosen if k in self._rects}
        if len(rects) < 2:
            return
        self._to_free()
        if how == "left":
            x = min(r.left() for r in rects.values())
            for k in rects:
                self.art.edit(k)["x"] = round(x)
        elif how == "right":
            x = max(r.right() for r in rects.values())
            for k, r in rects.items():
                self.art.edit(k)["x"] = max(0, round(x - r.width()))
        elif how == "top":
            y = min(r.top() for r in rects.values())
            for k in rects:
                self.art.edit(k)["y"] = round(y)
        elif how == "spread":
            order = sorted(rects, key=lambda k: rects[k].top())
            first, last = rects[order[0]], rects[order[-1]]
            room = last.bottom() - first.top() - sum(r.height() for r in rects.values())
            gap = max(4.0, room / (len(order) - 1))
            y = first.top()
            for k in order:
                self.art.edit(k)["y"] = round(y)
                y += rects[k].height() + gap
        self.changed.emit()

    def arrange(self, columns: int) -> None:
        """Every value in a grid of 1-3 columns, in reading order, the title on top; the size follows."""
        keys = self.values()
        if not keys:
            return
        self._to_free()
        y0 = MARGIN
        title = self._rects.get(TITLE)
        if title is not None:
            it = self.art.edit(TITLE)
            it["x"], it["y"] = MARGIN, MARGIN
            y0 = MARGIN + title.height() + 6
        col_w = max(self._rects[k].width() for k in keys) + 18
        y = y0
        for row in range(0, len(keys), columns):
            line = keys[row:row + columns]
            for col, k in enumerate(line):
                it = self.art.edit(k)
                it["x"], it["y"] = round(MARGIN + col * col_w), round(y)
            y += max(self._rects[k].height() for k in line) + 5
        self.art.style["fit"] = True
        self.changed.emit()


def tidy(style: dict, rects: dict[str, QRectF]) -> None:
    """Size follows the content: move everything so the content starts MARGIN from the top left."""
    if style["layout"] != "free" or not rects:
        return
    left = min(r.left() for r in rects.values())
    top = min(r.top() for r in rects.values())
    for key, it in style["items"].items():
        if key in rects and "x" in it:
            it["x"] = max(0, round(it["x"] - left + MARGIN))
            it["y"] = max(0, round(it["y"] - top + MARGIN))


class WidgetEditor(QDialog):
    changed = Signal()

    def __init__(self, overlay: Overlay, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit widget")
        self.overlay = overlay
        self.art = overlay.art
        self._loading = False

        self.canvas = _Canvas(overlay)
        self.canvas.changed.connect(self._apply)
        self.canvas.selected.connect(self._load_item)
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        scroll.setMinimumSize(480, 340)
        hint = QLabel("Drag the values to place them, their edges stick to the others · Shift + click or "
                      "drag a box to pick several · the corner square resizes · arrow keys nudge "
                      "(Shift: one grid step)")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        left = QVBoxLayout()
        left.addLayout(self._align_bar())
        left.addWidget(scroll, 1)
        left.addWidget(hint)

        right = QVBoxLayout()
        right.addWidget(self._widget_box())
        right.addWidget(self._item_box())
        right.addStretch(1)

        reset = QPushButton(theme.icon("reset", theme.TEXT, 16), "Reset to default")
        reset.setToolTip("Back to the original look and list layout (your values stay)")
        reset.clicked.connect(self._reset)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(close)

        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addLayout(right)
        outer = QVBoxLayout(self)
        outer.addLayout(body, 1)
        outer.addLayout(buttons)
        self.resize(940, 560)
        self._load_widget()
        self._load_item("")

    # -- panels ------------------------------------------------------------
    def _align_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        self.align_buttons: list[tuple[QToolButton, int]] = []
        for how, icon_name, tip, need in (("left", "align-left", "Align the left edges", 2),
                                          ("right", "align-right", "Align the right edges", 2),
                                          ("top", "align-top", "Align the tops (one row)", 2),
                                          ("spread", "spread", "Even spacing from top to bottom", 3)):
            b = QToolButton()
            b.setIcon(theme.icon(icon_name, theme.TEXT, 18))
            b.setToolTip(f"{tip} · pick {need} or more values (Shift + click or drag a box)")
            b.clicked.connect(lambda _=False, h=how: self.canvas.align(h))
            row.addWidget(b)
            self.align_buttons.append((b, need))
        row.addSpacing(14)
        label = QLabel("Arrange:")
        label.setObjectName("muted")
        row.addWidget(label)
        for n in (1, 2, 3):
            b = QToolButton()
            b.setText(f"{n} column{'s' if n > 1 else ''}")
            b.setIcon(theme.icon(f"columns{n}", theme.TEXT, 18))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setToolTip(f"Every value in {n} column{'s' if n > 1 else ''}, in their order from the top")
            b.clicked.connect(lambda _=False, c=n: self.canvas.arrange(c))
            row.addWidget(b)
        row.addStretch(1)
        return row

    def _widget_box(self) -> QGroupBox:
        box = QGroupBox("Widget")
        form = QFormLayout(box)
        self.fit = QCheckBox("Fit to the content")
        self.fit.toggled.connect(self._on_fit)
        self.width_spin, self.height_spin = QSpinBox(), QSpinBox()
        for spin, lo, hi in ((self.width_spin, MIN_SIZE[0], MAX_SIZE[0]), (self.height_spin, MIN_SIZE[1], MAX_SIZE[1])):
            spin.setRange(lo, hi)
            spin.setSuffix(" px")
            spin.valueChanged.connect(self._on_size)
        size_row = QHBoxLayout()
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.height_spin)
        form.addRow("Size", self.fit)
        form.addRow("", size_row)

        self.background, self.background_label = self._slider("background")
        form.addRow("Background", self._with_label(self.background, self.background_label))

        self.choose_image = QPushButton("Choose image…")
        self.choose_image.clicked.connect(self._gallery)
        self.remove_image = QPushButton("Remove")
        self.remove_image.clicked.connect(self._drop_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.choose_image)
        image_row.addWidget(self.remove_image)
        form.addRow("Image", image_row)
        self.image_opacity, self.image_label = self._slider("image_opacity")
        form.addRow("Image opacity", self._with_label(self.image_opacity, self.image_label))

        self.show_title = QCheckBox("Show the CoreX title")
        self.show_title.toggled.connect(lambda on: self._set("title", on))
        self.snap = QCheckBox(f"Snap to a {GRID} px grid")
        self.snap.toggled.connect(lambda on: self._set("snap", on))
        form.addRow("", self.show_title)
        form.addRow("", self.snap)
        return box

    def _item_box(self) -> QGroupBox:
        self.item_box = box = QGroupBox("Selected value")
        lay = QVBoxLayout(box)
        self.item_hint = QLabel("Click a value in the preview to change it.")
        self.item_hint.setObjectName("muted")
        self.item_hint.setWordWrap(True)
        lay.addWidget(self.item_hint)
        form = QFormLayout()
        self.icon_combo = QComboBox()
        for key, text in ICON_CHOICES:
            if key in ("auto", "none"):
                self.icon_combo.addItem(text, key)
            else:
                self.icon_combo.addItem(theme.icon(key, theme.TEXT, 16), text, key)
        self.icon_combo.currentIndexChanged.connect(lambda: self._set_item("icon", self.icon_combo.currentData()))
        self.size_combo = QComboBox()
        for key, text in SIZE_NAMES:
            self.size_combo.addItem(text, key)
        self.size_combo.currentIndexChanged.connect(lambda: self._set_item("size", self.size_combo.currentData()))
        self.show_name = QCheckBox("Show the name")
        self.show_name.toggled.connect(lambda on: self._set_item("name", on))
        self.show_bar = QCheckBox("Show the bar")
        self.show_bar.toggled.connect(lambda on: self._set_item("bar", on))
        self.to_all = QPushButton("Use for all values")
        self.to_all.setToolTip("Same icon setting, text size, name and bar on every value")
        self.to_all.clicked.connect(self._copy_to_all)
        form.addRow("Icon", self.icon_combo)
        form.addRow("Text size", self.size_combo)
        form.addRow("", self.show_name)
        form.addRow("", self.show_bar)
        form.addRow("", self.to_all)
        self.item_form = QWidget()
        self.item_form.setLayout(form)
        lay.addWidget(self.item_form)
        box.setMinimumWidth(330)
        return box

    def _slider(self, key: str) -> tuple[QSlider, QLabel]:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        label = QLabel()
        label.setMinimumWidth(40)

        def moved(v: int) -> None:
            label.setText(f"{v} %")
            self._set(key, v)
        s.valueChanged.connect(moved)
        return s, label

    @staticmethod
    def _with_label(slider: QSlider, label: QLabel) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(slider, 1)
        row.addWidget(label)
        return w

    # -- loading the controls ----------------------------------------------
    def _load_widget(self) -> None:
        s = self.art.style
        self._loading = True
        self.fit.setChecked(s["fit"])
        self.width_spin.setValue(s["width"])
        self.height_spin.setValue(s["height"])
        self.width_spin.setEnabled(not s["fit"])
        self.height_spin.setEnabled(not s["fit"])
        for slider, label, key in ((self.background, self.background_label, "background"),
                                   (self.image_opacity, self.image_label, "image_opacity")):
            slider.setValue(s[key])
            label.setText(f"{s[key]} %")
        has_image = bool(s["image"])
        self.remove_image.setEnabled(has_image)
        self.image_opacity.setEnabled(has_image)
        self.choose_image.setText("Change image…" if has_image else "Choose image…")
        self.show_title.setChecked(s["title"])
        self.snap.setChecked(s["snap"])
        self._loading = False

    def _load_item(self, key: str) -> None:
        for b, need in self.align_buttons:
            b.setEnabled(len(self.canvas.chosen) >= need)
        entry = next((e for e in self.art.entries if e.id == key), None)
        self.item_hint.setVisible(not key)
        self.item_form.setVisible(bool(key))
        if not key:
            self.item_box.setTitle("Selected value")
            return
        o = self.art.opts(key)
        self._loading = True
        many = len(self.canvas.chosen)
        self.item_box.setTitle(f"{many} selected · changes go to all" if many > 1 else "CoreX title" if key == TITLE
                               else (entry.name if entry and entry.name else "Value"))
        self.icon_combo.setCurrentIndex(max(0, self.icon_combo.findData(o["icon"])))
        self.size_combo.setCurrentIndex(max(0, self.size_combo.findData(o["size"])))
        self.show_name.setChecked(o["name"])
        self.show_bar.setChecked(o["bar"])
        is_value = key != TITLE
        self.icon_combo.setEnabled(is_value)
        self.show_name.setEnabled(is_value)
        self.show_bar.setEnabled(is_value and entry is not None and entry.pct is not None)
        self.show_bar.setToolTip("" if self.show_bar.isEnabled() else "Only percentages have a bar")
        self.to_all.setEnabled(is_value)
        self._loading = False

    # -- changes -----------------------------------------------------------
    def _apply(self) -> None:
        self.overlay.relayout()
        self.canvas.refit()
        self._loading = True
        self.width_spin.setValue(round(self.canvas._size.width()))
        self.height_spin.setValue(round(self.canvas._size.height()))
        self.fit.setChecked(self.art.style["fit"])
        self.width_spin.setEnabled(not self.art.style["fit"])
        self.height_spin.setEnabled(not self.art.style["fit"])
        self._loading = False
        self.changed.emit()

    def _set(self, key: str, value) -> None:
        if self._loading:
            return
        self.art.style[key] = value
        if key == "title" and not value and self.canvas.current == TITLE:
            self.canvas.select("")
        self._apply()

    def _set_item(self, key: str, value) -> None:
        if self._loading or not self.canvas.current:
            return
        if len(self.canvas.chosen) > 1:
            for k in self.canvas.chosen:
                if k != TITLE or key == "size":
                    self.art.edit(k)[key] = value
            self._apply()
            return
        before = self.canvas._rects.get(self.canvas.current)
        self.art.edit(self.canvas.current)[key] = value
        after = self.art.layout()[0].get(self.canvas.current)
        if self.art.style["layout"] == "free" and before is not None and after is not None:
            # taller text: what sat under the value moves down with it instead of being covered
            grow = round(after.bottom() - before.bottom())
            for other, r in self.canvas._rects.items():
                it = self.art.style["items"].get(other)
                if grow and other != self.canvas.current and it and "y" in it and r.top() >= before.bottom() - 1:
                    it["y"] = max(0, it["y"] + grow)
        self._apply()

    def _copy_to_all(self) -> None:
        src = self.art.opts(self.canvas.current)
        for e in self.art.entries:
            it = self.art.edit(e.id)
            for key in ("icon", "size", "name", "bar"):
                it[key] = src[key]
        self._apply()

    def _on_fit(self, on: bool) -> None:
        if self._loading:
            return
        self.art.style["fit"] = on
        if on:
            tidy(self.art.style, self.canvas._rects)
        self._apply()

    def _on_size(self) -> None:
        if self._loading:
            return
        self.art.style["width"] = self.width_spin.value()
        self.art.style["height"] = self.height_spin.value()
        self._apply()

    def _gallery(self) -> None:
        dlg = GalleryDialog(self)
        if dlg.exec() and dlg.image is not None and not dlg.image.isNull():
            self._use_image(dlg.image)
        elif dlg.want_file:
            self._pick_image()

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a background image", "",
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Edit widget", "This file is not an image CoreX can read.")
            return
        self._use_image(img)

    def _use_image(self, img: QImage) -> None:
        if max(img.width(), img.height()) > 1600:          # a wallpaper-sized photo is far more than needed
            img = img.scaled(1600, 1600, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        target = config_dir() / BACKGROUND_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        if not img.save(str(target), "PNG"):
            QMessageBox.warning(self, "Edit widget", f"Could not save the image in {target.parent}.")
            return
        self.art.restyle()                                 # same file name, new picture
        self.art.style["image"] = BACKGROUND_FILE
        self._load_widget()
        self._apply()

    def _drop_image(self) -> None:
        self.art.style["image"] = ""
        try:
            (config_dir() / BACKGROUND_FILE).unlink()
        except OSError:
            pass
        self._load_widget()
        self._apply()

    def _reset(self) -> None:
        if QMessageBox.question(self, "Edit widget", "Put the widget back to its original look and layout?\n"
                                "The values you chose stay.") != QMessageBox.StandardButton.Yes:
            return
        locked = self.art.style["locked"]
        self.art.style.clear()
        self.art.style.update(copy.deepcopy(DEFAULT_STYLE))
        self.art.style["locked"] = locked
        self.canvas.select("")
        self._load_widget()
        self._apply()
