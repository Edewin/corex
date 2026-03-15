import os
import sys
os.environ['QT_QPA_PLATFORM'] = 'xcb'
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'

import subprocess
import time
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMessageBox,
    QMenu,
    QStyle,
    QSystemTrayIcon,
)

from corex.models import HardwareTree, HardwareComponent
from corex.sensors.cpu import build_cpu_component, get_cpu_usage, get_cpu_frequencies
from corex.sensors.lm_reader import get_all_lm_components
from corex.sensors.gpu import get_gpu_components
from corex.sensors.memory import build_memory_component
from corex.sensors.storage import get_storage_components
from corex.sensors.network import get_network_components
from corex.sensors.discovery import SensorDiscovery, needs_discovery
from corex.ui.dashboard import CoreXDashboard
from corex.ui.widget import CoreXWidget
from corex.ui.discovery_dialog import DiscoveryDialog


# ============================================================================
# SensorPoller — background thread that reads hardware data
# ============================================================================

class SensorPoller(QThread):
    """Background thread that polls hardware sensors every second."""

    data_ready       = pyqtSignal(object)   # HardwareTree
    discovery_needed = pyqtSignal(object)   # List[HardwareComponent]
    status_update    = pyqtSignal(bool, bool)  # lm_ok, nvml_ok

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_flag = False
        self._tree: Optional[HardwareTree] = None

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        # ── Step 1: Build initial HardwareTree ────────────────────────
        cpu          = build_cpu_component()
        lm_components = get_all_lm_components(cpu_component=cpu)
        gpu_components = get_gpu_components()
        mem          = build_memory_component()
        storage      = get_storage_components()
        nets         = get_network_components()

        lm_ok   = len(lm_components) > 0
        nvml_ok = any(g.chip_name == 'nvml' for g in gpu_components)

        all_components = lm_components + gpu_components + [mem] + storage + nets

        self._tree = HardwareTree(
            components=all_components,
            last_updated=time.time()
        )

        # ── Step 2: Apply saved sensor mappings ───────────────────────
        sd = SensorDiscovery()
        mappings = sd.load_saved_mappings()
        if mappings:
            sd.apply_mappings(self._tree.components, mappings)

        # ── Step 3: Check if discovery needed ─────────────────────────
        if needs_discovery(self._tree.components):
            self.discovery_needed.emit(self._tree.components)

        # ── Step 4: Emit initial data and status ──────────────────────
        self.status_update.emit(lm_ok, nvml_ok)
        self.data_ready.emit(self._tree)

        # ── Step 5: Polling loop every 1 second ───────────────────────
        while not self._stop_flag:
            time.sleep(1)
            self._update_tree()
            self._tree.last_updated = time.time()
            self.data_ready.emit(self._tree)

    # ------------------------------------------------------------------
    # In-place tree update
    # ------------------------------------------------------------------

    def _update_tree(self) -> None:
        """Update all sensor values in-place without rebuilding the tree."""
        if self._tree is None:
            return

        # Build lookup maps for efficient matching
        components_by_name: Dict[str, HardwareComponent] = {
            c.name: c for c in self._tree.components
        }

        # ── CPU ───────────────────────────────────────────────────────
        new_usage_group = get_cpu_usage()
        new_freq_group  = get_cpu_frequencies()

        for comp in self._tree.components:
            if comp.chip_name == "cpu":
                for group in comp.groups:
                    if group.name == "Utilization":
                        new_sensors_by_id = {
                            s.sensor_id: s for s in new_usage_group.sensors
                        }
                        for sensor in group.sensors:
                            if sensor.sensor_id in new_sensors_by_id:
                                sensor.update(new_sensors_by_id[sensor.sensor_id].value)

                    elif group.name == "Frequencies":
                        new_sensors_by_id = {
                            s.sensor_id: s for s in new_freq_group.sensors
                        }
                        for sensor in group.sensors:
                            if sensor.sensor_id in new_sensors_by_id:
                                sensor.update(new_sensors_by_id[sensor.sensor_id].value)
                break

        # ── GPU ───────────────────────────────────────────────────────
        new_gpus = get_gpu_components()
        new_gpus_by_name = {g.name: g for g in new_gpus}

        for comp in self._tree.components:
            if comp.chip_name in ("nvml",) or comp.chip_name.startswith("drm_card"):
                new_gpu = new_gpus_by_name.get(comp.name)
                if new_gpu is None:
                    continue
                new_sensors_by_id: Dict[str, Any] = {}
                for grp in new_gpu.groups:
                    for s in grp.sensors:
                        new_sensors_by_id[s.sensor_id] = s
                for group in comp.groups:
                    for sensor in group.sensors:
                        if sensor.sensor_id in new_sensors_by_id:
                            sensor.update(new_sensors_by_id[sensor.sensor_id].value)

        # ── Memory ────────────────────────────────────────────────────
        new_mem = build_memory_component()
        new_mem_sensors: Dict[str, Any] = {}
        for grp in new_mem.groups:
            for s in grp.sensors:
                new_mem_sensors[s.sensor_id] = s

        for comp in self._tree.components:
            if comp.chip_name == "memory":
                for group in comp.groups:
                    for sensor in group.sensors:
                        if sensor.sensor_id in new_mem_sensors:
                            sensor.update(new_mem_sensors[sensor.sensor_id].value)
                break

        # ── Storage ───────────────────────────────────────────────────
        new_storage = get_storage_components()
        new_storage_sensors: Dict[str, Any] = {}
        for st in new_storage:
            for grp in st.groups:
                for s in grp.sensors:
                    new_storage_sensors[s.sensor_id] = s

        for comp in self._tree.components:
            if comp.component_type == "Storage":
                for group in comp.groups:
                    for sensor in group.sensors:
                        if sensor.sensor_id in new_storage_sensors:
                            sensor.update(new_storage_sensors[sensor.sensor_id].value)

        # ── Network ───────────────────────────────────────────────────
        new_nets = get_network_components()
        new_net_sensors: Dict[str, Any] = {}
        for net in new_nets:
            for grp in net.groups:
                for s in grp.sensors:
                    new_net_sensors[s.sensor_id] = s

        for comp in self._tree.components:
            if comp.component_type == "Network":
                for group in comp.groups:
                    for sensor in group.sensors:
                        if sensor.sensor_id in new_net_sensors:
                            sensor.update(new_net_sensors[sensor.sensor_id].value)

        # ── lm-sensors (temperatures, fans, voltages) ─────────────────
        new_lm = get_all_lm_components()
        new_lm_sensors: Dict[str, Any] = {}
        for lm_comp in new_lm:
            for grp in lm_comp.groups:
                for s in grp.sensors:
                    new_lm_sensors[s.sensor_id] = s

        for comp in self._tree.components:
            # lm-sensors components have chip_names like "coretemp-isa-0000",
            # "nct6795-isa-0290", etc. — they are NOT "cpu", "memory", "nvml",
            # "drm_card*", or a network/storage chip_name.
            if comp.chip_name in ("cpu", "memory"):
                continue
            if comp.chip_name.startswith("drm_card"):
                continue
            if comp.chip_name == "nvml":
                continue
            if comp.component_type in ("Storage", "Network"):
                continue

            for group in comp.groups:
                for sensor in group.sensors:
                    if sensor.sensor_id in new_lm_sensors:
                        sensor.update(new_lm_sensors[sensor.sensor_id].value)

    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._stop_flag = True


