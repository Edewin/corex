"""CoreX entry point: wires settings, the engine thread, the main window, the widget and the tray."""

from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from corex import __version__
from corex.app import alerts, autostart, report
from corex.app.poller import History, Poller
from corex.app.recorder import Recorder
from corex.app.settings import Settings
from corex.core.engine import Engine
from corex.core.model import Snapshot
from corex.ui import pick, theme
from corex.ui.about import AboutDialog
from corex.ui.dashboard import MainWindow
from corex.ui.dialogs import AlertDialog, ReportDialog
from corex.ui.firstrun import FirstRunDialog
from corex.ui.history import HistoryDialog
from corex.ui.overlay import Overlay

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "corex_icon.svg")


class CoreXApp:
    def __init__(self, app: QApplication, start_hidden: bool = False):
        self.app = app
        self.settings = Settings.load()
        theme.apply(self.settings.theme)
        app.setPalette(theme.palette())
        app.setStyleSheet(theme.STYLESHEET)
        app.styleHints().colorSchemeChanged.connect(
            lambda _: self.set_theme("system") if self.settings.theme == "system" else None)
        self.history = History()
        self.engine = Engine(labels=self.settings.labels)
        try:
            self.recorder: Recorder | None = Recorder(keep_days=self.settings.history_days)
        except Exception as e:        # read-only home, broken database: run without history
            print(f"CoreX: history disabled ({e})", file=sys.stderr)
            self.recorder = None
        self.alerts = alerts.AlertWatcher()
        if self.settings.view_mode is None and not start_hidden:
            self.settings.view_mode, self.settings.widget_visible = FirstRunDialog.ask()
            self.settings.save()

        self.tray = None
        self._make_window()
        self.overlay = Overlay(self.settings.widget_opacity)
        if self.settings.widget_readings is not None:
            self.overlay.set_readings(self.settings.widget_readings)
        if self.settings.widget_pos:
            self.overlay.move(*self.settings.widget_pos)
        self._setup_tray()

        o = self.overlay
        o.open_dashboard.connect(self.show_window)
        o.choose_values.connect(self._choose_values)
        o.hide_requested.connect(lambda: self.set_widget_visible(False))
        o.quit_requested.connect(self.quit)
        o.opacity_changed.connect(lambda v: self._save(widget_opacity=v))
        o.moved.connect(lambda x, y: self._save(widget_pos=[x, y]))

        self.poller = Poller(self.engine, self.settings.interval_s)
        self.poller.snapshot.connect(self._on_snapshot)
        self.poller.failed.connect(lambda msg: print("CoreX: sensor read failed\n" + msg, file=sys.stderr))
        self.poller.start()

        if not start_hidden:
            self.window.showMaximized()
        self.set_widget_visible(self.settings.widget_visible)

    # ------------------------------------------------------------------
    def _make_window(self) -> None:
        self.window = w = MainWindow(self.history, self.settings)
        if self.settings.widget_readings is not None:
            w.widget_ids = set(self.settings.widget_readings)
        w.hide_on_close = self.tray is not None
        w.interval_changed.connect(self._set_interval)
        w.reset_minmax.connect(self.engine.reset_minmax)
        w.toggle_widget.connect(self.toggle_widget)
        w.renamed.connect(self._rename)
        w.widget_toggled.connect(self._widget_toggled)
        w.view_changed.connect(lambda m: self._save(view_mode=m))
        w.prefs_changed.connect(self.settings.save)
        w.autostart_changed.connect(self._set_autostart)
        w.about_requested.connect(lambda: AboutDialog(w).exec())
        w.quit_requested.connect(self.quit)
        w.theme_changed.connect(self.set_theme)
        w.history_requested.connect(self.show_history)
        w.alert_requested.connect(self.edit_alert)
        w.report_requested.connect(self.show_report)

    def set_theme(self, mode: str) -> None:
        """Switch the colours; the main window is rebuilt so every icon and chart takes them."""
        if mode != self.settings.theme:
            self._save(theme=mode)
        theme.apply(mode)
        self.app.setPalette(theme.palette())
        self.app.setStyleSheet(theme.STYLESHEET)
        old = self.window
        was_visible = old.isVisible()
        old.hide_on_close = True               # closing the old one must not quit
        self.settings.last_page = old.page
        self._make_window()
        self.window.widget_btn.setChecked(self.overlay.isVisible())
        if self.history.latest:
            self.window.on_snapshot(self.history.latest)
        if was_visible:
            self.window.showMaximized()
        old.hide()
        old.deleteLater()
        self.overlay.restyle()

    def show_history(self, reading_id: str = "") -> None:
        if self.recorder is None:
            self.window.statusBar().showMessage("History is not available: CoreX cannot write its "
                                                "history file in ~/.local/share/corex.", 10000)
            return
        self.recorder.flush()
        dlg = HistoryDialog(self.recorder, reading_id or None, self.settings.history_days, self.window)
        dlg.exec()
        if dlg.keep_days != self.settings.history_days:
            self._save(history_days=dlg.keep_days)

    def edit_alert(self, reading_id: str) -> None:
        snap = self.history.latest
        dev = next((d for d in snap.devices if d.reading(reading_id)), None) if snap else None
        if dev is None:
            return
        dlg = AlertDialog(dev.name, dev.reading(reading_id), self.settings.alerts.get(reading_id), self.window)
        if dlg.exec() and dlg.result_rule is not None:
            rules = dict(self.settings.alerts)
            if dlg.result_rule:
                rules[reading_id] = dlg.result_rule
            else:
                rules.pop(reading_id, None)
            self._save(alerts=rules)
            self._check_alerts(snap)
            self.window.on_snapshot(snap)

    def show_report(self) -> None:
        if self.history.latest:
            ReportDialog(report.build(self.history.latest), self.window).exec()

    def _check_alerts(self, snap: Snapshot) -> None:
        over, tell = self.alerts.check(snap, self.settings.alerts)
        theme.alerting = over
        for title, body in tell:
            alerts.notify(title, body, self.tray)

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.app.windowIcon())
        self.tray.setToolTip(f"CoreX {__version__}")
        menu = QMenu()
        menu.addAction("Open CoreX", self.show_window)
        self.tray_widget_action = menu.addAction("Show widget", self.toggle_widget)
        menu.addSeparator()
        menu.addAction("Quit CoreX", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self.window.hide_on_close = True        # closing the window keeps CoreX in the tray

    def _on_snapshot(self, snap: Snapshot) -> None:
        self.history.add(snap)
        if self.recorder is not None:
            try:
                self.recorder.add(snap)
            except Exception as e:    # disk full, database locked: keep monitoring
                print(f"CoreX: history write failed ({e})", file=sys.stderr)
        theme.alerting = set()
        if self.settings.alerts:
            self._check_alerts(snap)
        if self.settings.widget_readings is None:          # first run: sensible defaults
            self.settings.widget_readings = pick.default_widget(snap)
            self.overlay.set_readings(self.settings.widget_readings)
            self.window.widget_ids = set(self.settings.widget_readings)
            self.settings.save()
        self.window.on_snapshot(snap)
        if self.overlay.isVisible():
            self.overlay.on_snapshot(snap)

    def _save(self, **changes) -> None:
        for k, v in changes.items():
            setattr(self.settings, k, v)
        self.settings.save()

    def _set_interval(self, seconds: float) -> None:
        self.poller.set_interval(seconds)
        self._save(interval_s=seconds)

    def _rename(self, reading_id: str, label: str) -> None:
        labels = dict(self.settings.labels)
        if label:
            labels[reading_id] = label
        else:
            labels.pop(reading_id, None)
        self.engine.labels = labels
        self._save(labels=labels)

    def _widget_toggled(self, reading_id: str, on: bool) -> None:
        ids = list(self.settings.widget_readings or [])
        if on and reading_id not in ids:
            ids.append(reading_id)
        elif not on and reading_id in ids:
            ids.remove(reading_id)
        self.window.widget_ids = set(ids)
        self.overlay.set_readings(ids)
        if self.history.latest:
            self.overlay.on_snapshot(self.history.latest)
        self._save(widget_readings=ids)
        if on:
            self.set_widget_visible(True)

    def _set_autostart(self, on: bool) -> None:
        error = autostart.set_enabled(on)
        if error:
            self.window.set_autostart_checked(not on)
            self.window.statusBar().showMessage(error, 10000)
        else:
            self._save(autostart=on)

    def _choose_values(self) -> None:
        self.show_window()
        self.window.statusBar().showMessage(
            "Tick the Widget column next to the values you want." if self.window.mode == "list" else
            "Open a device on the left and tick the Widget column next to the values you want.", 8000)

    # ------------------------------------------------------------------
    def show_window(self) -> None:
        if self.window.isMinimized() or not self.window.isVisible():
            self.window.showMaximized()
        self.window.raise_()
        self.window.activateWindow()

    def set_widget_visible(self, visible: bool) -> None:
        self.overlay.setVisible(visible)
        if visible and self.history.latest:
            self.overlay.on_snapshot(self.history.latest)
        self.window.widget_btn.setChecked(visible)
        if self.tray:
            self.tray_widget_action.setText("Hide widget" if visible else "Show widget")
        if self.settings.widget_visible != visible:
            self._save(widget_visible=visible)

    def toggle_widget(self) -> None:
        self.set_widget_visible(not self.overlay.isVisible())

    def quit(self) -> None:
        self._save(last_page=self.window.page)
        self.poller.stop()
        if self.recorder is not None:
            self.recorder.close()
        if self.tray:
            self.tray.hide()
        self.overlay.close()
        self.app.quit()


def main() -> None:
    parser = argparse.ArgumentParser(prog="corex", description="Hardware monitor for Linux")
    parser.add_argument("--hidden", action="store_true", help="start with only the widget and tray icon")
    parser.add_argument("--version", action="version", version=f"CoreX {__version__}")
    args, qt_args = parser.parse_known_args()

    # The floating widget can only be placed and kept on top through X11; on a Wayland
    # session run through XWayland unless the user picked a platform explicitly.
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY") \
            and "QT_QPA_PLATFORM" not in os.environ and "-platform" not in qt_args:
        os.environ["QT_QPA_PLATFORM"] = "xcb;wayland"      # Wayland only if XWayland is missing

    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("CoreX")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("io.github.edewin.corex")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    corex = CoreXApp(app, start_hidden=args.hidden)  # noqa: F841 (kept alive for the event loop)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
