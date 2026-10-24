"""Colours, fonts, stylesheet and line icons (SVG, no emoji fonts needed)."""

from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

from corex.core.model import DeviceKind, Kind

THEMES = ("dark", "light", "system")

_PALETTES = {
    "dark": dict(BG="#11131a", PANEL="#181b24", PANEL_HI="#1f2330", BORDER="#2a2f3d", BORDER_HI="#3a4152",
                 ALT_ROW="#1b1e28", TEXT="#e6e8ee", MUTED="#8a90a2", ACCENT="#1d9e75", ACCENT_SOFT="#16382f",
                 WARN="#ffb547", HOT="#ff5d5d",
                 kinds=("#ff7a59", "#3fb6ff", "#b48cff", "#ffc94d", "#5ee0c0", "#62d26f", "#9aa3b5", "#f78fb3")),
    "light": dict(BG="#f3f4f7", PANEL="#ffffff", PANEL_HI="#eceef3", BORDER="#d8dbe3", BORDER_HI="#b9bfcc",
                  ALT_ROW="#f7f8fa", TEXT="#1b1e26", MUTED="#687083", ACCENT="#16936c", ACCENT_SOFT="#d5efe5",
                  WARN="#c97a00", HOT="#d93636",
                  kinds=("#e2552f", "#1d86d0", "#7d52e6", "#b88700", "#119a7d", "#2c9a3a", "#667085", "#cc4f82")),
}

# filled in by apply(); dark until then
BG = PANEL = PANEL_HI = BORDER = BORDER_HI = ALT_ROW = TEXT = MUTED = ACCENT = ACCENT_SOFT = WARN = HOT = ""
KIND_COLORS: dict[str, str] = {}
STYLESHEET = ""
alerting: set[str] = set()     # reading ids over their alert threshold right now


def resolve(mode: str) -> str:
    """'system' -> 'dark' / 'light' from the desktop's colour scheme."""
    if mode != "system":
        return mode if mode in _PALETTES else "dark"
    from PySide6.QtGui import QGuiApplication
    hints = QGuiApplication.styleHints() if QGuiApplication.instance() else None
    if hints is not None and hints.colorScheme() == Qt.ColorScheme.Light:
        return "light"
    return "dark"


def apply(mode: str) -> str:
    """Switch every colour (and the stylesheet) to the given theme; returns 'dark' or 'light'."""
    global KIND_COLORS, STYLESHEET
    name = resolve(mode)
    pal = dict(_PALETTES[name])
    temp, load, clock, power, fan, rate, data, volt = pal.pop("kinds")
    globals().update(pal)
    KIND_COLORS = {Kind.TEMP: temp, Kind.LOAD: load, Kind.CLOCK: clock, Kind.POWER: power, Kind.FAN: fan,
                   Kind.FAN_PCT: fan, Kind.RATE: rate, Kind.DATA: data, Kind.VOLT: volt, Kind.CURRENT: volt,
                   Kind.INFO: pal["MUTED"]}
    STYLESHEET = _stylesheet(*_arrows(name))
    return name


