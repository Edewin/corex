"""
corex/ui/widget.py

Always-on-top draggable overlay widget for CoreX.

NOTE: Do NOT set QT_QPA_PLATFORM here.
      It must be set in main.py before QApplication is created.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_PATH = Path.home() / ".config" / "corex" / "widget.json"

COLOR_GREEN  = "#4CAF50"
COLOR_YELLOW = "#FFC107"
COLOR_RED    = "#F44336"
COLOR_MUTED  = "#E0E0E0"


# ---------------------------------------------------------------------------
# Mono font helper
# ---------------------------------------------------------------------------

def _get_mono_font(size: int = 12) -> QFont:
    """Return the best available monospace font from a preferred list."""
    preferred = [
        "JetBrains Mono",
        "Fira Code",
        "Hack",
        "Ubuntu Mono",
        "DejaVu Sans Mono",
        "Monospace",
    ]
    available = QFontDatabase.families()
    for name in preferred:
        if name in available:
            return QFont(name, size)
    return QFont("Monospace", size)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _value_color(unit: str, value: float) -> str:
    """Return a hex colour string based on unit and magnitude."""
    if unit == "°C":
        if value < 60:
            return COLOR_GREEN
        if value <= 80:
            return COLOR_YELLOW
        return COLOR_RED
    if unit == "%":
        if value < 60:
            return COLOR_GREEN
        if value <= 85:
            return COLOR_YELLOW
        return COLOR_RED
    if unit == "RPM":
        return COLOR_GREEN if value > 0 else COLOR_RED
    return COLOR_MUTED


def _format_value(value: float, unit: str) -> str:
    """Format a metric value + unit into a display string."""
    if unit in ("°C", "%", "RPM", "GHz", "MHz", "W", "V"):
        return f"{value:.1f}{unit}"
    # MB/s, GB/s, etc. — keep unit separate with a space
    return f"{value:.3f} {unit}"


# ---------------------------------------------------------------------------
# CoreXWidget
# ---------------------------------------------------------------------------

class CoreXWidget(QWidget):
    """
    Frameless, always-on-top, translucent overlay widget.

    Signals
    -------
    open_dashboard
        Emitted when the user selects "Open dashboard" from the context menu.
    quit_app
        Emitted when the user selects "Quit CoreX" from the context menu.
    """

    open_dashboard = pyqtSignal()
    quit_app       = pyqtSignal()

    # Internal state
    _drag_offset: Optional[QPoint]
    _metric_rows: Dict[str, Dict[str, QLabel]]   # name → {icon, name, value}

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._drag_offset = None
        self._metric_rows = {}

        # ── Window flags ───────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(120, 60)
        self.resize(300, 200)

        # ── Context menu ───────────────────────────────────────────────────
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # ── Build layout ───────────────────────────────────────────────────
        self._build_layout()

        # ── Restore saved position ─────────────────────────────────────────
        self.load_config()

    # -----------------------------------------------------------------------
    # Layout construction
    # -----------------------------------------------------------------------

    def _build_layout(self) -> None:
        """Construct the title bar and metrics area."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 10)
        outer.setSpacing(6)

        # ── Title bar ──────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        lbl_title = QLabel("CoreX")
        font_title = _get_mono_font(10)
        font_title.setBold(True)
        lbl_title.setFont(font_title)
        lbl_title.setStyleSheet("color: #1D9E75;")

        hostname = socket.gethostname()
        lbl_host = QLabel(hostname)
        lbl_host.setFont(_get_mono_font(10))
        lbl_host.setStyleSheet("color: #666688;")

        spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        btn_close = QPushButton("×")
        btn_close.setFlat(True)
        btn_close.setFixedSize(18, 18)
        btn_close.setStyleSheet(
            "QPushButton { color: #888899; font-size: 14px; border: none; }"
            "QPushButton:hover { color: #F44336; }"
        )
        btn_close.clicked.connect(self.hide)

        title_row.addWidget(lbl_title)
        title_row.addWidget(lbl_host)
        title_row.addItem(spacer)
        title_row.addWidget(btn_close)

        outer.addLayout(title_row)

        # ── Metrics area ───────────────────────────────────────────────────
        self._metrics_layout = QVBoxLayout()
        self._metrics_layout.setSpacing(3)
        self._metrics_layout.setContentsMargins(0, 0, 0, 0)

        outer.addLayout(self._metrics_layout)
        outer.addStretch(1)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def update_metrics(self, summary: Dict[str, Any]) -> None:
        """
        Update the displayed metrics.

        Parameters
        ----------
        summary:
            Dict mapping metric name → dict with keys:
              "value"          : float
              "unit"           : str
              "component_icon" : str  (emoji)
              "group_icon"     : str  (emoji)

        On the first call, metric rows are created dynamically.
        On subsequent calls, only the value label text and colour are updated.
        """
        for metric_name, info in summary.items():
            value          = float(info.get("value", 0.0))
            unit           = str(info.get("unit", ""))
            component_icon = str(info.get("component_icon", ""))
            group_icon     = str(info.get("group_icon", ""))

            if metric_name not in self._metric_rows:
                self._create_metric_row(metric_name, component_icon, group_icon)

            row = self._metric_rows[metric_name]
            color = _value_color(unit, value)
            row["value"].setText(_format_value(value, unit))
            row["value"].setStyleSheet(f"color: {color};")

        # Resize height to fit content
        self.adjustSize()

    # -----------------------------------------------------------------------
    # Row factory
    # -----------------------------------------------------------------------

    def _create_metric_row(
        self,
        metric_name: str,
        component_icon: str,
        group_icon: str,
    ) -> None:
        """Create and register a new metric row in the metrics layout."""
        row_layout = QHBoxLayout()
        row_layout.setSpacing(4)
        row_layout.setContentsMargins(0, 0, 0, 0)

        # Icon label — component + group emoji
        icon_label = QLabel(f"{component_icon}{group_icon}")
        icon_label.setFixedWidth(36)
        icon_label.setStyleSheet("font-size: 12px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Name label
        name_label = QLabel(metric_name)
        name_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Value label — placeholder until first update
        value_label = QLabel("—")
        value_label.setFixedWidth(80)
        value_label.setFont(_get_mono_font(12))
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setStyleSheet(f"color: {COLOR_MUTED};")

        row_layout.addWidget(icon_label)
        row_layout.addWidget(name_label)
        row_layout.addWidget(value_label)

        self._metrics_layout.addLayout(row_layout)

        self._metric_rows[metric_name] = {
            "icon":  icon_label,
            "name":  name_label,
            "value": value_label,
        }

    # -----------------------------------------------------------------------
    # Paint — rounded translucent background
    # -----------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        # Fill
        painter.fillPath(path, QBrush(QColor(15, 15, 25, 210)))

        # Border
        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

    # -----------------------------------------------------------------------
    # Drag behaviour
    # -----------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.save_config()
        super().mouseReleaseEvent(event)

    # -----------------------------------------------------------------------
    # Context menu
    # -----------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self._on_context_menu(event.pos())

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #e0e0e0;
                border: 1px solid #3a3a6a;
                font-size: 12px;
            }
            QMenu::item {
                padding: 5px 18px;
            }
            QMenu::item:selected {
                background-color: #2a2a5a;
            }
            QMenu::separator {
                height: 1px;
                background: #3a3a6a;
                margin: 3px 0;
            }
        """)

        act_configure  = menu.addAction("⚙️ Configure metrics...")
        act_copy       = menu.addAction("📋 Copy snapshot")
        menu.addSeparator()
        act_dashboard  = menu.addAction("🖥️ Open dashboard")
        menu.addSeparator()
        act_quit       = menu.addAction("❌ Quit CoreX")

        # Map pos (widget-local) to global
        global_pos = self.mapToGlobal(pos)
        action = menu.exec(global_pos)

        if action == act_configure:
            self._show_configure_stub()
        elif action == act_copy:
            self._copy_snapshot()
        elif action == act_dashboard:
            self.open_dashboard.emit()
        elif action == act_quit:
            self.quit_app.emit()

    # -----------------------------------------------------------------------
    # Context menu handlers
    # -----------------------------------------------------------------------

    def _show_configure_stub(self) -> None:
        """Placeholder for the metric picker dialog."""
        dlg = QMessageBox(self)
        dlg.setWindowTitle("CoreX — Configure metrics")
        dlg.setText("Coming soon")
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.exec()

    def _copy_snapshot(self) -> None:
        """Copy all current metric values to the clipboard as plain text."""
        lines: list[str] = []
        for metric_name, row in self._metric_rows.items():
            value_text = row["value"].text()
            lines.append(f"{metric_name}: {value_text}")
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)

    # -----------------------------------------------------------------------
    # Config persistence
    # -----------------------------------------------------------------------

    def load_config(self) -> None:
        """Restore widget position from ~/.config/corex/widget.json."""
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text())
            x = int(data.get("x", self.x()))
            y = int(data.get("y", self.y()))
            self.move(x, y)
        except Exception:
            pass  # Silently ignore corrupt config

    def save_config(self) -> None:
        """Persist widget position to ~/.config/corex/widget.json."""
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: Dict[str, Any] = {}
        if CONFIG_PATH.exists():
            try:
                existing = json.loads(CONFIG_PATH.read_text())
            except Exception:
                pass
        existing["x"] = self.x()
        existing["y"] = self.y()
        try:
            CONFIG_PATH.write_text(json.dumps(existing, indent=2))
        except Exception:
            pass
