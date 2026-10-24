"""First start: ask how the user wants to see CoreX."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from corex.ui import theme

# (layout, widget visible, title, description, icon)
CHOICES = (
    ("list", False, "List", "Every sensor in one list with current, minimum and maximum values. "
                            "Charts only when you click for them.", "list"),
    ("list", True, "List + widget", "The same list, plus a small always-on-top widget "
                                    "with the values you pick.", "widget"),
    ("hybrid", True, "Hybrid", "The full list on the left, live charts on the right: of the device "
                               "you click, or an overview of all of them.", "hybrid"),
    ("dashboard", True, "Dashboard", "Devices on the left, live charts for each one, "
                                     "the full list underneath and the widget.", "overview"),
)


class FirstRunDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to CoreX")
        self.choice = CHOICES[-1]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        title = QLabel("How do you want to see CoreX?")
        title.setObjectName("h1")
        lay.addWidget(title)
        hint = QLabel("You can switch any time from the List / Hybrid / Dashboard buttons and the Widget button.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.setSpacing(14)
        for c in CHOICES:
            row.addWidget(self._card(c))
        lay.addLayout(row)

    def _card(self, choice) -> QPushButton:
        _, _, name, text, icon_name = choice
        b = QPushButton()
        b.setObjectName("choice")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumSize(210, 190)
        b.setStyleSheet(f"QPushButton#choice {{ background: {theme.PANEL}; border: 1px solid {theme.BORDER};"
                        f" border-radius: 10px; text-align: left; }}"
                        f"QPushButton#choice:hover {{ border-color: {theme.ACCENT}; background: {theme.PANEL_HI}; }}")
        inner = QVBoxLayout(b)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(theme.icon_pixmap(icon_name, theme.ACCENT, 30))
        head = QLabel(name)
        head.setObjectName("h2")
        body = QLabel(text)
        body.setWordWrap(True)
        body.setObjectName("muted")
        for w in (ic, head, body):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            w.setStyleSheet("background: transparent;")
            inner.addWidget(w)
        inner.addStretch(1)
        b.clicked.connect(lambda: self._pick(choice))
        return b

    def _pick(self, choice) -> None:
        self.choice = choice
        self.accept()

    @classmethod
    def ask(cls) -> tuple[str, bool]:
        """(layout, widget visible); closing the dialog keeps the full Dashboard."""
        d = cls()
        d.exec()
        return d.choice[0], d.choice[1]
