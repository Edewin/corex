"""
corex/ui/dashboard.py

Main dashboard window for CoreX hardware monitoring.
"""

from __future__ import annotations

import socket
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from corex.models import HardwareTree, HardwareComponent, SensorGroup, Sensor
from corex.ui.hardware_tree_widget import HardwareTreeWidget


# ---------------------------------------------------------------------------
# Chart styling constants
# ---------------------------------------------------------------------------

CHART_BACKGROUND = "#0d0d1a"
CHART_GRID_COLOR = "#1a1a3a"
CHART_AXIS_COLOR = "#333355"
CHART_TEXT_COLOR = "#e0e0e0"

# Colors for different metrics
COLOR_CPU_USAGE = "#1D9E75"
COLOR_CPU_TEMP = "#FFA726"
COLOR_GPU_USAGE = "#1D9E75"
COLOR_GPU_TEMP = "#EF5350"
COLOR_GPU_POWER = "#FFA726"
COLOR_NET_DOWN = "#1D9E75"
COLOR_NET_UP = "#FFA726"
COLOR_RAM = "#4CAF50"
COLOR_SWAP = "#FF9800"

# Window dimensions
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
LEFT_PANEL_WIDTH = 320

# History length (60 seconds)
HISTORY_LENGTH = 60


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def create_chart_widget(title: str) -> pg.PlotWidget:
    """Create a styled pyqtgraph PlotWidget with consistent styling."""
    widget = pg.PlotWidget()
    
    # Set background
    widget.setBackground(CHART_BACKGROUND)
    
    # Configure axis
    widget.showGrid(x=True, y=True, alpha=0.3)
    widget.getAxis('left').setPen(CHART_AXIS_COLOR)
    widget.getAxis('bottom').setPen(CHART_AXIS_COLOR)
    widget.getAxis('left').setTextPen(CHART_TEXT_COLOR)
    widget.getAxis('bottom').setTextPen(CHART_TEXT_COLOR)
    
    # Hide x-axis labels for rolling window
    widget.getAxis('bottom').setTicks([])
    
    # Set label styles
    label_style = {'color': CHART_TEXT_COLOR, 'font-size': '10pt'}
    widget.setLabel('left', '', **label_style)
    
    # Disable mouse interaction for cleaner look
    widget.setMouseEnabled(x=False, y=False)
    widget.setMenuEnabled(False)
    
    return widget


def get_color_for_value(value: float, unit: str = "%") -> str:
    """Get color based on value and unit."""
    if unit == "%":
        if value < 60:
            return "#4CAF50"  # Green
        elif value <= 85:
            return "#FFC107"  # Amber
        else:
            return "#F44336"  # Red
    elif unit == "°C":
        if value < 60:
            return "#4CAF50"  # Green
        elif value <= 80:
            return "#FFC107"  # Amber
        else:
            return "#F44336"  # Red
    else:
        return "#1D9E75"  # Default green


# ---------------------------------------------------------------------------
# Main Dashboard Class
# ---------------------------------------------------------------------------

