"""
corex/ui/hardware_tree_widget.py

HWiNFO-style QTreeWidget that displays a HardwareTree with 3 levels:
  Level 1 — HardwareComponent  (bold, coloured background)
  Level 2 — SensorGroup        (italic, no values)
  Level 3 — Sensor             (coloured value, min, max)

Columns: Sensor | Current | Min | Max
"""

from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QBrush, QClipboard
from PyQt6.QtWidgets import (
    QApplication,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QMenu,
)

from corex.models import HardwareTree, HardwareComponent, SensorGroup, Sensor


# ---------------------------------------------------------------------------
# Colour tables
# ---------------------------------------------------------------------------

COMPONENT_BG: Dict[str, str] = {
    "CPU":         "#1a2744",
    "GPU":         "#1a2e1a",
    "Motherboard": "#2a2a1a",
    "Storage":     "#1a1a2e",
    "System":      "#222233",
    "Network":     "#2a1a2a",
    "Battery":     "#2a2a1a",
}

DEFAULT_BG = "#1e1e2e"


def _value_color(unit: str, value: float) -> str:
    """Return a hex colour string for a sensor value based on unit and magnitude."""
    if unit == "°C":
        if value < 60:
            return "#4CAF50"
        if value <= 80:
            return "#FFC107"
        return "#F44336"
    if unit == "%":
        if value < 60:
            return "#4CAF50"
        if value <= 85:
            return "#FFC107"
        return "#F44336"
    if unit == "RPM":
        return "#4CAF50" if value > 0 else "#F44336"
    return "#E0E0E0"


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
# Helper: format a float for display
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    return f"{v:.1f}"


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class HardwareTreeWidget(QTreeWidget):
    """
    HWiNFO-style hardware sensor tree.

    Signals
    -------
    add_to_widget(sensor_id: str)
        Emitted when the user selects "Add to widget" from the right-click menu.
    """

    add_to_widget = pyqtSignal(str)

    # Map sensor_id → QTreeWidgetItem (Level 3 only)
    _items: Dict[str, QTreeWidgetItem]

    # Map sensor_id → Sensor reference (kept for context-menu access)
    _sensors: Dict[str, Sensor]

    # Map component name → Level-1 QTreeWidgetItem (for collapse tracking)
    _comp_items: Dict[str, QTreeWidgetItem]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._items = {}
        self._sensors = {}
        self._comp_items = {}

        # ── columns ────────────────────────────────────────────────────────
        self.setColumnCount(4)
        self.setHeaderLabels(["Sensor", "Current", "Min", "Max"])

        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        self.setColumnWidth(0, 240)
        self.setColumnWidth(1, 90)
        self.setColumnWidth(2, 90)
        self.setColumnWidth(3, 90)

        # ── behaviour ──────────────────────────────────────────────────────
        self.setUniformRowHeights(False)
        self.setAnimated(False)          # avoids flicker on expand/collapse
        self.setIndentation(16)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemDoubleClicked.connect(self._on_double_click)

        # ── dark theme ─────────────────────────────────────────────────────
        self.setStyleSheet("""
            QTreeWidget {
              background-color: #1a1a2e;
              color: #e0e0e0;
              border: none;
              font-size: 13px;
            }
            QTreeWidget::item:selected {
              background-color: #2a2a5a;
            }
            QHeaderView::section {
              background-color: #2a2a4a;
              color: #e0e0e0;
              padding: 4px;
              border: 1px solid #3a3a6a;
              font-weight: bold;
            }
        """)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def build_tree(self, tree: HardwareTree) -> None:
        """
        Called ONCE on first data received.
        Creates all QTreeWidgetItem objects and stores Level-3 items in
        self._items keyed by sensor_id.
        All Level-1 items are expanded by default.
        """
        self.clear()
        self._items.clear()
        self._sensors.clear()
        self._comp_items.clear()

        for component in tree.components:
            comp_item = self._make_component_item(component)
            self.addTopLevelItem(comp_item)
            self._comp_items[component.name] = comp_item

            for group in component.groups:
                group_item = self._make_group_item(group)
                comp_item.addChild(group_item)

                for sensor in group.sensors:
                    sensor_item = self._make_sensor_item(sensor)
                    group_item.addChild(sensor_item)
                    self._items[sensor.sensor_id] = sensor_item
                    self._sensors[sensor.sensor_id] = sensor

            comp_item.setExpanded(True)

    def update_tree(self, tree: HardwareTree) -> None:
        """
        Called every ~1 second.
        NEVER clears or rebuilds the tree — only updates text of existing items.
        This prevents flicker.
        """
        for component in tree.components:
            # Refresh the Level-1 label (collapse indicator may have changed
            # externally, but we keep the collapsed state from the widget itself)
            if component.name in self._comp_items:
                comp_item = self._comp_items[component.name]
                is_expanded = comp_item.isExpanded()
                arrow = "▲" if is_expanded else "▼"
                comp_item.setText(0, f"{component.icon} {component.name}  [{arrow}]")

            for group in component.groups:
                for sensor in group.sensors:
                    sid = sensor.sensor_id
                    if sid not in self._items:
                        continue
                    item = self._items[sid]
                    color = _value_color(sensor.unit, sensor.value)
                    brush = QBrush(QColor(color))
                    for col in range(1, 4):
                        item.setForeground(col, brush)
                    item.setText(1, _fmt(sensor.value))
                    item.setText(2, _fmt(sensor.min_val))
                    item.setText(3, _fmt(sensor.max_val))

    # -----------------------------------------------------------------------
    # Item factories
    # -----------------------------------------------------------------------

    def _make_component_item(self, component: HardwareComponent) -> QTreeWidgetItem:
        """Level 1 — bold, coloured background, collapse arrow."""
        arrow = "▼" if component.collapsed else "▲"
        label = f"{component.icon} {component.name}  [{arrow}]"

        item = QTreeWidgetItem([label, "", "", ""])

        # Bold font
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        for col in range(4):
            item.setFont(col, font)

        # Background colour
        bg_hex = COMPONENT_BG.get(component.component_type, DEFAULT_BG)
        bg = QBrush(QColor(bg_hex))
        for col in range(4):
            item.setBackground(col, bg)

        # Foreground
        fg = QBrush(QColor("#e0e0e0"))
        for col in range(4):
            item.setForeground(col, fg)

        # Tag so we can identify level in event handlers
        item.setData(0, Qt.ItemDataRole.UserRole, ("component", component.name))

        return item

    def _make_group_item(self, group: SensorGroup) -> QTreeWidgetItem:
        """Level 2 — italic, no value columns."""
        label = f"{group.icon} {group.name}"
        item = QTreeWidgetItem([label, "", "", ""])

        font = QFont()
        font.setItalic(True)
        font.setPointSize(10)
        for col in range(4):
            item.setFont(col, font)

        fg = QBrush(QColor("#b0b0c0"))
        for col in range(4):
            item.setForeground(col, fg)

        item.setData(0, Qt.ItemDataRole.UserRole, ("group", group.name))

        return item

    def _make_sensor_item(self, sensor: Sensor) -> QTreeWidgetItem:
        """Level 3 — coloured value, min, max."""
        # Pick an emoji prefix based on unit
        icon = _sensor_icon(sensor.unit)
        label = f"{icon} {sensor.label}"

        color = _value_color(sensor.unit, sensor.value)
        brush = QBrush(QColor(color))

        item = QTreeWidgetItem([
            label,
            _fmt(sensor.value),
            _fmt(sensor.min_val),
            _fmt(sensor.max_val),
        ])

        label_font = QFont()
        label_font.setPointSize(10)
        item.setFont(0, label_font)

        # Mono font for value columns (Current, Min, Max)
        mono_font = _get_mono_font(10)
        for col in range(1, 4):
            item.setFont(col, mono_font)

        # Colour the value columns
        for col in range(1, 4):
            item.setForeground(col, brush)

        # Label column — slightly dimmer white
        item.setForeground(0, QBrush(QColor("#d0d0d0")))

        # Tag with sensor_id for context menu
        item.setData(0, Qt.ItemDataRole.UserRole, ("sensor", sensor.sensor_id))

        return item

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        """Toggle collapse/expand for Level-1 items on double-click."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None or data[0] != "component":
            return

        comp_name = data[1]
        is_expanded = item.isExpanded()

        # Toggle
        if is_expanded:
            item.setExpanded(False)
            arrow = "▼"
        else:
            item.setExpanded(True)
            arrow = "▲"

        # Update label text to reflect new state
        # Reconstruct label from stored comp_items key
        # We need the icon — extract it from current text
        current_text = item.text(0)
        # Strip old arrow suffix and rebuild
        base = current_text.rsplit("  [", 1)[0]
        item.setText(0, f"{base}  [{arrow}]")

    def _on_context_menu(self, pos) -> None:
        """Right-click context menu for Level-3 sensor items."""
        item = self.itemAt(pos)
        if item is None:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None or data[0] != "sensor":
            return

        sensor_id = data[1]
        sensor = self._sensors.get(sensor_id)
        if sensor is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a4a;
                color: #e0e0e0;
                border: 1px solid #3a3a6a;
            }
            QMenu::item:selected {
                background-color: #3a3a6a;
            }
        """)

        copy_value_action = menu.addAction("📋 Copy value")
        copy_label_action = menu.addAction("📋 Copy label + value")
        menu.addSeparator()
        add_widget_action = menu.addAction("📌 Add to widget")

        action = menu.exec(self.viewport().mapToGlobal(pos))

        if action == copy_value_action:
            clipboard = QApplication.clipboard()
            clipboard.setText(str(sensor.value))

        elif action == copy_label_action:
            clipboard = QApplication.clipboard()
            clipboard.setText(f"{sensor.label}: {sensor.value} {sensor.unit}")

        elif action == add_widget_action:
            self.add_to_widget.emit(sensor_id)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _sensor_icon(unit: str) -> str:
    """Return a small emoji that matches the sensor unit."""
    mapping = {
        "°C":   "🌡️",
        "%":    "📊",
        "RPM":  "🌀",
        "GHz":  "⚡",
        "MHz":  "⚡",
        "W":    "🔋",
        "V":    "🔌",
        "MB/s": "🔄",
        "GB/s": "🔄",
        "MB":   "🧮",
        "GB":   "🧮",
    }
    return mapping.get(unit, "•")
