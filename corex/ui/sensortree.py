"""The sensor tree: Value / Min / Max per reading, used by the List view and the device pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeWidget, QTreeWidgetItem

from corex.core.model import Device, Kind
from corex.core.units import format_value
from corex.ui import theme

_ID = Qt.ItemDataRole.UserRole            # reading id on reading rows
_KEY = Qt.ItemDataRole.UserRole + 1       # collapse key on device / group rows


def group_key(device_id: str, group: str) -> str:
    return f"{device_id}#{group}"


class SensorTree(QTreeWidget):
    renamed = Signal(str, str)            # reading id, new label ("" = back to default)
    widget_toggled = Signal(str, bool)
    chart_toggled = Signal(str, bool)
    hide_toggled = Signal(str, bool)      # reading id, hidden
    collapsed_changed = Signal(str, bool)  # device / group key, collapsed
    widths_changed = Signal(list)         # widths of Value, Min, Max

    COLS = ("Sensor", "Value", "Min", "Max", "Chart", "Widget")
    VALUE, MIN, MAX, CHART, WIDGET = 1, 2, 3, 4, 5

    def __init__(self, all_devices: bool, charts: bool, parent=None):
        super().__init__(parent)
        self.all_devices = all_devices
        self.setColumnCount(len(self.COLS))
        self.setHeaderLabels(self.COLS)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        h = self.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (self.VALUE, self.MIN, self.MAX):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            self.setColumnWidth(c, 130)
        for c in (self.CHART, self.WIDGET):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(c, 64)
        self.setColumnHidden(self.CHART, not charts)
        self.headerItem().setToolTip(self.CHART, "Click the icon to draw a live chart of that value")
        self.headerItem().setToolTip(self.WIDGET, "Tick to show the value in the floating widget")

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemChanged.connect(self._changed)
        self.itemClicked.connect(self._clicked)
        self.itemExpanded.connect(lambda it: self._expanded(it, False))
        self.itemCollapsed.connect(lambda it: self._expanded(it, True))
        self._width_timer = QTimer(self, singleShot=True, interval=400)
        self._width_timer.timeout.connect(
            lambda: self.widths_changed.emit([self.columnWidth(c) for c in (self.VALUE, self.MIN, self.MAX)]))
        h.sectionResized.connect(lambda c, *_: self._width_timer.start() if c in (1, 2, 3) and not self._updating else None)

        self._items: dict[str, QTreeWidgetItem] = {}
        self._signature: tuple = ()
        self._updating = False
        self._mono = theme.mono_font(10)
        self._chart_on = theme.icon("chart", theme.ACCENT, 16)
        self._chart_off = theme.icon("chart", theme.BORDER, 16)

    def set_widths(self, widths: list[int] | None) -> None:
        if not widths:
            return
        self._updating = True
        for c, w in zip((self.VALUE, self.MIN, self.MAX), widths):
            self.setColumnWidth(c, max(60, int(w)))
        self._updating = False

    def invalidate(self) -> None:
        self._signature = ()

    # ------------------------------------------------------------------
    def refresh(self, devices: list[Device], widget_ids: set[str], chart_ids: set[str],
                hidden: set[str], show_hidden: bool, collapsed: set[str]) -> None:
        visible = {d.id: [(g.name, [r for r in g.readings if show_hidden or r.id not in hidden])
                          for g in d.groups] for d in devices}
        signature = (show_hidden, frozenset(hidden & set(self._all_ids(devices))),
                     tuple((d.id, d.name, d.detail, tuple((g, tuple(r.id for r in rs)) for g, rs in visible[d.id]))
                           for d in devices))
        if signature != self._signature:
            self._build(devices, visible, hidden, collapsed)
            self._signature = signature
        editing = self.state() == QAbstractItemView.State.EditingState
        self._updating = True
        for d in devices:
            for _, readings in visible[d.id]:
                for r in readings:
                    item = self._items[r.id]
                    if not editing and item.text(0) != r.label:
                        item.setText(0, r.label)
                    item.setText(self.VALUE, format_value(r.kind, r.value, r.text))
                    if r.id not in hidden:
                        item.setForeground(self.VALUE, theme.qcolor(theme.level_color(r.kind, r.value)))
                    if r.kind != Kind.INFO:
                        item.setText(self.MIN, format_value(r.kind, r.min))
                        item.setText(self.MAX, format_value(r.kind, r.max))
                        item.setCheckState(self.WIDGET, Qt.CheckState.Checked if r.id in widget_ids
                                           else Qt.CheckState.Unchecked)
                        on = r.id in chart_ids
                        if item.data(self.CHART, _ID) != on:
                            item.setData(self.CHART, _ID, on)
                            item.setIcon(self.CHART, self._chart_on if on else self._chart_off)
        self._updating = False

    @staticmethod
    def _all_ids(devices: list[Device]):
        return (r.id for d in devices for g in d.groups for r in g.readings)

    def _build(self, devices, visible, hidden, collapsed) -> None:
        self._updating = True
        self.clear()
        self._items.clear()
        bold = self.font()
        bold.setBold(True)
        for d in devices:
            groups = [(g, rs) for g, rs in visible[d.id] if rs]
            if not groups:
                continue
            parent = self.invisibleRootItem()
            if self.all_devices:
                top = QTreeWidgetItem(self, [f"{d.name}   ·   {d.detail}" if d.detail else d.name])
                top.setFirstColumnSpanned(True)
                top.setIcon(0, theme.icon(d.kind, theme.ACCENT, 18))
                top.setFont(0, bold)
                top.setFlags(Qt.ItemFlag.ItemIsEnabled)
                top.setData(0, _KEY, d.id)
                parent = top
            for gname, readings in groups:
                g = QTreeWidgetItem(parent, [gname])
                g.setFirstColumnSpanned(True)
                g.setForeground(0, theme.qcolor(theme.MUTED))
                g.setFont(0, bold)
                g.setFlags(Qt.ItemFlag.ItemIsEnabled)
                g.setData(0, _KEY, group_key(d.id, gname))
                for r in readings:
                    self._items[r.id] = self._reading_item(g, r, r.id in hidden)
        # expand everything except what the user folded
        it = self._walk()
        for item in it:
            key = item.data(0, _KEY)
            if key:
                item.setExpanded(key not in collapsed)
        self._updating = False

    def _reading_item(self, parent: QTreeWidgetItem, r, is_hidden: bool) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [r.label])
        item.setData(0, _ID, r.id)
        item.setToolTip(0, "Hidden · right-click › Show this sensor" if is_hidden else "Double-click to rename")
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        if r.kind != Kind.INFO:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
            item.setCheckState(self.WIDGET, Qt.CheckState.Unchecked)
            item.setToolTip(self.WIDGET, "Show this value in the floating widget")
            item.setToolTip(self.CHART, "Live chart of this value")
            item.setIcon(self.CHART, self._chart_off)
            item.setData(self.CHART, _ID, False)
        item.setFlags(flags)
        for c in (self.VALUE, self.MIN, self.MAX):
            item.setFont(c, self._mono)
            item.setTextAlignment(c, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if is_hidden:
            muted = theme.qcolor(theme.MUTED)
            for c in range(self.columnCount()):
                item.setForeground(c, muted)
            f = item.font(0)
            f.setItalic(True)
            item.setFont(0, f)
        return item

    def _walk(self):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            yield item
            stack += [item.child(i) for i in range(item.childCount())]

    # ------------------------------------------------------------------
    def _changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating:
            return
        rid = item.data(0, _ID)
        if not rid:
            return
        if column == 0:
            self.renamed.emit(rid, item.text(0).strip())
        elif column == self.WIDGET:
            self.widget_toggled.emit(rid, item.checkState(self.WIDGET) == Qt.CheckState.Checked)

    def _clicked(self, item: QTreeWidgetItem, column: int) -> None:
        rid = item.data(0, _ID)
        if rid and column == self.CHART and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            self.chart_toggled.emit(rid, not item.data(self.CHART, _ID))

    def _expanded(self, item: QTreeWidgetItem, collapsed: bool) -> None:
        key = item.data(0, _KEY)
        if key and not self._updating:
            self.collapsed_changed.emit(key, collapsed)

    def _set_all_expanded(self, expanded: bool) -> None:
        for item in list(self._walk()):
            if item.data(0, _KEY):
                item.setExpanded(expanded)

    def _menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        rid = item.data(0, _ID)
        if rid:
            hidden = item.font(0).italic()
            menu.addAction("Rename…", lambda: self.editItem(item, 0))
            menu.addAction("Restore original name", lambda: self.renamed.emit(rid, ""))
            menu.addSeparator()
            menu.addAction("Copy value", lambda: QGuiApplication.clipboard().setText(item.text(self.VALUE)))
            menu.addAction("Copy name and value", lambda: QGuiApplication.clipboard().setText(
                f"{item.text(0)}: {item.text(self.VALUE)}"))
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                menu.addSeparator()
                if not self.isColumnHidden(self.CHART):
                    chart = bool(item.data(self.CHART, _ID))
                    menu.addAction("Remove chart" if chart else "Show chart",
                                   lambda: self.chart_toggled.emit(rid, not chart))
                on = item.checkState(self.WIDGET) == Qt.CheckState.Checked
                menu.addAction("Remove from widget" if on else "Show in widget",
                               lambda: item.setCheckState(self.WIDGET, Qt.CheckState.Unchecked if on
                                                          else Qt.CheckState.Checked))
            menu.addSeparator()
            menu.addAction("Show this sensor" if hidden else "Hide this sensor",
                           lambda: self.hide_toggled.emit(rid, not hidden))
        else:
            menu.addAction("Expand all", lambda: self._set_all_expanded(True))
            menu.addAction("Collapse all", lambda: self._set_all_expanded(False))
        menu.exec(self.viewport().mapToGlobal(pos))
