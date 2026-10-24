"""Choose and order the charts of the Overview (shared by the Hybrid and Dashboard views)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from corex.core.model import Snapshot
from corex.ui import pick, theme

_IDS = Qt.ItemDataRole.UserRole


class OverviewDialog(QDialog):
    """chosen: the charts to show (lists of reading ids), or None to go back to the automatic choice."""

    def __init__(self, snap: Snapshot, current: list[list[str]] | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize the overview")
        self.resize(560, 620)
        self.chosen: list[list[str]] | None = current
        self._auto = current is None
        self._snap = snap
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)
        title = QLabel("Customize the overview")
        title.setObjectName("h2")
        lay.addWidget(title)
        hint = QLabel("Tick the charts to show and drag them into the order you like. "
                      "The Hybrid and Dashboard views share this overview.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.find = QLineEdit()
        self.find.setPlaceholderText("Find a sensor…")
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(self._filter)
        lay.addWidget(self.find)

        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.itemChanged.connect(self._changed)
        self.list.model().rowsMoved.connect(self._changed)
        row.addWidget(self.list, 1)
        side = QVBoxLayout()
        for text, step in (("Move up", -1), ("Move down", 1)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, s=step: self._move(s))
            side.addWidget(b)
        side.addStretch(1)
        row.addLayout(side)
        lay.addLayout(row, 1)
        self.count = QLabel()
        self.count.setObjectName("muted")
        lay.addWidget(self.count)

        bottom = QHBoxLayout()
        reset = QPushButton("Back to automatic")
        reset.setToolTip("The first charts of every device, as CoreX picks them")
        reset.clicked.connect(self._reset)
        bottom.addWidget(reset)
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save)
        bottom.addWidget(cancel)
        bottom.addWidget(save)
        lay.addLayout(bottom)
        self._fill(current)
        self.list.setFocus()

    def _fill(self, current: list[list[str]] | None) -> None:
        shown = [ids for _, ids in pick.overview_tiles(self._snap, current)]
        cands = pick.overview_candidates(self._snap)
        kinds = {d.id: d.kind for d in self._snap.devices}
        by_ids = {tuple(ids): (dev_id, name) for dev_id, ids, name in cands}
        rows = [(by_ids[tuple(ids)], ids, True) for ids in shown if tuple(ids) in by_ids]
        rows += [((dev_id, name), ids, False) for dev_id, ids, name in cands if ids not in shown]
        self.list.blockSignals(True)
        self.list.clear()
        for (dev_id, name), ids, on in rows:
            item = QListWidgetItem(theme.icon(kinds.get(dev_id, "overview"), theme.ACCENT, 16), name)
            item.setData(_IDS, ids)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                          Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._filter(self.find.text())
        self._count()

    def _checked(self) -> list[list[str]]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(_IDS))
        return out

    def _count(self) -> None:
        n = len(self._checked())
        self.count.setText("No charts: the overview stays empty" if n == 0 else
                           f"{n} chart{'s' if n > 1 else ''} on the overview"
                           + (" · automatic" if self._auto else ""))

    def _changed(self, *_) -> None:
        self._auto = False
        self._count()

    def _filter(self, text: str) -> None:
        words = text.lower().split()
        for i in range(self.list.count()):
            item = self.list.item(i)
            self.list.setRowHidden(i, not all(w in item.text().lower() for w in words))

    def _move(self, step: int) -> None:
        row = self.list.currentRow()
        target = row + step
        while 0 <= target < self.list.count() and self.list.isRowHidden(target):
            target += step
        if row < 0 or not 0 <= target < self.list.count():
            return
        self.list.blockSignals(True)
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)
        self.list.blockSignals(False)
        self._changed()

    def _reset(self) -> None:
        self._fill(None)
        self._auto = True
        self._count()

    def _save(self) -> None:
        self.chosen = None if self._auto else self._checked()
        self.accept()