def _arrows(name: str) -> tuple[str, str]:
    """Up / down chevrons as SVG files: stylesheets can only take images from files."""
    folder = os.path.join(tempfile.gettempdir(), f"corex-{os.getuid()}")
    os.makedirs(folder, exist_ok=True)
    paths = []
    for which, d in (("up", "M3 8l4-4 4 4"), ("down", "M3 5l4 4 4-4")):
        path = os.path.join(folder, f"{which}-{name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 14 14"><path d="{d}" fill="none" '
                    f'stroke="{MUTED}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        paths.append(path.replace(os.sep, "/"))
    return paths[0], paths[1]


def palette() -> QPalette:
    """Qt palette for what the stylesheet does not draw (arrows, check marks, spin buttons)."""
    pal = QPalette()
    role = QPalette.ColorRole
    for r, c in ((role.Window, BG), (role.WindowText, TEXT), (role.Base, PANEL), (role.AlternateBase, ALT_ROW),
                 (role.Text, TEXT), (role.Button, PANEL_HI), (role.ButtonText, TEXT), (role.ToolTipBase, PANEL_HI),
                 (role.ToolTipText, TEXT), (role.Highlight, ACCENT), (role.HighlightedText, "#ffffff"),
                 (role.PlaceholderText, MUTED), (role.Mid, BORDER), (role.Midlight, BORDER_HI),
                 (role.Dark, BORDER), (role.Light, PANEL_HI), (role.Link, ACCENT)):
        pal.setColor(r, QColor(c))
    pal.setColor(QPalette.ColorGroup.Disabled, role.Text, QColor(MUTED))
    pal.setColor(QPalette.ColorGroup.Disabled, role.ButtonText, QColor(MUTED))
    return pal


def level_color(kind: str, value: float | None, reading_id: str | None = None) -> str:
    """Warn colours for hot / busy readings and readings over their alert; neutral text otherwise."""
    if value is None:
        return MUTED
    if reading_id is not None and reading_id in alerting:
        return HOT
    if kind == Kind.TEMP:
        return HOT if value >= 85 else WARN if value >= 70 else TEXT
    if kind == Kind.LOAD:
        return HOT if value >= 95 else WARN if value >= 80 else TEXT
    return TEXT


def mono_font(size: int = 10, bold: bool = False) -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSize(size)
    f.setBold(bold)
    return f


def _stylesheet(up: str, down: str) -> str:
    return f"""
QWidget {{ background: {BG}; color: {TEXT}; }}
QToolTip {{ background: {PANEL_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QFrame#panel, QFrame#tile {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#tile:hover {{ border-color: {BORDER_HI}; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#h1 {{ font-size: 17pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 11pt; font-weight: 600; color: {MUTED}; }}
QListWidget#sidebar {{ background: {PANEL}; border: none; border-right: 1px solid {BORDER}; outline: 0; }}
QListWidget#sidebar::item {{ border-radius: 8px; margin: 2px 8px; }}
QListWidget#sidebar::item:selected {{ background: {ACCENT_SOFT}; }}
QListWidget#sidebar::item:hover:!selected {{ background: {PANEL_HI}; }}
QTreeWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; outline: 0;
               alternate-background-color: {ALT_ROW}; }}
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
QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
                                      padding: 4px 6px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 6px 14px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom-color: {ACCENT}; }}
QTabWidget::pane {{ border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({down}); width: 12px; height: 12px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
                                                 width: 20px; border: none; background: transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
                                                     width: 20px; border: none; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
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
    "hybrid": '<path d="M3 6h6M3 12h6M3 18h6"/><rect x="12" y="4" width="9" height="16" rx="1.5"/>'
              '<path d="M14 15l2-3 1.5 1.5 2-3"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "list": '<path d="M9 6h12M9 12h12M9 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/>',
    "report": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h7"/>',
    "theme": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/>',
    # sensor groups, chosen by the kind of their readings
    Kind.TEMP: '<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z"/><path d="M12 9v8"/>',
    Kind.FAN: '<circle cx="12" cy="12" r="2"/><path d="M12 10c-1-3 0-6 3-7 2 2 1 5-1 7M14 12c3-1 6 0 7 3-2 2-5 1-7-1'
              'M12 14c1 3 0 6-3 7-2-2-1-5 1-7M10 12c-3 1-6 0-7-3 2-2 5-1 7 1"/>',
    Kind.VOLT: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    Kind.CURRENT: '<path d="M2 12h3l3-7 4 14 4-10 2 3h4"/>',
    Kind.POWER: '<path d="M12 3c1 4 6 6 6 11a6 6 0 0 1-12 0c0-3 2-4 3-6 1 2 2 3 3 3 0-3-1-5 0-8z"/>',
    Kind.LOAD: '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-6"/><path d="M4 18h16"/>',
    Kind.CLOCK: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    Kind.DATA: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6'
               'M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    Kind.RATE: '<path d="M8 20V4M4 8l4-4 4 4M16 4v16M12 16l4 4 4-4"/>',
    Kind.INFO: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
}


def icon_pixmap(name: str, color: str | None = None, size: int = 20) -> QPixmap:
    color = color or TEXT
    body = _SVG.get(name, _SVG[DeviceKind.SYSTEM])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" color="{color}" stroke="{color}" '
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


def icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    return QIcon(icon_pixmap(name, color, size))


def qcolor(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


apply("dark")
