"""Main window: List (one sensor tree), Hybrid (tree + charts) or Dashboard (sidebar, overview, device pages)."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from corex import __version__
from corex.app.poller import History
from corex.app.settings import INTERVALS_S, Settings
from corex.core.model import Kind, Snapshot
from corex.ui import pick, theme
from corex.ui.overviewedit import OverviewDialog
from corex.ui.sensortree import OVERVIEW, SensorTree
from corex.ui.tiles import SidebarEntry, Tile

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


def _tree_refresh(tree: SensorTree, devices, widget_ids: set[str], prefs: Settings) -> None:
    tree.refresh(devices, widget_ids, set(prefs.charts), set(prefs.hidden), prefs.show_hidden, set(prefs.collapsed))


# ---------------------------------------------------------------------------
class DevicePage(QWidget):
    """Header and charts of one device; with table=True also its sensors underneath, else a way back."""

    back = Signal()

    def __init__(self, table: bool = True, parent=None):
        super().__init__(parent)
        self.device_id: str | None = None
        self.tile_ids: list = []
        self._columns = 0
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
        if not table:
            back = QToolButton()
            back.setText("Overview")
            back.setIcon(theme.icon("overview", theme.TEXT, 16))
            back.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            back.setToolTip("Back to the charts of every device (Esc in the list)")
            back.clicked.connect(self.back)
            head.addWidget(back, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        self.tiles_host = QWidget()
        self.tiles_host.setLayout(QGridLayout())
        lay.addWidget(self.tiles_host)
        self.table = SensorTree(all_devices=False, charts=False) if table else None
        if self.table:
            lay.addWidget(self.table, 1)
        else:
            lay.addStretch(1)

    def show_device(self, device_id: str) -> None:
        self.device_id = device_id
        self.tile_ids = []
        if self.table:
            self.table.invalidate()

    def refresh(self, snap: Snapshot, history: History, widget_ids: set[str], prefs: Settings,
                extra: str | None = None) -> None:
        """extra: one more value to chart (the row picked in the Hybrid list)."""
        dev = snap.device(self.device_id) if self.device_id else None
        if dev is None:
            return
        self.icon.setPixmap(theme.icon_pixmap(dev.kind, theme.ACCENT, 34))
        self.name.setText(dev.name)
        self.detail.setText(dev.detail)
        wanted = pick.tiles(dev)
        r = dev.reading(extra) if extra else None
        if r is not None and r.kind != Kind.INFO and not any(extra in ids for ids in wanted):
            wanted = wanted + [[extra]]
        columns = len(wanted) if self.table else min(len(wanted), self.width() // 300)
        columns = max(1, columns)
        if wanted != self.tile_ids or columns != self._columns:
            self.tile_ids, self._columns = wanted, columns
            QWidget().setLayout(self.tiles_host.layout())      # re-parent the old layout so it is deleted
            self.tiles = [Tile(dev.id, ids, clickable=False) for ids in wanted]
            self.tiles_host.setLayout(_tile_grid(self.tiles, columns))
            self.tiles_host.setVisible(bool(self.tiles))
        for t in self.tiles:
            t.refresh(snap, history)
        if self.table:
            _tree_refresh(self.table, [dev], widget_ids, prefs)


class OverviewPage(QScrollArea):
    """The charts of every device; the user picks and orders them (prefs.overview)."""

    open_device = Signal(str)
    customize = Signal()
    removed = Signal(str)            # first reading id of the chart taken off

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._ids: list | None = None
        self._columns = 0
        self.tiles: list[Tile] = []
        self.setWidget(QWidget())

    def refresh(self, snap: Snapshot, history: History, custom: list[list[str]] | None) -> None:
        wanted = pick.overview_tiles(snap, custom)
        columns = max(1, min(4, self.viewport().width() // 320))
        if wanted != self._ids or columns != self._columns:
            self._ids, self._columns = wanted, columns
            host = QWidget()
            outer = QVBoxLayout(host)
            outer.setContentsMargins(24, 12, 24, 18)
            outer.setSpacing(10)
            head = QHBoxLayout()
            hint = QLabel("Click a chart to open its device")
            hint.setObjectName("muted")
            head.addWidget(hint, 1)
            edit = QToolButton()
            edit.setText("Customize…")
            edit.setIcon(theme.icon("edit", theme.TEXT, 16))
            edit.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            edit.setToolTip("Choose the charts of the overview and their order")
            edit.clicked.connect(self.customize)
            head.addWidget(edit)
            outer.addLayout(head)
            self.tiles = [Tile(dev_id, ids, show_device=True, closable=True, clickable=True,
                               close_tip="Remove from the overview") for dev_id, ids in wanted]
            for t in self.tiles:
                t.clicked.connect(self.open_device)
                t.closed.connect(self.removed)
            if self.tiles:
                outer.addLayout(_tile_grid(self.tiles, columns))
            else:
                empty = QLabel("The overview is empty.\nUse Customize… to choose its charts, or right-click "
                               "a sensor in the list › Add to the overview.")
                empty.setObjectName("muted")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                outer.addSpacing(60)
                outer.addWidget(empty)
            outer.addStretch(1)
            self.setWidget(host)
        for t in self.tiles:
            t.refresh(snap, history)


class HybridPage(QSplitter):
    """Every sensor on the left; on the right the charts of the device picked there, or the overview."""

    device_selected = Signal(str)    # device id or OVERVIEW
    picked = Signal()                # another row of the list: its chart joins the device's
    split_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setChildrenCollapsible(False)
        self.page = OVERVIEW
        self.tree = SensorTree(all_devices=True, charts=False, pick_device=True)
        self.tree.setMinimumWidth(420)
        self.tree.device_selected.connect(self.device_selected)
        self.tree.currentItemChanged.connect(lambda *_: None if self.tree._updating else self.picked.emit())
        self.addWidget(self.tree)
        self.right = QStackedWidget()
        self.overview = OverviewPage()
        self.overview.open_device.connect(self.device_selected)
        self.device = DevicePage(table=False)
        self.device.back.connect(lambda: self.device_selected.emit(OVERVIEW))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.device)
        self.device_scroll = scroll
        self.right.addWidget(self.overview)
        self.right.addWidget(scroll)
        self.right.setMinimumWidth(300)
        self.addWidget(self.right)
        self._split_set = False
        self._split_timer = QTimer(self, singleShot=True, interval=400)
        self._split_timer.timeout.connect(lambda: self.split_changed.emit(self.sizes()))
        self.splitterMoved.connect(lambda *_: self._split_timer.start())

    def set_split(self, sizes: list[int] | None) -> None:
        if sizes and len(sizes) == 2:
            self.setSizes(sizes)
            self._split_set = True

    def show_page(self, page: str) -> None:
        if page != self.page:
            self.page = page
            if page != OVERVIEW:
                self.device.show_device(page)
        self.tree.select_device(page)
        self.right.setCurrentWidget(self.overview if page == OVERVIEW else self.device_scroll)

    def refresh(self, snap: Snapshot, history: History, widget_ids: set[str], prefs: Settings) -> None:
        if not self._split_set and self.width() > 900:
            self.setSizes([self.width() // 2, self.width() - self.width() // 2])
            self._split_set = True
        _tree_refresh(self.tree, snap.devices, widget_ids, prefs)
        self.tree.select_device(self.page)          # a rebuilt tree forgets its current row
        if self.page != OVERVIEW and snap.device(self.page):
            self.device.refresh(snap, history, widget_ids, prefs, self.tree.current_reading())
        else:
            self.overview.refresh(snap, history, prefs.overview)


class ListPage(QSplitter):
    """Every device in one tree; charts only for the values the user asks for."""

    chart_closed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setChildrenCollapsible(False)
        self.tree = SensorTree(all_devices=True, charts=True)
        self.addWidget(self.tree)
        self.charts = QScrollArea()
        self.charts.setWidgetResizable(True)
        self.charts.setWidget(QWidget())
        self.addWidget(self.charts)
        self.charts.hide()
        self.tiles: list[Tile] = []
        self._key: tuple = ()

    def refresh(self, snap: Snapshot, history: History, widget_ids: set[str], prefs: Settings) -> None:
        _tree_refresh(self.tree, snap.devices, widget_ids, prefs)
        wanted = []
        for rid in prefs.charts:
            dev = next((d for d in snap.devices if d.reading(rid)), None)
            if dev:
                wanted.append((dev.id, rid))
        columns = max(1, min(4, self.width() // 320))
        if (tuple(wanted), columns) != self._key:
            self._key = (tuple(wanted), columns)
            host = QWidget()
            outer = QVBoxLayout(host)
            outer.setContentsMargins(16, 12, 16, 12)
            self.tiles = [Tile(dev_id, [rid], show_device=True, closable=True) for dev_id, rid in wanted]
            for t in self.tiles:
                t.closed.connect(self.chart_closed)
            outer.addLayout(_tile_grid(self.tiles, columns))
            outer.addStretch(1)
            self.charts.setWidget(host)
            opening = self.charts.isHidden() and self.tiles
            self.charts.setVisible(bool(self.tiles))
            if opening:
                self.setSizes([max(200, self.height() - 236), 236])
        for t in self.tiles:
            t.refresh(snap, history)


# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    interval_changed = Signal(float)
    reset_minmax = Signal()
    toggle_widget = Signal()
    renamed = Signal(str, str)
    widget_toggled = Signal(str, bool)
    view_changed = Signal(str)
    autostart_changed = Signal(bool)
    prefs_changed = Signal()             # hidden / collapsed / charts / columns changed in prefs
    about_requested = Signal()
    quit_requested = Signal()
    history_requested = Signal(str)      # reading id ("" = pick in the window)
    alert_requested = Signal(str)
    report_requested = Signal()
    edit_widget_requested = Signal()
    theme_changed = Signal(str)

    def __init__(self, history: History, prefs: Settings):
        super().__init__()
        self.history = history
        self.prefs = prefs
        self.widget_ids: set[str] = set()
        self.hide_on_close = False
        self.mode = prefs.view_mode or "dashboard"
        self._page = prefs.last_page
        self._sidebar_ids: list[str] | None = None
        self._entries: dict[str, SidebarEntry] = {}
        self.setWindowTitle(f"CoreX {__version__}")
        self.resize(1280, 820)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.side = QWidget()
        self.side.setFixedWidth(280)
        self.side.setStyleSheet(f"background: {theme.PANEL};")
        sv = QVBoxLayout(self.side)
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
        h.addWidget(self.side)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        mv.addWidget(self._toolbar(prefs.interval_s))
        self.stack = QStackedWidget()
        self.overview = OverviewPage()
        self.overview.open_device.connect(self.select)
        self.device_page = DevicePage()
        self.list_page = ListPage()
        self.list_page.chart_closed.connect(lambda rid: self._toggle_pref("charts", rid, False))
        self.hybrid = HybridPage()
        self.hybrid.set_split(prefs.columns.get("hybrid_split"))
        self.hybrid.device_selected.connect(self.select)
        self.hybrid.picked.connect(self._refresh_now)
        self.hybrid.split_changed.connect(lambda s: self._set_widths("hybrid_split", s))
        for ov in (self.overview, self.hybrid.overview):
            ov.customize.connect(self.customize_overview)
            ov.removed.connect(lambda rid: self._overview_toggle(rid, False))
        for tree, key in ((self.device_page.table, "device"), (self.list_page.tree, "list"),
                          (self.hybrid.tree, "hybrid")):
            tree.set_widths(prefs.columns.get(key))
            tree.renamed.connect(self.renamed)
            tree.widget_toggled.connect(self.widget_toggled)
            tree.chart_toggled.connect(lambda rid, on: self._toggle_pref("charts", rid, on))
            tree.hide_toggled.connect(lambda rid, on: self._toggle_pref("hidden", rid, on))
            tree.collapsed_changed.connect(lambda k, on: self._toggle_pref("collapsed", k, on, refresh=False))
            tree.widths_changed.connect(lambda w, key=key: self._set_widths(key, w))
            tree.history_requested.connect(self.history_requested)
            tree.alert_requested.connect(self.alert_requested)
            tree.overview_toggled.connect(self._overview_toggle)
        for page in (self.overview, self.device_page, self.list_page, self.hybrid):
            self.stack.addWidget(page)
        mv.addWidget(self.stack, 1)
        h.addWidget(main, 1)
        self.setCentralWidget(root)

        sb = self.statusBar()
        self.status_sensors = QLabel()
        self.status_hint = QLabel()
        self.status_hint.setStyleSheet(f"color: {theme.WARN};")
        self.status_time = QLabel()
        sb.addWidget(self.status_sensors)
        sb.addWidget(self.status_hint, 1)
        sb.addPermanentWidget(self.status_time)
        self.set_view(self.mode)

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

        self.view_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(bar)
        for mode, text, icon_name, key in (("list", "List", "list", "Ctrl+1"),
                                           ("hybrid", "Hybrid", "hybrid", "Ctrl+2"),
                                           ("dashboard", "Dashboard", "overview", "Ctrl+3")):
            b = QToolButton()
            b.setText(text)
            b.setIcon(theme.icon(icon_name, theme.TEXT, 16))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setCheckable(True)
            b.setShortcut(key)
            b.setToolTip({"list": "All sensors in one list, charts only when you ask for them",
                          "hybrid": "All sensors on the left, charts on the right: of the device you click, "
                                    "or the overview",
                          "dashboard": "Devices on the left, charts for each one"}[mode] + f" ({key})")
            b.clicked.connect(lambda _=False, m=mode: self._choose_view(m))
            group.addButton(b)
            lay.addWidget(b)
            self.view_buttons[mode] = b
        lay.addSpacing(12)

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
        self.show_hidden_action = menu.addAction("Show hidden sensors")
        self.show_hidden_action.setCheckable(True)
        self.show_hidden_action.setChecked(self.prefs.show_hidden)
        self.show_hidden_action.setToolTip("Hidden sensors appear greyed out; right-click one to bring it back")
        self.show_hidden_action.toggled.connect(self._set_show_hidden)
        self.autostart_action = menu.addAction("Start with system")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.prefs.autostart)
        self.autostart_action.toggled.connect(self.autostart_changed)
        menu.setToolTipsVisible(True)
        themes = menu.addMenu(theme.icon("theme", theme.TEXT, 16), "Theme")
        group = QActionGroup(themes)
        for mode, text in (("dark", "Dark"), ("light", "Light"), ("system", "Same as the system")):
            a = QAction(text, themes, checkable=True, checked=self.prefs.theme == mode)
            a.triggered.connect(lambda _=False, m=mode: self.theme_changed.emit(m))
            group.addAction(a)
            themes.addAction(a)
        menu.addSeparator()
        history = QAction(theme.icon("history", theme.TEXT, 16), "History…", self)
        history.setShortcut("Ctrl+H")
        history.triggered.connect(lambda: self.history_requested.emit(""))
        menu.addAction(history)
        self.addAction(history)
        report = QAction(theme.icon("report", theme.TEXT, 16), "System report…", self)
        report.setShortcut("Ctrl+R")
        report.triggered.connect(self.report_requested)
        menu.addAction(report)
        self.addAction(report)
        edit_widget = QAction(theme.icon("widget", theme.TEXT, 16), "Edit widget…", self)
        edit_widget.setShortcut("Ctrl+E")
        edit_widget.triggered.connect(self.edit_widget_requested)
        menu.addAction(edit_widget)
        self.addAction(edit_widget)
        menu.addAction(theme.icon("overview", theme.TEXT, 16), "Customize the overview…", self.customize_overview)
        menu.addSeparator()
        menu.addAction("About CoreX", self.about_requested.emit)
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

    # -- view ------------------------------------------------------------
    def set_view(self, mode: str) -> None:
        self.mode = mode
        self.side.setVisible(mode == "dashboard")
        for m, b in self.view_buttons.items():
            b.setChecked(m == mode)
        self._show_page()

    def _choose_view(self, mode: str) -> None:
        if mode != self.mode:
            self.set_view(mode)
            self.view_changed.emit(mode)

    def _show_page(self) -> None:
        if self.mode == "list":
            self.stack.setCurrentWidget(self.list_page)
            self.page_title.setText("All sensors")
        elif self.mode == "hybrid":
            page = self._page if self._page in self._entries else OVERVIEW
            self.hybrid.show_page(page)
            self.stack.setCurrentWidget(self.hybrid)
            self.page_title.setText("Overview" if page == OVERVIEW else self._entries[page].name.text())
        elif self._page == OVERVIEW or self._page not in self._entries:
            self.stack.setCurrentWidget(self.overview)
            self.page_title.setText("Overview")
        else:
            self.device_page.show_device(self._page)
            self.stack.setCurrentWidget(self.device_page)
            self.page_title.setText(self._entries[self._page].name.text())
        self._refresh_now()

    def select(self, page: str) -> None:
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(_ID) == page:
                self.sidebar.setCurrentRow(i)
                return

    @property
    def page(self) -> str:
        return self._page

    def _on_select(self, current: QListWidgetItem | None, _prev=None) -> None:
        if current is not None:
            self._page = current.data(_ID)
            self._show_page()

    # -- preferences -----------------------------------------------------
    def _toggle_pref(self, name: str, value: str, on: bool, refresh: bool = True) -> None:
        values = getattr(self.prefs, name)
        if on and value not in values:
            values.append(value)
        elif not on and value in values:
            values.remove(value)
        self.prefs_changed.emit()
        if refresh:
            self._refresh_now()

    def _overview_specs(self) -> list[list[str]]:
        if self.prefs.overview is not None:
            return [list(ids) for ids in self.prefs.overview]
        snap = self.history.latest
        return [ids for _, ids in pick.overview_tiles(snap)] if snap else []

    def _overview_toggle(self, rid: str, on: bool) -> None:
        specs = self._overview_specs()
        if on and not any(rid in ids for ids in specs):
            specs.append([rid])
        elif not on:
            specs = [ids for ids in specs if rid not in ids]
        self.prefs.overview = specs
        self.prefs_changed.emit()
        self.statusBar().showMessage("Added to the overview" if on else
                                     "Removed from the overview · Customize… brings it back", 4000)
        self._refresh_now()

    def customize_overview(self) -> None:
        if not self.history.latest:
            return
        dlg = OverviewDialog(self.history.latest, self.prefs.overview, self)
        if dlg.exec():
            self.prefs.overview = dlg.chosen
            self.prefs_changed.emit()
            self._refresh_now()

    def _set_widths(self, key: str, widths: list[int]) -> None:
        self.prefs.columns[key] = widths
        self.prefs_changed.emit()

    def _set_show_hidden(self, on: bool) -> None:
        self.prefs.show_hidden = on
        self.prefs_changed.emit()
        self._refresh_now()

    def set_autostart_checked(self, on: bool) -> None:
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(on)
        self.autostart_action.blockSignals(False)

    # -- data ------------------------------------------------------------
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
        if self._page not in self._entries:
            self._page = OVERVIEW
        self.select(self._page)
        self._show_page()

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

    def _refresh_now(self) -> None:
        if self.history.latest:
            self._refresh_page(self.history.latest)

    def _refresh_page(self, snap: Snapshot) -> None:
        alert_ids = set(self.prefs.alerts)
        on_overview = {i for _, ids in pick.overview_tiles(snap, self.prefs.overview) for i in ids}
        for tree in (self.list_page.tree, self.device_page.table, self.hybrid.tree):
            tree.alert_ids = alert_ids
            tree.overview_ids = on_overview
        page = self.stack.currentWidget()
        if page is self.list_page:
            self.list_page.refresh(snap, self.history, self.widget_ids, self.prefs)
        elif page is self.hybrid:
            self.hybrid.refresh(snap, self.history, self.widget_ids, self.prefs)
        elif page is self.overview:
            self.overview.refresh(snap, self.history, self.prefs.overview)
        else:
            self.device_page.refresh(snap, self.history, self.widget_ids, self.prefs)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.stack.currentWidget() is not self.device_page:
            self._refresh_now()

    def closeEvent(self, e):
        if self.hide_on_close:
            e.ignore()
            self.hide()
        else:
            e.accept()
            self.quit_requested.emit()
