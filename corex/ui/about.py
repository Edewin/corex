"""About dialog."""

from __future__ import annotations

import platform

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from corex import __version__
from corex.ui import theme

REPO = "https://github.com/Edewin/corex"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About CoreX")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 18)
        lay.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(theme.icon_pixmap("cpu", theme.ACCENT, 48))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(logo)
        title = QLabel(f"<span style='color:{theme.ACCENT}; font-size:20pt; font-weight:700'>Core</span>"
                       f"<span style='font-size:20pt; font-weight:700'>X</span>"
                       f"<br><span style='color:{theme.MUTED}'>Version {__version__}</span>")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        text = QLabel(
            "Hardware monitor for Linux.<br>"
            f"<a style='color:{theme.ACCENT}' href='{REPO}'>{REPO.removeprefix('https://')}</a><br><br>"
            f"<span style='color:{theme.MUTED}; font-size:9pt'>MIT License · "
            f"Qt for Python (PySide6 {pyside_version}, LGPLv3) · pyqtgraph (MIT)<br>"
            f"Python {platform.python_version()} · {platform.system()} {platform.release()}</span>"
        )
        text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        text.setOpenExternalLinks(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        lay.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
