"""Main window: device sidebar, overview, per-device pages with tiles and a sensor table."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from corex import __version__
from corex.app.poller import History
from corex.app.settings import INTERVALS_S
from corex.core.model import Device, Kind, Snapshot
from corex.core.units import format_value
from corex.ui import pick, theme
from corex.ui.tiles import SidebarEntry, Tile

OVERVIEW = "overview"
_ID = Qt.ItemDataRole.UserRole


def _tile_grid(tiles: list[Tile], columns: int) -> QGridLayout:
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(12)
    for i, t in enumerate(tiles):
        grid.addWidget(t, i // columns, i % columns)
    for c in range(columns):
        grid.setColumnStretch(c, 1)
    return grid


# ---------------------------------------------------------------------------
class SensorTable(QTreeWidget):
    renamed = Signal(str, str)           # reading id, new label ("" = back to default)
    widget_toggled = Signal(str, bool)

    COLS = ("Sensor", "Value", "Min", "Max", "Widget")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLS))
        self.setHeaderLabels(self.COLS)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        h = self.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(c, 130)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(4, 70)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemChanged.connect(self._changed)
        self._items: dict[str, QTreeWidgetItem] = {}
        self.signature: tuple = ()
        self._updating = False
        self._mono = theme.mono_font(10)

    def show_device(self, device: Device, widget_ids: set[str]) -> None:
        signature = tuple((g.name, tuple(r.id for r in g.readings)) for g in device.groups)
        if signature != self.signature:
            self._build(device)
            self.signature = signature
        editing = self.state() == QAbstractItemView.State.EditingState
        self._updating = True
        for g in device.groups:
            for r in g.readings:
                item = self._items[r.id]
                if not editing and item.text(0) != r.label:
                    item.setText(0, r.label)
                item.setText(1, format_value(r.kind, r.value, r.text))
                item.setForeground(1, theme.qcolor(theme.level_color(r.kind, r.value)))
                if r.kind != Kind.INFO:
                    item.setText(2, format_value(r.kind, r.min))
                    item.setText(3, format_value(r.kind, r.max))
                    item.setCheckState(4, Qt.CheckState.Checked if r.id in widget_ids else Qt.CheckState.Unchecked)
        self._updating = False

    def _build(self, device: Device) -> None:
        self._updating = True
        self.clear()
        self._items.clear()
        for g in device.groups:
            parent = QTreeWidgetItem(self, [g.name])
            parent.setFirstColumnSpanned(True)
            parent.setForeground(0, theme.qcolor(theme.MUTED))
            f = parent.font(0)
            f.setBold(True)
            parent.setFont(0, f)
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for r in g.readings:
                item = QTreeWidgetItem(parent, [r.label])
                item.setData(0, _ID, r.id)
                item.setToolTip(0, "Double-click to rename")
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
                if r.kind != Kind.INFO:
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                    item.setCheckState(4, Qt.CheckState.Unchecked)
                    item.setToolTip(4, "Show this value in the floating widget")
                item.setFlags(flags)
                for c in (1, 2, 3):
                    item.setFont(c, self._mono)
                    item.setTextAlignment(c, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._items[r.id] = item
            parent.setExpanded(True)
        self._updating = False

    def _changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating:
            return
        rid = item.data(0, _ID)
        if not rid:
            return
        if column == 0:
            self.renamed.emit(rid, item.text(0).strip())
        elif column == 4:
            self.widget_toggled.emit(rid, item.checkState(4) == Qt.CheckState.Checked)

    def _menu(self, pos) -> None:
        item = self.itemAt(pos)
        rid = item.data(0, _ID) if item else None
        if not rid:
            return
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.editItem(item, 0))
        menu.addAction("Restore original name", lambda: self.renamed.emit(rid, ""))
        menu.addSeparator()
        menu.addAction("Copy value", lambda: QGuiApplication.clipboard().setText(item.text(1)))
        menu.addAction("Copy name and value",
                       lambda: QGuiApplication.clipboard().setText(f"{item.text(0)}: {item.text(1)}"))
        if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            on = item.checkState(4) == Qt.CheckState.Checked
            menu.addSeparator()
            menu.addAction("Remove from widget" if on else "Show in widget",
                           lambda: item.setCheckState(4, Qt.CheckState.Unchecked if on else Qt.CheckState.Checked))
        menu.exec(self.viewport().mapToGlobal(pos))


# ---------------------------------------------------------------------------
class DevicePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_id: str | None = None
        self.tile_ids: list = []
        self.tiles: list[Tile] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(12)
        self.icon = QLabel()
        head.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name = QLabel()
        self.name.setObjectName("h1")
        self.detail = QLabel()
        self.detail.setObjectName("muted")
        col.addWidget(self.name)
        col.addWidget(self.detail)
        head.addLayout(col, 1)
        lay.addLayout(head)
        self.tiles_host = QWidget()
        self.tiles_host.setLayout(QGridLayout())
        lay.addWidget(self.tiles_host)
        self.table = SensorTable()
        lay.addWidget(self.table, 1)

    def show_device(self, device_id: str) -> None:
        self.device_id = device_id
        self.tile_ids = []
        self.table.signature = ()

    def refresh(self, snap: Snapshot, history: History, widget_ids: set[str]) -> None:
        dev = snap.device(self.device_id) if self.device_id else None
        if dev is None:
            return
        self.icon.setPixmap(theme.icon_pixmap(dev.kind, theme.ACCENT, 34))
        self.name.setText(dev.name)
        self.detail.setText(dev.detail)
        wanted = pick.tiles(dev)
        if wanted != self.tile_ids:
            self.tile_ids = wanted
            QWidget().setLayout(self.tiles_host.layout())      # re-parent the old layout so it is deleted
            self.tiles = [Tile(dev.id, ids) for ids in wanted]
            self.tiles_host.setLayout(_tile_grid(self.tiles, max(1, len(self.tiles))))
            self.tiles_host.setVisible(bool(self.tiles))
        for t in self.tiles:
            t.refresh(snap, history)
        self.table.show_device(dev, widget_ids)


class OverviewPage(QScrollArea):
    open_device = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._ids: list = []
        self._columns = 0
        self.tiles: list[Tile] = []
        self.setWidget(QWidget())

    def refresh(self, snap: Snapshot, history: History) -> None:
        wanted = pick.overview_tiles(snap)
        columns = max(1, min(4, self.viewport().width() // 320))
        if wanted != self._ids or columns != self._columns:
            self._ids, self._columns = wanted, columns
            host = QWidget()
            outer = QVBoxLayout(host)
            outer.setContentsMargins(24, 18, 24, 18)
            self.tiles = [Tile(dev_id, ids, show_device=True) for dev_id, ids in wanted]
            for t in self.tiles:
                t.clicked.connect(self.open_device)
            outer.addLayout(_tile_grid(self.tiles, columns))
            outer.addStretch(1)
            self.setWidget(host)
        for t in self.tiles:
            t.refresh(snap, history)


# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    interval_changed = Signal(float)
    reset_minmax = Signal()
    toggle_widget = Signal()
    renamed = Signal(str, str)
    widget_toggled = Signal(str, bool)
    about_requested = Signal()
    quit_requested = Signal()

    def __init__(self, history: History, interval_s: float, start_page: str = OVERVIEW):
        super().__init__()
        self.history = history
        self.widget_ids: set[str] = set()
        self.hide_on_close = False
        self._page = start_page
        self._sidebar_ids: list[str] | None = None
        self._entries: dict[str, SidebarEntry] = {}
        self.setWindowTitle(f"CoreX {__version__}")
        self.resize(1280, 820)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QWidget()
        side.setFixedWidth(280)
        side.setStyleSheet(f"background: {theme.PANEL};")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 16, 0, 8)
        brand = QLabel(f"<span style='color:{theme.ACCENT}; font-size:17pt; font-weight:700'>Core</span>"
                       f"<span style='font-size:17pt; font-weight:700'>X</span>"
                       f"<span style='color:{theme.MUTED}; font-size:9pt'>&nbsp;&nbsp;{__version__}</span>")
        brand.setContentsMargins(20, 0, 0, 12)
        sv.addWidget(brand)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.currentItemChanged.connect(self._on_select)
        sv.addWidget(self.sidebar, 1)
        h.addWidget(side)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        mv.addWidget(self._toolbar(interval_s))
        self.stack = QStackedWidget()
        self.overview = OverviewPage()
        self.overview.open_device.connect(self.select)
        self.device_page = DevicePage()
        self.device_page.table.renamed.connect(self.renamed)
        self.device_page.table.widget_toggled.connect(self.widget_toggled)
        self.stack.addWidget(self.overview)
        self.stack.addWidget(self.device_page)
        mv.addWidget(self.stack, 1)
        h.addWidget(main, 1)
        self.setCentralWidget(root)

        sb = self.statusBar()
        self.status_sensors = QLabel()
        self.status_hint = QLabel()
        self.status_hint.setStyleSheet("color: #ffb547;")
        self.status_time = QLabel()
        sb.addWidget(self.status_sensors)
        sb.addWidget(self.status_hint, 1)
        sb.addPermanentWidget(self.status_time)

    def _toolbar(self, interval_s: float) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolbar")
        bar.setStyleSheet(f"QWidget#toolbar {{ border-bottom: 1px solid {theme.BORDER}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 10, 16, 10)
        self.page_title = QLabel("Overview")
        self.page_title.setObjectName("h2")
        lay.addWidget(self.page_title)
        lay.addStretch(1)

        self.interval = QComboBox()
        self.interval.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for s in INTERVALS_S:
            self.interval.addItem(f"Update every {s:g} s", s)
        self.interval.setCurrentIndex(INTERVALS_S.index(interval_s) if interval_s in INTERVALS_S else 1)
        self.interval.currentIndexChanged.connect(lambda i: self.interval_changed.emit(self.interval.itemData(i)))
        lay.addWidget(self.interval)

        reset = QToolButton()
        reset.setText("Reset min/max")
        reset.setIcon(theme.icon("reset", theme.TEXT, 16))
        reset.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        reset.setToolTip("Start the min/max columns over from the current values")
        reset.clicked.connect(self.reset_minmax)
        lay.addWidget(reset)

        self.widget_btn = QToolButton()
        self.widget_btn.setText("Widget")
        self.widget_btn.setIcon(theme.icon("widget", theme.TEXT, 16))
        self.widget_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.widget_btn.setCheckable(True)
        self.widget_btn.setToolTip("Show or hide the floating widget (Ctrl+W)")
        self.widget_btn.clicked.connect(self.toggle_widget)
        lay.addWidget(self.widget_btn)

        menu_btn = QToolButton()
        menu_btn.setIcon(theme.icon("menu", theme.TEXT, 16))
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        menu = QMenu(menu_btn)
        menu.addAction("About CoreX", self.about_requested)
        menu.addSeparator()
        quit_action = QAction("Quit CoreX", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.quit_requested)
        menu.addAction(quit_action)
        self.addAction(quit_action)
        menu_btn.setMenu(menu)
        lay.addWidget(menu_btn)

        toggle = QAction(self)
        toggle.setShortcut("Ctrl+W")
        toggle.triggered.connect(self.toggle_widget)
        self.addAction(toggle)
        return bar

    # ------------------------------------------------------------------
    def select(self, page: str) -> None:
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(_ID) == page:
                self.sidebar.setCurrentRow(i)
                return

    @property
    def page(self) -> str:
        return self._page

    def _on_select(self, current: QListWidgetItem | None, _prev=None) -> None:
        if current is None:
            return
        self._page = current.data(_ID)
        if self._page == OVERVIEW:
            self.stack.setCurrentWidget(self.overview)
            self.page_title.setText("Overview")
        else:
            self.device_page.show_device(self._page)
            self.stack.setCurrentWidget(self.device_page)
            entry = self._entries.get(self._page)
            self.page_title.setText(entry.name.text() if entry else "")
        if self.history.latest:
            self._refresh_page(self.history.latest)

    def _rebuild_sidebar(self, snap: Snapshot) -> None:
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        self._entries.clear()
        rows = [(OVERVIEW, "overview", "Overview", "All devices at a glance")]
        rows += [(d.id, d.kind, d.name, d.detail) for d in snap.devices]
        for dev_id, icon_name, name, detail in rows:
            item = QListWidgetItem(self.sidebar)
            item.setData(_ID, dev_id)
            entry = SidebarEntry(icon_name, name, detail)
            item.setSizeHint(entry.sizeHint())
            self.sidebar.setItemWidget(item, entry)
            self._entries[dev_id] = entry
        self._sidebar_ids = [d.id for d in snap.devices]
        self.sidebar.blockSignals(False)
        self.select(self._page if self._page in self._entries else OVERVIEW)

    def on_snapshot(self, snap: Snapshot) -> None:
        if [d.id for d in snap.devices] != self._sidebar_ids:
            self._rebuild_sidebar(snap)
        for d in snap.devices:
            entry = self._entries.get(d.id)
            if entry:
                entry.summary.setText(pick.summary(d))
        if self.isVisible():
            self._refresh_page(snap)
        count = sum(1 for r in snap.readings() if r.kind != Kind.INFO)
        self.status_sensors.setText(f"{count} sensors · {len(snap.devices)} devices")
        self.status_hint.setText("" if snap.status.get("hwmon") else
                                 "No temperature or fan chips found. Install lm-sensors and run "
                                 "'sudo sensors-detect', then restart CoreX.")
        self.status_time.setText("Updated " + time.strftime("%H:%M:%S", time.localtime(snap.timestamp)))

    def _refresh_page(self, snap: Snapshot) -> None:
        if self._page == OVERVIEW:
            self.overview.refresh(snap, self.history)
        else:
            self.device_page.refresh(snap, self.history, self.widget_ids)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.history.latest and self._page == OVERVIEW:
            self.overview.refresh(self.history.latest, self.history)

    def closeEvent(self, e):
        if self.hide_on_close:
            e.ignore()
            self.hide()
        else:
            e.accept()
            self.quit_requested.emit()
