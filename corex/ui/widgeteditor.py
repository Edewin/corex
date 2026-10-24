"""The widget editor: live preview to drag values around, plus the look of the widget."""

from __future__ import annotations

import copy

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout,
                               QWidget)

from corex.app.settings import config_dir
from corex.ui import theme
from corex.ui.overlay import (BACKGROUND_FILE, DEFAULT_STYLE, GRID, ICON_CHOICES, MARGIN, MAX_SIZE, MIN_SIZE,
                              SIZE_NAMES, TITLE, Overlay)

PAD = 32                       # desktop shown around the widget in the preview
HANDLE = 10                    # resize grip, px


class _Canvas(QWidget):
    """The widget drawn on a fake desktop; drag values to place them, drag the corner to resize."""
    selected = Signal(str)
    changed = Signal()

    def __init__(self, overlay: Overlay, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.art = overlay.art
        self.current = ""
        self._grab: QPointF | None = None        # offset inside the dragged item
        self._resizing = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.refit()

    def refit(self) -> None:
        rects, size = self.art.layout()
        self._rects, self._size = rects, size
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
        if self._grab is not None and self.art.style["snap"]:
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.2))
            for x in range(0, round(self._size.width()) + 1, GRID):
                for y in range(0, round(self._size.height()) + 1, GRID):
                    p.drawPoint(x, y)
        self.art.paint(p, self._rects, self._size)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine))
        p.drawRect(QRectF(QPointF(0, 0), self._size).adjusted(-0.5, -0.5, 0.5, 0.5))
        r = self._rects.get(self.current)
        if r is not None:
            p.setPen(QPen(QColor(theme.ACCENT), 1.5))
            p.drawRoundedRect(r.adjusted(-4, -3, 4, 3), 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawRect(self._handle())

    def _handle(self) -> QRectF:
        return QRectF(self._size.width() - HANDLE / 2, self._size.height() - HANDLE / 2, HANDLE, HANDLE)

    # -- mouse & keys ------------------------------------------------------
    def _at(self, pos: QPointF) -> str | None:
        return next((k for k, r in self._rects.items() if k and r.adjusted(-4, -3, 4, 3).contains(pos)), None)

    def select(self, key: str) -> None:
        self.current = key
        self.selected.emit(key)
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position() - QPointF(PAD, PAD)
        if self._handle().adjusted(-4, -4, 4, 4).contains(pos):
            self._resizing = True
            return
        key = self._at(pos)
        self.select(key or "")
        if key:
            self._grab = pos - self._rects[key].topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        pos = e.position() - QPointF(PAD, PAD)
        style = self.art.style
        if self._resizing:
            style["fit"] = False
            style["width"] = max(MIN_SIZE[0], min(MAX_SIZE[0], self._snap(pos.x())))
            style["height"] = max(MIN_SIZE[1], min(MAX_SIZE[1], self._snap(pos.y())))
            self.changed.emit()
        elif self._grab is not None:
            self._to_free()
            top_left = pos - self._grab
            it = self.art.edit(self.current)
            it["x"] = max(0, min(MAX_SIZE[0], self._snap(top_left.x())))
            it["y"] = max(0, min(MAX_SIZE[1], self._snap(top_left.y())))
            self.changed.emit()
        elif self._handle().adjusted(-4, -4, 4, 4).contains(pos):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif self._at(pos):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        if self._grab is not None and self.art.style["fit"]:
            tidy(self.art.style, self._rects)
            self.changed.emit()
        self._grab = None
        self._resizing = False
        self.unsetCursor()
        self.update()

    def keyPressEvent(self, e):
        step = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        d = step.get(e.key())
        if d is None or not self.current:
            return super().keyPressEvent(e)
        n = GRID if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        self._to_free()
        it = self.art.edit(self.current)
        it["x"] = max(0, it["x"] + d[0] * n)
        it["y"] = max(0, it["y"] + d[1] * n)
        self.changed.emit()

    def _snap(self, v: float) -> int:
        return round(v / GRID) * GRID if self.art.style["snap"] else round(v)

    def _to_free(self) -> None:
        """First drag: every item keeps the place the list layout gave it."""
        if self.art.style["layout"] == "free":
            return
        self.art.style["layout"] = "free"
        for key, r in self._rects.items():
            if key:
                it = self.art.edit(key)
                it["x"], it["y"] = round(r.x()), round(r.y())


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
        hint = QLabel("Drag the values to place them · drag the corner square to resize · "
                      "arrow keys nudge (Shift: one grid step)")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        left = QVBoxLayout()
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
        self.choose_image.clicked.connect(self._pick_image)
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
        entry = next((e for e in self.art.entries if e.id == key), None)
        self.item_hint.setVisible(not key)
        self.item_form.setVisible(bool(key))
        if not key:
            self.item_box.setTitle("Selected value")
            return
        o = self.art.opts(key)
        self._loading = True
        self.item_box.setTitle("CoreX title" if key == TITLE else (entry.name if entry and entry.name else "Value"))
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

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a background image", "",
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Edit widget", "This file is not an image CoreX can read.")
            return
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
