"""Small dialogs: alert on a reading, system report."""

from __future__ import annotations

import os

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from corex.app import alerts
from corex.core.model import Kind, Reading
from corex.core.units import format_value
from corex.ui import theme

# sensible starting threshold when an alert is first set
_START = {Kind.TEMP: 85.0, Kind.LOAD: 95.0, Kind.FAN_PCT: 90.0}


class AlertDialog(QDialog):
    """Set, change or remove the alert of one reading. result_rule: dict, {} (removed) or None (cancelled)."""

    def __init__(self, device_name: str, reading: Reading, rule: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alert")
        self.result_rule: dict | None = None
        self.unit, self.factor = alerts.dialog_unit(reading.kind)
        rule = rule or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)
        title = QLabel(f"{device_name} · {reading.label}")
        title.setObjectName("h2")
        lay.addWidget(title)
        now = QLabel(f"Now: {format_value(reading.kind, reading.value)}")
        now.setObjectName("muted")
        lay.addWidget(now)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        start = _START.get(reading.kind, (reading.value or 0.0) / self.factor)
        self.above_on, self.above = self._row(grid, 0, "Tell me when it goes above", rule.get("above"), start)
        self.below_on, self.below = self._row(grid, 1, "Tell me when it drops below", rule.get("below"),
                                              start * 0.5 if reading.kind != Kind.TEMP else 30.0)
        if not rule:
            self.above_on.setChecked(True)
        lay.addLayout(grid)
        hint = QLabel("A desktop notification, repeated at most every 5 minutes; "
                      "the value turns red in the list and the widget.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        buttons = QHBoxLayout()
        if rule:
            remove = QPushButton("Remove alert")
            remove.clicked.connect(self._remove)
            buttons.addWidget(remove)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        lay.addLayout(buttons)

    def _row(self, grid: QGridLayout, row: int, text: str, value: float | None, default: float):
        check = QCheckBox(text)
        check.setChecked(value is not None)
        spin = QDoubleSpinBox()
        spin.setRange(-1e6, 1e9)
        spin.setDecimals(0 if self.factor == 1.0 and default >= 10 else 2)
        spin.setSuffix(f" {self.unit}" if self.unit else "")
        spin.setValue((value / self.factor) if value is not None else default)
        spin.setEnabled(check.isChecked())
        check.toggled.connect(spin.setEnabled)
        grid.addWidget(check, row, 0)
        grid.addWidget(spin, row, 1)
        return check, spin

    def _save(self) -> None:
        rule = {}
        if self.above_on.isChecked():
            rule["above"] = self.above.value() * self.factor
        if self.below_on.isChecked():
            rule["below"] = self.below.value() * self.factor
        self.result_rule = rule
        self.accept()

    def _remove(self) -> None:
        self.result_rule = {}
        self.accept()


class ReportDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System report")
        self.resize(900, 640)
        self.text = text
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        hint = QLabel("Every device and value right now. Copy it into a forum post or a bug report "
                      "when you ask for help.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        view = QPlainTextEdit(text)
        view.setReadOnly(True)
        view.setFont(theme.mono_font(10))
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(view, 1)
        buttons = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("muted")
        buttons.addWidget(self.status, 1)
        copy = QPushButton("Copy")
        copy.setObjectName("primary")
        copy.clicked.connect(self._copy)
        save = QPushButton("Save as…")
        save.clicked.connect(self._save)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for b in (copy, save, close):
            buttons.addWidget(b)
        lay.addLayout(buttons)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text)
        self.status.setText("Copied to the clipboard.")

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save system report",
                                              os.path.join(os.path.expanduser("~"), "corex-report.txt"),
                                              "Text (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text)
            self.status.setText(f"Saved to {path}")
        except OSError as e:
            self.status.setText(f"Could not save: {e.strerror}")
            self.status.setStyleSheet(f"color: {theme.HOT};")

