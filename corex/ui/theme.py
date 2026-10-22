"""Colours, fonts, stylesheet and line icons (SVG, no emoji fonts needed)."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from corex.core.model import DeviceKind, Kind

BG = "#11131a"
PANEL = "#181b24"
PANEL_HI = "#1f2330"
BORDER = "#2a2f3d"
TEXT = "#e6e8ee"
MUTED = "#8a90a2"
ACCENT = "#1d9e75"        # CoreX green
ACCENT_SOFT = "#16382f"

KIND_COLORS = {
    Kind.TEMP: "#ff7a59",
    Kind.LOAD: "#3fb6ff",
    Kind.CLOCK: "#b48cff",
    Kind.POWER: "#ffc94d",
    Kind.FAN: "#5ee0c0",
    Kind.FAN_PCT: "#5ee0c0",
    Kind.RATE: "#62d26f",
    Kind.DATA: "#9aa3b5",
    Kind.VOLT: "#f78fb3",
    Kind.CURRENT: "#f78fb3",
    Kind.INFO: MUTED,
}


def level_color(kind: str, value: float | None) -> str:
    """Warn colours for hot / busy readings; neutral text otherwise."""
    if value is None:
        return MUTED
    if kind == Kind.TEMP:
        return "#ff5d5d" if value >= 85 else "#ffb547" if value >= 70 else TEXT
    if kind == Kind.LOAD:
        return "#ff5d5d" if value >= 95 else "#ffb547" if value >= 80 else TEXT
    return TEXT


def mono_font(size: int = 10, bold: bool = False) -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSize(size)
    f.setBold(bold)
    return f


STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; }}
QToolTip {{ background: {PANEL_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QFrame#panel, QFrame#tile {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#tile:hover {{ border-color: #3a4152; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#h1 {{ font-size: 17pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 11pt; font-weight: 600; color: {MUTED}; }}
QListWidget#sidebar {{ background: {PANEL}; border: none; border-right: 1px solid {BORDER}; outline: 0; }}
QListWidget#sidebar::item {{ border-radius: 8px; margin: 2px 8px; }}
QListWidget#sidebar::item:selected {{ background: {ACCENT_SOFT}; }}
QListWidget#sidebar::item:hover:!selected {{ background: {PANEL_HI}; }}
QTreeWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; outline: 0;
               alternate-background-color: #1b1e28; }}
QTreeWidget::item {{ padding: 3px 0; }}
QTreeWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
                        padding: 6px 8px; font-weight: 600; }}
QPushButton, QToolButton, QComboBox {{ background: {PANEL_HI}; border: 1px solid {BORDER}; border-radius: 7px;
                                       padding: 5px 12px; }}
QPushButton:hover, QToolButton:hover, QComboBox:hover {{ border-color: {ACCENT}; }}
QPushButton:checked, QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QComboBox QAbstractItemView {{ background: {PANEL_HI}; selection-background-color: {ACCENT_SOFT}; }}
QMenu {{ background: {PANEL_HI}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
"""

# 24x24 line icons, drawn with stroke="currentColor" (replaced at render time)
_SVG = {
    DeviceKind.CPU: '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/>'
                    '<path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    DeviceKind.GPU: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="9" cy="12" r="3"/>'
                    '<circle cx="16" cy="12" r="3"/><path d="M5 18v3"/>',
    DeviceKind.MEMORY: '<rect x="2" y="7" width="20" height="10" rx="1.5"/><path d="M6 10v4M10 10v4M14 10v4M18 10v4'
                       'M5 17v3M19 17v3"/>',
    DeviceKind.STORAGE: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="12" cy="12" r="4"/>'
                        '<path d="M12 12h.01M17 17h.01"/>',
    DeviceKind.NETWORK: '<path d="M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/>'
                        '<path d="M12 19.5h.01"/>',
    DeviceKind.BOARD: '<rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="6" height="6" rx="1"/>'
                      '<path d="M16 7h2M16 10h2M7 16h11"/>',
    DeviceKind.SYSTEM: '<path d="M12 3v10"/><circle cx="12" cy="17" r="4"/><path d="M9 5h6"/>',
    DeviceKind.BATTERY: '<rect x="2" y="7" width="18" height="10" rx="2"/><path d="M22 11v2M6 10v4M10 10v4"/>',
    "overview": '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="5" rx="1.5"/>'
                '<rect x="13" y="10" width="8" height="11" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/>',
    "pin": '<path d="M9 3h6l-1 6 4 4H6l4-4z"/><path d="M12 13v8"/>',
    "widget": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 10h6M7 14h10"/>',
    "reset": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/>',
    "list": '<path d="M9 6h12M9 12h12M9 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
}


def icon_pixmap(name: str, color: str = TEXT, size: int = 20) -> QPixmap:
    body = _SVG.get(name, _SVG[DeviceKind.SYSTEM])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str = TEXT, size: int = 20) -> QIcon:
    return QIcon(icon_pixmap(name, color, size))


def qcolor(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c
