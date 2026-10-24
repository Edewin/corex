"""Backgrounds for the widget: pictures shipped with CoreX, a few drawn here, or the user's own file."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton, \
    QVBoxLayout, QWidget

from corex.ui import theme

KIT_DIR = Path(__file__).resolve().parent.parent / "assets" / "backgrounds"
W, H = 1280, 720               # drawn backgrounds
THUMB = QSize(200, 112)


def _sky(p: QPainter, *stops: tuple[float, str]) -> None:
    g = QLinearGradient(0, 0, 0, H)
    for at, color in stops:
        g.setColorAt(at, QColor(color))
    p.fillRect(0, 0, W, H, g)


def _ridge(rng: random.Random, base: float, height: float, step: int = 40) -> QPainterPath:
    """A mountain line from left to right, closed along the bottom."""
    path = QPainterPath(QPointF(0, H))
    y = base - rng.random() * height
    for x in range(0, W + step, step):
        y = min(base, max(base - height, y + rng.uniform(-height, height) * 0.35))
        path.lineTo(x, y)
    path.lineTo(W, H)
    path.closeSubpath()
    return path


def _dusk(p: QPainter, rng: random.Random) -> None:
    _sky(p, (0, "#1d1b3a"), (0.45, "#6b3a6e"), (0.75, "#e0795a"), (1, "#f6c27a"))
    sun = QRadialGradient(QPointF(W * 0.68, H * 0.62), 220)
    sun.setColorAt(0, QColor(255, 226, 170, 255))
    sun.setColorAt(0.18, QColor(255, 200, 140, 230))
    sun.setColorAt(1, QColor(255, 160, 110, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(sun)
    p.drawEllipse(QPointF(W * 0.68, H * 0.62), 220, 220)
    for i, color in enumerate(("#8a4a74", "#5e3460", "#3c2347", "#21142c")):
        p.setBrush(QColor(color))
        p.drawPath(_ridge(rng, H * (0.62 + i * 0.1), 120 - i * 18, 48 - i * 6))


def _aurora(p: QPainter, rng: random.Random) -> None:
    _sky(p, (0, "#030914"), (0.6, "#0a1f33"), (1, "#0f2a2e"))
    _stars(p, rng, 160, H * 0.7)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for band, (color, y0) in enumerate((("#3ef0a8", 0.30), ("#2ad4c8", 0.38), ("#8a6cf0", 0.24))):
        phase = rng.random() * 6.28
        for k in range(26):                         # many soft strokes make a glowing curtain
            c = QColor(color)
            c.setAlpha(max(4, 34 - k))
            p.setPen(QPen(c, 6 + k * 2.2))
            path = QPainterPath()
            for x in range(-40, W + 41, 20):
                y = H * y0 + math.sin(x / 210 + phase) * 60 + math.sin(x / 77 + band) * 18 + k * 3
                path.lineTo(x, y) if x > -40 else path.moveTo(x, y)
            p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#02060c"))
    p.drawPath(_ridge(rng, H * 0.92, 90, 36))


def _stars(p: QPainter, rng: random.Random, count: int, bottom: float) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(count):
        c = QColor(255, 255, 255, rng.randint(60, 230))
        p.setBrush(c)
        r = rng.choice((0.7, 0.9, 1.1, 1.5, 2.0))
        p.drawEllipse(QPointF(rng.random() * W, rng.random() * bottom), r, r)


def _night(p: QPainter, rng: random.Random) -> None:
    _sky(p, (0, "#05060f"), (0.7, "#141a3a"), (1, "#28305c"))
    band = QLinearGradient(0, H, W, 0)                # the milky way, corner to corner
    band.setColorAt(0.3, QColor(160, 170, 255, 0))
    band.setColorAt(0.5, QColor(190, 180, 255, 60))
    band.setColorAt(0.7, QColor(160, 170, 255, 0))
    p.fillRect(0, 0, W, H, band)
    _stars(p, rng, 520, H)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#070810"))
    p.drawPath(_ridge(rng, H * 0.95, 70, 30))


def _ocean(p: QPainter, rng: random.Random) -> None:
    _sky(p, (0, "#8ed1f0"), (0.42, "#d9f1fb"), (0.43, "#2f8fbf"), (1, "#0b3557"))
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(9):
        y0 = H * 0.45 + i * i * 7 + i * 14
        c = QColor("#cfefff")
        c.setAlpha(30 + i * 6)
        p.setBrush(c)
        path = QPainterPath(QPointF(0, y0))
        phase = rng.random() * 6.28
        for x in range(0, W + 20, 20):
            path.lineTo(x, y0 + math.sin(x / (60 + i * 12) + phase) * (2 + i * 1.4))
        for x in range(W, -20, -20):
            path.lineTo(x, y0 + 3 + i * 0.8 + math.sin(x / (60 + i * 12) + phase) * (2 + i * 1.4))
        p.drawPath(path)


def _circuit(p: QPainter, rng: random.Random) -> None:
    _sky(p, (0, "#05100d"), (1, "#0b1f1a"))
    glow = QRadialGradient(QPointF(W / 2, H / 2), W * 0.55)
    glow.setColorAt(0, QColor(46, 204, 140, 70))
    glow.setColorAt(1, QColor(46, 204, 140, 0))
    p.fillRect(0, 0, W, H, glow)
    step = 40
    for _ in range(90):                       # traces on a grid, with right-angle and 45° turns
        x, y = rng.randrange(0, W // step) * step, rng.randrange(0, H // step) * step
        alpha = rng.randint(50, 170)
        p.setPen(QPen(QColor(62, 240, 168, alpha), rng.choice((1.5, 2, 3))))
        path = QPainterPath(QPointF(x, y))
        for _ in range(rng.randint(2, 6)):
            dx, dy = rng.choice(((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (1, -1)))
            n = rng.randint(1, 4)
            x, y = x + dx * step * n, y + dy * step * n
            path.lineTo(x, y)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setBrush(QColor(62, 240, 168, alpha))
        p.drawEllipse(QPointF(x, y), 4, 4)


DRAWN = (("dusk", "Dusk mountains", _dusk), ("aurora", "Aurora", _aurora), ("night", "Starry night", _night),
         ("ocean", "Calm sea", _ocean), ("circuit", "Circuit", _circuit))


def drawn(name: str) -> QImage:
    img = QImage(W, H, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    fn = next(f for key, _, f in DRAWN if key == name)
    fn(p, random.Random(name))                # the same picture every time
    p.end()
    return img


def choices() -> list[tuple[str, str]]:
    """(key, title): "kit:<file>" for the pictures shipped with CoreX, "drawn:<name>" for the drawn ones."""
    kit = sorted(KIT_DIR.glob("*.jpg"), key=lambda f: (not f.stem.startswith("mountain"), f.stem))
    out = [(f"kit:{f.name}", f.stem.replace("-", " ").capitalize()) for f in kit]
    return out + [(f"drawn:{key}", title) for key, title, _ in DRAWN]


def load(key: str) -> QImage:
    kind, _, name = key.partition(":")
    return QImage(str(KIT_DIR / name)) if kind == "kit" else drawn(name)


class GalleryDialog(QDialog):
    """Pick a background: image is the picture chosen, want_file asks for the user's own file instead."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Widget background")
        self.image: QImage | None = None
        self.want_file = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Choose a background")
        title.setObjectName("h2")
        lay.addWidget(title)
        hint = QLabel("The picture fills the widget; its opacity is set in the editor.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        host = QWidget()
        grid = QGridLayout(host)
        grid.setSpacing(12)
        tiles = choices()
        for i, (key, name) in enumerate(tiles):
            grid.addWidget(self._tile(name, self._thumb(load(key)), lambda _=False, k=key: self._pick(k)),
                           i // 3, i % 3)
        own = QPixmap(THUMB)
        own.fill(QColor(theme.PANEL_HI))
        p = QPainter(own)
        p.drawPixmap(THUMB.width() // 2 - 18, THUMB.height() // 2 - 18, theme.icon_pixmap("folder", theme.MUTED, 36))
        p.end()
        n = len(tiles)
        grid.addWidget(self._tile("From file…", own, self._own), n // 3, n % 3)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        scroll.setMinimumSize(3 * (THUMB.width() + 28) + 20, 560)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)

    @staticmethod
    def _thumb(img: QImage) -> QPixmap:
        img = img.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        x, y = (img.width() - THUMB.width()) // 2, (img.height() - THUMB.height()) // 2
        return QPixmap.fromImage(img.copy(x, y, THUMB.width(), THUMB.height()))

    @staticmethod
    def _tile(name: str, pm: QPixmap, on_click) -> QToolButton:
        b = QToolButton()
        b.setIcon(pm)
        b.setIconSize(THUMB)
        b.setText(name)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QToolButton {{ border: 2px solid transparent; border-radius: 8px; padding: 4px; }}"
                        f"QToolButton:hover {{ border-color: {theme.ACCENT}; background: {theme.PANEL_HI}; }}")
        b.clicked.connect(on_click)
        return b

    def _pick(self, key: str) -> None:
        self.image = load(key)
        self.accept()

    def _own(self) -> None:
        self.want_file = True
        self.reject()