# ============================================================================
# CoreXApp — wires everything together
# ============================================================================

class CoreXApp:
    """Application controller: tray icon, windows, poller."""

    def __init__(self, app: QApplication) -> None:
        self.app = app

        # ── 1. Dark palette ───────────────────────────────────────────
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,      QColor(26, 26, 46))
        palette.setColor(QPalette.ColorRole.WindowText,  QColor(224, 224, 224))
        palette.setColor(QPalette.ColorRole.Base,        QColor(13, 13, 26))
        palette.setColor(QPalette.ColorRole.Text,        QColor(224, 224, 224))
        palette.setColor(QPalette.ColorRole.Button,      QColor(42, 42, 74))
        palette.setColor(QPalette.ColorRole.ButtonText,  QColor(224, 224, 224))
        palette.setColor(QPalette.ColorRole.Highlight,   QColor(29, 158, 117))
        app.setPalette(palette)

        # ── 2. Load application icon ──────────────────────────────────
        from PyQt6.QtGui import QIcon, QPixmap
        from PyQt6.QtCore import QSize
        import os
        
        # Try to find the icon file
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
        icon_path = os.path.join(assets_dir, 'corex_icon.svg')
        
        app_icon = None
        if os.path.exists(icon_path):
            # Try to load SVG directly
            app_icon = QIcon(icon_path)
            
            # Force rasterize at multiple sizes for window icon
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                app_icon = QIcon(pixmap)
            
            app.setWindowIcon(app_icon)
        else:
            # fallback to system icon
            app_icon = app.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            )
            app.setWindowIcon(app_icon)

        # ── 3. Create windows ─────────────────────────────────────────
        self.dashboard = CoreXDashboard()
        self.widget    = CoreXWidget()
        
        # Set icon on windows
        if app_icon:
            self.dashboard.setWindowIcon(app_icon)
            self.widget.setWindowIcon(app_icon)

        # ── 4. Tray icon ──────────────────────────────────────────────
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(app_icon if app_icon else app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

        tray_menu = QMenu()
        act_dashboard = tray_menu.addAction("🖥️ Show Dashboard")
        act_widget    = tray_menu.addAction("📌 Show Widget")
        tray_menu.addSeparator()
        act_quit      = tray_menu.addAction("❌ Quit CoreX")

        act_dashboard.triggered.connect(lambda: (
            self.dashboard.show(),
            self.dashboard.raise_()
        ))
        act_widget.triggered.connect(lambda: (
            self.widget.show(),
            self.widget.raise_()
        ))
        act_quit.triggered.connect(self.quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.setToolTip("CoreX Hardware Monitor")
        self.tray.show()

        # Double-click tray → show dashboard
        self.tray.activated.connect(self._on_tray_activated)

        # ── 4. Connect widget signals ─────────────────────────────────
        self.widget.open_dashboard.connect(
            lambda: (self.dashboard.show(), self.dashboard.raise_())
        )
        self.widget.quit_app.connect(self.quit)

        # ── 5. Create and start poller ────────────────────────────────
        self.poller = SensorPoller()
        self.poller.data_ready.connect(self._on_data)
        self.poller.discovery_needed.connect(self._on_discovery_needed)
        self.poller.status_update.connect(self.dashboard.set_sensor_status)
        self.poller.start()

        # ── 6. Show widget immediately; dashboard stays hidden ────────
        self.widget.show()

    # ------------------------------------------------------------------
    # Tray activation
    # ------------------------------------------------------------------

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.dashboard.show()
            self.dashboard.raise_()

    # ------------------------------------------------------------------
    # Data callbacks
    # ------------------------------------------------------------------

    def _on_data(self, tree: HardwareTree) -> None:
        self.dashboard.update_dashboard(tree)
        summary = self._build_widget_summary(tree)
        self.widget.update_metrics(summary)

    def _build_widget_summary(self, tree: HardwareTree) -> Dict[str, Any]:
        """Build the summary dict consumed by CoreXWidget.update_metrics()."""
        summary: Dict[str, Any] = {}

        for comp in tree.components:
            # ── CPU ───────────────────────────────────────────────────
            if comp.component_type == "CPU":
                for group in comp.groups:
                    if group.name == "Utilization":
                        for sensor in group.sensors:
                            if "Total" in sensor.label:
                                summary["CPU %"] = {
                                    "value":          sensor.value,
                                    "unit":           "%",
                                    "component_icon": "🔲",
                                    "group_icon":     "📊",
                                }
                                break
                    elif group.name == "Temperatures":
                        # Prefer Package / CPU die; fall back to first sensor
                        chosen = None
                        for sensor in group.sensors:
                            if "Package" in sensor.label or "CPU die" in sensor.label:
                                chosen = sensor
                                break
                        if chosen is None and group.sensors:
                            chosen = group.sensors[0]
                        if chosen is not None:
                            summary["CPU Temp"] = {
                                "value":          chosen.value,
                                "unit":           "°C",
                                "component_icon": "🔲",
                                "group_icon":     "🌡️",
                            }

            # ── GPU ───────────────────────────────────────────────────
            elif comp.component_type == "GPU":
                for group in comp.groups:
                    if group.name == "Utilization":
                        for sensor in group.sensors:
                            if "GPU" in sensor.label and sensor.unit == "%":
                                summary["GPU %"] = {
                                    "value":          sensor.value,
                                    "unit":           "%",
                                    "component_icon": "🎮",
                                    "group_icon":     "📊",
                                }
                                break
                    elif group.name == "Temperatures":
                        for sensor in group.sensors:
                            if "GPU Core" in sensor.label:
                                summary["GPU Temp"] = {
                                    "value":          sensor.value,
                                    "unit":           "°C",
                                    "component_icon": "🎮",
                                    "group_icon":     "🌡️",
                                }
                                break

            # ── Memory ────────────────────────────────────────────────
            elif comp.chip_name == "memory":
                for group in comp.groups:
                    if group.name == "RAM":
                        for sensor in group.sensors:
                            if sensor.sensor_id == "mem_usage":
                                summary["RAM %"] = {
                                    "value":          sensor.value,
                                    "unit":           "%",
                                    "component_icon": "🧮",
                                    "group_icon":     "🧮",
                                }
                                break

            # ── Network (first active interface) ──────────────────────
            elif comp.component_type == "Network" and "Download" not in summary:
                for group in comp.groups:
                    if group.name == "Traffic":
                        for sensor in group.sensors:
                            if "Download" in sensor.label:
                                summary["Download"] = {
                                    "value":          sensor.value,
                                    "unit":           "MB/s",
                                    "component_icon": "🌐",
                                    "group_icon":     "🔄",
                                }
                            elif "Upload" in sensor.label:
                                summary["Upload"] = {
                                    "value":          sensor.value,
                                    "unit":           "MB/s",
                                    "component_icon": "🌐",
                                    "group_icon":     "🔄",
                                }

        return summary

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _on_discovery_needed(self, components: List[HardwareComponent]) -> None:
        dialog = DiscoveryDialog(components=components, parent=self.dashboard)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mappings = SensorDiscovery().load_saved_mappings()
            if mappings and self.poller._tree is not None:
                SensorDiscovery().apply_mappings(
                    self.poller._tree.components, mappings
                )

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def quit(self) -> None:
        self.poller.stop()
        self.poller.wait(2000)
        self.tray.hide()
        self.app.quit()


# ============================================================================
# main()
# ============================================================================

def main() -> None:
    # ── 1. Check lm-sensors ───────────────────────────────────────────
    result = subprocess.run(['which', 'sensors'], capture_output=True)
    if result.returncode != 0:
        # Need a minimal QApplication to show the warning box
        _tmp_app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.warning(
            None,
            "⚠️ lm-sensors not found",
            "lm-sensors is required for temperature and fan monitoring.\n\n"
            "Install with:\n"
            "  sudo apt install lm-sensors\n"
            "  sudo sensors-detect\n\n"
            "CoreX will start with limited functionality."
        )

    # ── 3. Create QApplication ────────────────────────────────────────
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("CoreX")
    app.setApplicationVersion("0.1.0")
    app.setQuitOnLastWindowClosed(False)   # CRITICAL: keep alive when window closes

    # ── 4. Check system tray ──────────────────────────────────────────
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "CoreX", "System tray not available.")
        sys.exit(1)

    # ── 5. Start app ──────────────────────────────────────────────────
    corex_app = CoreXApp(app)
    sys.exit(app.exec())


# ============================================================================

if __name__ == '__main__':
    main()