class CoreXDashboard(QMainWindow):
    """Main dashboard window for CoreX hardware monitoring."""
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        
        # Get hostname for window title
        hostname = socket.gethostname()
        self.setWindowTitle(f"CoreX — {hostname}")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Apply dark theme
        self._apply_dark_theme()
        
        # Initialize data storage
        self._history = defaultdict(lambda: deque(maxlen=HISTORY_LENGTH))
        
        # Sensor status
        self._lm_sensors_ok = False
        self._nvml_ok = False
        
        # Build UI
        self._setup_ui()
        
        # Setup update timer (for testing)
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._on_timer_update)
        self._update_timer.start(1000)  # Update every second
        
    def _apply_dark_theme(self) -> None:
        """Apply dark theme to the window."""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: #1a1a2e;
                color: #e0e0e0;
            }}
            QSplitter::handle {{
                background-color: #2a2a4a;
                width: 4px;
            }}
            QTabWidget::pane {{
                border: 1px solid #2a2a4a;
                background-color: #1a1a2e;
            }}
            QTabBar::tab {{
                background-color: #2a2a4a;
                color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #3a3a6a;
            }}
            QTabBar::tab:selected {{
                background-color: #3a3a6a;
                border-bottom: 2px solid #1D9E75;
            }}
            QTabBar::tab:hover {{
                background-color: #3a3a6a;
            }}
            QLabel {{
                color: #e0e0e0;
            }}
        """)
        
    def _setup_ui(self) -> None:
        """Setup the main UI layout."""
        # Create central splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Hardware tree
        left_panel = QWidget()
        left_panel.setMinimumWidth(LEFT_PANEL_WIDTH)
        left_panel.setMaximumWidth(LEFT_PANEL_WIDTH)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        
        tree_label = QLabel("Hardware Tree")
        tree_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #1D9E75;")
        left_layout.addWidget(tree_label)
        
        self.tree_widget = HardwareTreeWidget()
        left_layout.addWidget(self.tree_widget)
        
        splitter.addWidget(left_panel)
        
        # Right panel - Tabs
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs)
        
        # Create tabs
        self._create_overview_tab()
        self._create_cpu_tab()
        self._create_memory_tab()
        self._create_gpu_tab()
        self._create_network_tab()
        
        splitter.addWidget(right_panel)
        
        # Set splitter sizes
        splitter.setSizes([LEFT_PANEL_WIDTH, WINDOW_WIDTH - LEFT_PANEL_WIDTH])
        
        # Create status bar
        self._setup_status_bar()
        
    def _setup_status_bar(self) -> None:
        """Setup the status bar with sensor status."""
        status_bar = self.statusBar()
        
        # Left: timestamp
        self.status_time = QLabel("🕐 --:--:--")
        status_bar.addWidget(self.status_time, 1)
        
        # Center: sensor count
        self.status_sensors = QLabel("📡 0 sensors active")
        status_bar.addPermanentWidget(self.status_sensors)
        
        # Right: sensor status
        self.status_sensor_status = QLabel("lm-sensors ❌   NVML ❌")
        status_bar.addPermanentWidget(self.status_sensor_status)
        
        # Update timer for timestamp
        self._time_timer = QTimer()
        self._time_timer.timeout.connect(self._update_timestamp)
        self._time_timer.start(1000)
        self._update_timestamp()
        
    def _update_timestamp(self) -> None:
        """Update the timestamp in status bar."""
        current_time = time.strftime("%H:%M:%S")
        self.status_time.setText(f"🕐 {current_time}")
        
    def _create_overview_tab(self) -> None:
        """Create the Overview tab with 2x2 grid of charts."""
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # CPU Usage %
        cpu_usage_widget = create_chart_widget("CPU Usage %")
        cpu_usage_widget.setTitle("🔲 CPU Usage %", color=CHART_TEXT_COLOR, size="12pt")
        self.cpu_usage_plot = cpu_usage_widget.plot(pen=COLOR_CPU_USAGE, width=2)
        layout.addWidget(cpu_usage_widget, 0, 0)
        
        # CPU Temperature
        cpu_temp_widget = create_chart_widget("CPU Temperature")
        cpu_temp_widget.setTitle("🌡️ CPU Temperature", color=CHART_TEXT_COLOR, size="12pt")
        self.cpu_temp_plot = cpu_temp_widget.plot(pen=COLOR_CPU_TEMP, width=2)
        layout.addWidget(cpu_temp_widget, 0, 1)
        
        # GPU Usage %
        gpu_usage_widget = create_chart_widget("GPU Usage %")
        gpu_usage_widget.setTitle("🎮 GPU Usage %", color=CHART_TEXT_COLOR, size="12pt")
        self.gpu_usage_plot = gpu_usage_widget.plot(pen=COLOR_GPU_USAGE, width=2)
        layout.addWidget(gpu_usage_widget, 1, 0)
        
        # GPU Temperature
        gpu_temp_widget = create_chart_widget("GPU Temperature")
        gpu_temp_widget.setTitle("🌡️ GPU Temperature", color=CHART_TEXT_COLOR, size="12pt")
        self.gpu_temp_plot = gpu_temp_widget.plot(pen=COLOR_GPU_TEMP, width=2)
        layout.addWidget(gpu_temp_widget, 1, 1)
        
        self.tabs.addTab(tab, "📊 Overview")
        
    def _create_cpu_tab(self) -> None:
        """Create the CPU tab with core utilization bars and frequency charts."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Top: Core utilization bars
        util_label = QLabel("Core Utilization %")
        util_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #1D9E75;")
        layout.addWidget(util_label)
        
        self.cpu_util_graph = pg.GraphicsLayoutWidget()
        self.cpu_util_graph.setBackground(CHART_BACKGROUND)
        self.cpu_util_plot = self.cpu_util_graph.addPlot()
        self.cpu_util_plot.hideAxis('bottom')
        self.cpu_util_plot.hideAxis('left')
        self.cpu_util_plot.setMouseEnabled(x=False, y=False)
        self.cpu_util_bars = pg.BarGraphItem(x=[], height=[], width=0.8, brush="#1D9E75")
        self.cpu_util_plot.addItem(self.cpu_util_bars)
        layout.addWidget(self.cpu_util_graph, 1)
        
        # Bottom: Core frequency lines
        freq_label = QLabel("Core Frequency (GHz)")
        freq_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFA726;")
        layout.addWidget(freq_label)
        
        freq_widget = create_chart_widget("Core Frequencies")
        self.cpu_freq_plots = []  # Will store one plot line per core
        layout.addWidget(freq_widget, 1)
        self.cpu_freq_widget = freq_widget
        
        self.tabs.addTab(tab, "🔲 CPU")
        
    def _create_memory_tab(self) -> None:
        """Create the Memory tab with RAM and Swap usage charts."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # RAM Usage
        ram_label = QLabel("RAM Usage %")
        ram_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #4CAF50;")
        layout.addWidget(ram_label)
        
        ram_widget = create_chart_widget("RAM Usage")
        self.ram_plot = ram_widget.plot(pen=COLOR_RAM, width=2, fillLevel=0, 
                                        brush=(COLOR_RAM + "40"))
        layout.addWidget(ram_widget, 1)
        
        # Swap Usage
        swap_label = QLabel("Swap Usage %")
        swap_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FF9800;")
        layout.addWidget(swap_label)
        
        swap_widget = create_chart_widget("Swap Usage")
        self.swap_plot = swap_widget.plot(pen=COLOR_SWAP, width=2, fillLevel=0,
                                          brush=(COLOR_SWAP + "40"))
        layout.addWidget(swap_widget, 1)
        
        self.tabs.addTab(tab, "🧮 Memory")
        
    def _create_gpu_tab(self) -> None:
        """Create the GPU tab with utilization, temperature, and power charts."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # GPU Utilization
        util_label = QLabel("GPU Utilization %")
        util_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #1D9E75;")
        layout.addWidget(util_label)
        
        util_widget = create_chart_widget("GPU Utilization")
        self.gpu_util_detail_plot = util_widget.plot(pen=COLOR_GPU_USAGE, width=2)
        layout.addWidget(util_widget, 1)
        
        # GPU Temperature
        temp_label = QLabel("GPU Temperature °C")
        temp_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #EF5350;")
        layout.addWidget(temp_label)
        
        temp_widget = create_chart_widget("GPU Temperature")
        self.gpu_temp_detail_plot = temp_widget.plot(pen=COLOR_GPU_TEMP, width=2)
        layout.addWidget(temp_widget, 1)
        
        # GPU Power
        power_label = QLabel("GPU Power (W)")
        power_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFA726;")
        layout.addWidget(power_label)
        
        power_widget = create_chart_widget("GPU Power")
        self.gpu_power_plot = power_widget.plot(pen=COLOR_GPU_POWER, width=2)
        layout.addWidget(power_widget, 1)
        
        self.tabs.addTab(tab, "🎮 GPU")
        
    def _create_network_tab(self) -> None:
        """Create the Network tab with download and upload charts."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Download
        down_label = QLabel("Download (MB/s)")
        down_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #1D9E75;")
        layout.addWidget(down_label)
        
        down_widget = create_chart_widget("Download")
        self.net_down_plot = down_widget.plot(pen=COLOR_NET_DOWN, width=2, fillLevel=0,
                                              brush=(COLOR_NET_DOWN + "40"))
        layout.addWidget(down_widget, 1)
        
        # Upload
        up_label = QLabel("Upload (MB/s)")
        up_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFA726;")
        layout.addWidget(up_label)
        
        up_widget = create_chart_widget("Upload")
        self.net_up_plot = up_widget.plot(pen=COLOR_NET_UP, width=2, fillLevel=0,
                                          brush=(COLOR_NET_UP + "40"))
        layout.addWidget(up_widget, 1)
        
        self.tabs.addTab(tab, "🌐 Network")
        
    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------
    
    def update_dashboard(self, tree: HardwareTree) -> None:
        """
        Update the dashboard with new hardware tree data.
        
        Parameters
        ----------
        tree : HardwareTree
            The hardware tree containing all sensor data.
        """
        # Update the tree widget
        if not self.tree_widget._items:  # First time
            self.tree_widget.build_tree(tree)
        else:
            self.tree_widget.update_tree(tree)
            
        # Extract values into history
        self._extract_history(tree)
        
        # Update sensor count in status bar
        sensor_count = len(tree.all_sensors())
        self.status_sensors.setText(f"📡 {sensor_count} sensors active")
        
        # Update only the visible tab's charts
        self._update_visible_charts()
        
    def _extract_history(self, tree: HardwareTree) -> None:
        """
        Extract values from hardware tree and store in history.
        
        Parameters
        ----------
        tree : HardwareTree
            The hardware tree containing all sensor data.
        """
        # Reset per-core data tracking
        core_count = 0
        freq_count = 0
        
        for component in tree.components:
            if component.component_type == "CPU":
                # Find CPU total utilization and temperature
                for group in component.groups:
                    if group.name == "Utilization":
                        for sensor in group.sensors:
                            if "Total" in sensor.label:
                                self._history["cpu_total"].append(sensor.value)
                            elif "Core" in sensor.label:
                                # Extract core number
                                try:
                                    core_num = int(sensor.label.split()[1])
                                    key = f"cpu_core_{core_num}"
                                    self._history[key].append(sensor.value)
                                    core_count = max(core_count, core_num + 1)
                                except (ValueError, IndexError):
                                    pass
                    elif group.name == "Temperatures":
                        for sensor in group.sensors:
                            if "Package" in sensor.label or "CPU die" in sensor.label:
                                self._history["cpu_temp"].append(sensor.value)
                                break
                        else:
                            if group.sensors:
                                self._history["cpu_temp"].append(group.sensors[0].value)
                    elif group.name == "Frequencies":
                        for sensor in group.sensors:
                            if "Core" in sensor.label:
                                try:
                                    core_num = int(sensor.label.split()[1])
                                    key = f"cpu_freq_{core_num}"
                                    self._history[key].append(sensor.value)
                                    freq_count = max(freq_count, core_num + 1)
                                except (ValueError, IndexError):
                                    pass
                                    
            elif component.component_type == "GPU":
                # Find GPU utilization, temperature, and power
                for group in component.groups:
                    if group.name == "Utilization":
                        for sensor in group.sensors:
                            if "GPU" in sensor.label and sensor.unit == "%":
                                self._history["gpu_util"].append(sensor.value)
                    elif group.name == "Temperatures":
                        for sensor in group.sensors:
                            if "GPU Core" in sensor.label:
                                self._history["gpu_temp"].append(sensor.value)
                                break
                        else:
                            if group.sensors:
                                self._history["gpu_temp"].append(group.sensors[0].value)
                    elif group.name == "Power":
                        for sensor in group.sensors:
                            if "Current Draw" in sensor.label:
                                self._history["gpu_power"].append(sensor.value)
                                break
                                
            elif component.component_type == "System":
                # Memory and swap
                for group in component.groups:
                    if group.name == "Usage":
                        for sensor in group.sensors:
                            if "RAM" in sensor.label or "Memory" in sensor.label:
                                self._history["ram_pct"].append(sensor.value)
                            elif "Swap" in sensor.label:
                                self._history["swap_pct"].append(sensor.value)
                                
            elif component.component_type == "Network":
                # Network traffic
                for group in component.groups:
                    if group.name == "Traffic":
                        for sensor in group.sensors:
                            if "Download" in sensor.label:
                                self._history["net_down"].append(sensor.value)
                            elif "Upload" in sensor.label:
                                self._history["net_up"].append(sensor.value)
        
        # Ensure all history keys have at least one value
        for key in ["cpu_total", "cpu_temp", "gpu_util", "gpu_temp", "gpu_power",
                    "ram_pct", "swap_pct", "net_down", "net_up"]:
            if not self._history[key]:
                self._history[key].append(0.0)
                
        # Track core count for bar chart
        self._core_count = core_count
        self._freq_count = freq_count
        
    def _update_visible_charts(self) -> None:
        """Update only the charts in the currently visible tab."""
        current_tab = self.tabs.currentIndex()
        tab_text = self.tabs.tabText(current_tab)
        
        if tab_text == "📊 Overview":
            self._update_overview_charts()
        elif tab_text == "🔲 CPU":
            self._update_cpu_charts()
        elif tab_text == "🧮 Memory":
            self._update_memory_charts()
        elif tab_text == "🎮 GPU":
            self._update_gpu_charts()
        elif tab_text == "🌐 Network":
            self._update_network_charts()
            
    def _update_overview_charts(self) -> None:
        """Update the Overview tab charts."""
        # CPU Usage %
        if self._history["cpu_total"]:
            self.cpu_usage_plot.setData(list(self._history["cpu_total"]))
            
        # CPU Temperature
        if self._history["cpu_temp"]:
            self.cpu_temp_plot.setData(list(self._history["cpu_temp"]))
            
        # GPU Usage %
        if self._history["gpu_util"]:
            self.gpu_usage_plot.setData(list(self._history["gpu_util"]))
            
        # GPU Temperature
        if self._history["gpu_temp"]:
            self.gpu_temp_plot.setData(list(self._history["gpu_temp"]))
            
    def _update_cpu_charts(self) -> None:
        """Update the CPU tab charts."""
        # Core utilization bars
        if hasattr(self, '_core_count') and self._core_count > 0:
            x_vals = list(range(self._core_count))
            heights = []
            brushes = []
            
            for i in range(self._core_count):
                key = f"cpu_core_{i}"
                if self._history[key]:
                    value = self._history[key][-1]
                    heights.append(value)
                    brushes.append(get_color_for_value(value, "%"))
                else:
                    heights.append(0.0)
                    brushes.append("#666666")
                    
            self.cpu_util_bars.setOpts(x=x_vals, height=heights, brush=brushes)
            
        # Core frequency lines
        if hasattr(self, '_freq_count') and self._freq_count > 0:
            # Clear existing plots
            for plot in self.cpu_freq_plots:
                self.cpu_freq_widget.removeItem(plot)
            self.cpu_freq_plots.clear()
            
            # Create new plots for each core
            for i in range(self._freq_count):
                key = f"cpu_freq_{i}"
                if self._history[key]:
                    color = pg.mkColor(get_color_for_value(self._history[key][-1] if self._history[key] else 0, "GHz"))
                    plot = self.cpu_freq_widget.plot(list(self._history[key]), 
                                                     pen=color, width=1.5,
                                                     name=f"Core {i}")
                    self.cpu_freq_plots.append(plot)
                    
    def _update_memory_charts(self) -> None:
        """Update the Memory tab charts."""
        # RAM Usage
        if self._history["ram_pct"]:
            self.ram_plot.setData(list(self._history["ram_pct"]))
            
        # Swap Usage
        if self._history["swap_pct"]:
            self.swap_plot.setData(list(self._history["swap_pct"]))
            
    def _update_gpu_charts(self) -> None:
        """Update the GPU tab charts."""
        # GPU Utilization
        if self._history["gpu_util"]:
            self.gpu_util_detail_plot.setData(list(self._history["gpu_util"]))
            
        # GPU Temperature
        if self._history["gpu_temp"]:
            self.gpu_temp_detail_plot.setData(list(self._history["gpu_temp"]))
            
        # GPU Power
        if self._history["gpu_power"]:
            self.gpu_power_plot.setData(list(self._history["gpu_power"]))
            
    def _update_network_charts(self) -> None:
        """Update the Network tab charts."""
        # Download
        if self._history["net_down"]:
            self.net_down_plot.setData(list(self._history["net_down"]))
            
        # Upload
        if self._history["net_up"]:
            self.net_up_plot.setData(list(self._history["net_up"]))
            
    def set_sensor_status(self, lm_ok: bool, nvml_ok: bool) -> None:
        """
        Update sensor status in the status bar.
        
        Parameters
        ----------
        lm_ok : bool
            Whether lm-sensors is working.
        nvml_ok : bool
            Whether NVML (NVIDIA Management Library) is working.
        """
        self._lm_sensors_ok = lm_ok
        self._nvml_ok = nvml_ok
        
        lm_status = "✅" if lm_ok else "❌"
        nvml_status = "✅" if nvml_ok else "❌"
        
        self.status_sensor_status.setText(f"lm-sensors {lm_status}   NVML {nvml_status}")
        
    def _on_timer_update(self) -> None:
        """Timer callback for testing - generates dummy data."""
        # This is for testing only - in real use, update_dashboard would be called
        # with real hardware tree data
        pass


# ---------------------------------------------------------------------------
# Test function
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    # Set platform for headless testing if needed
    if not QApplication.instance():
        app = QApplication(sys.argv)
        
    # Create and show dashboard
    dash = CoreXDashboard()
    dash.show()
    
    # Set dummy sensor status
    dash.set_sensor_status(True, True)
    
    print("Dashboard visible — close to exit")
    sys.exit(app.exec())