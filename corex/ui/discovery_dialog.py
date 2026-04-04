"""
corex/ui/discovery_dialog.py

3-page wizard dialog for identifying ambiguous temperature sensors.
Shown on first run when generic sensors (temp1, temp2, etc.) are detected.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QWidget,
)

from corex.models import HardwareComponent
from corex.sensors.discovery import SensorDiscovery


class DiscoveryDialog(QDialog):
    """
    A 3-page wizard shown on first run when ambiguous sensors are detected.
    
    Pages:
        0 - Introduction
        1 - Running test (3-second CPU load test)
        2 - Results (editable table with identified sensors)
    """
    
    def __init__(self, components: List[HardwareComponent], parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._components = components
        self._page = 0  # 0, 1, 2
        self._mappings: Dict[str, Tuple[str, str]] = {}
        self._timer: Optional[QTimer] = None
        self._progress_steps = 0
        
        self.setWindowTitle("Sensor Identification")
        self.setFixedSize(480, 360)
        self.setStyleSheet(self._get_stylesheet())
        
        self._setup_ui()
        
    def _get_stylesheet(self) -> str:
        """Return dark theme stylesheet matching the rest of the app."""
        return """
            QDialog {
                background-color: #1e1e2e;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #2a2a5a;
                color: #e0e0e0;
                border: 1px solid #3a3a6a;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #3a3a7a;
                border-color: #4a4a8a;
            }
            QPushButton:pressed {
                background-color: #1a1a4a;
            }
            QPushButton:disabled {
                background-color: #1a1a3a;
                color: #666666;
                border-color: #2a2a4a;
            }
            QProgressBar {
                border: 1px solid #3a3a6a;
                border-radius: 4px;
                background-color: #1a1a2a;
                text-align: center;
                color: #e0e0e0;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
            QTableWidget {
                background-color: #1a1a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a6a;
                gridline-color: #3a3a6a;
                font-size: 12px;
                selection-background-color: #2a2a5a;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #2a2a5a;
            }
            QHeaderView::section {
                background-color: #2a2a4a;
                color: #e0e0e0;
                padding: 6px;
                border: 1px solid #3a3a6a;
                font-weight: bold;
            }
        """
    
    def _setup_ui(self):
        """Create the stacked widget and all three pages."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Stacked widget for the 3 pages
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)
        
        # Create pages
        self._create_page_intro()
        self._create_page_test()
        self._create_page_results()
        
        # Show first page
        self._stack.setCurrentIndex(0)
    
    def _create_page_intro(self):
        """Create page 0: Introduction."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Icon
        icon_label = QLabel("🔍")
        icon_font = QFont()
        icon_font.setPointSize(48)
        icon_label.setFont(icon_font)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel("Sensor Identification")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(18)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Description
        desc_text = (
            "CoreX found temperature sensors on your motherboard\n"
            "that couldn't be identified automatically.\n\n"
            "A 3-second test will identify them by measuring\n"
            "their response to a brief CPU load spike.\n"
            "This is completely safe and takes only 3 seconds."
        )
        desc_label = QLabel(desc_text)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        layout.addWidget(desc_label)
        
        layout.addStretch(1)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        skip_button = QPushButton("Skip for now")
        skip_button.clicked.connect(self.reject)
        
        identify_button = QPushButton("🔍 Identify →")
        identify_button.clicked.connect(self._start_test)
        
        button_layout.addWidget(skip_button)
        button_layout.addStretch(1)
        button_layout.addWidget(identify_button)
        
        layout.addLayout(button_layout)
        
        self._stack.addWidget(page)
    
    def _create_page_test(self):
        """Create page 1: Running test."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Title
        title_label = QLabel("🔍 Identifying sensors...")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(16)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setFixedWidth(300)
        layout.addWidget(self._progress_bar)
        
        # Status label
        self._status_label = QLabel("Running CPU load test...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        layout.addWidget(self._status_label)
        
        layout.addStretch(1)
        
        self._stack.addWidget(page)
    
    def _create_page_results(self):
        """Create page 2: Results table."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("✅ Identification complete")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(16)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #4CAF50;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Table
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Raw sensor", "Identified as", "Confidence"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        back_button = QPushButton("← Back")
        back_button.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        
        save_button = QPushButton("✅ Save →")
        save_button.clicked.connect(self._save_and_accept)
        
        button_layout.addWidget(back_button)
        button_layout.addStretch(1)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
        
        self._stack.addWidget(page)
    
    def _start_test(self):
        """Switch to page 1 and start the 3-second test."""
        self._stack.setCurrentIndex(1)
        
        # Reset progress
        self._progress_steps = 0
        self._progress_bar.setValue(0)
        self._status_label.setText("Running CPU load test...")
        
        # Start timer for progress animation
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_progress)
        self._timer.start(100)  # 100ms interval
        
    def _update_progress(self):
        """Update progress bar each timer tick (30 steps = 3 seconds)."""
        self._progress_steps += 1
        progress = min(100, int((self._progress_steps / 30) * 100))
        self._progress_bar.setValue(progress)
        
        if self._progress_steps >= 30:
            self._timer.stop()
            self._timer = None
            self._finish_test()
    
    def _finish_test(self):
        """Run actual discovery and switch to results page."""
        self._status_label.setText("Analyzing sensor responses...")
        
        # Run discovery (in same thread since we already waited 3 seconds)
        discovery = SensorDiscovery()
        self._mappings = discovery.run_discovery(self._components)
        
        # Populate results table
        self._populate_results_table()
        
        # Switch to results page
        self._stack.setCurrentIndex(2)
    
    def _populate_results_table(self):
        """Populate the results table with discovered mappings."""
        self._table.setRowCount(len(self._mappings))
        
        for row, (sensor_id, (label, emoji)) in enumerate(self._mappings.items()):
            # Raw sensor ID
            sensor_item = QTableWidgetItem(sensor_id)
            sensor_item.setFlags(sensor_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, sensor_item)
            
            # Editable label
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 1, label_item)
            
            # Confidence based on delta (emoji from discovery)
            confidence_text = self._get_confidence_text(emoji)
            confidence_item = QTableWidgetItem(confidence_text)
            confidence_item.setFlags(confidence_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 2, confidence_item)
    
    def _get_confidence_text(self, emoji: str) -> str:
        """Convert emoji to confidence text."""
        if emoji == "✅":
            return "✅ High"
        elif emoji == "⚠️":
            return "⚠️ Medium"
        else:
            return "❓ Low — edit manually"
    
    def _save_and_accept(self):
        """Save edited mappings and close dialog."""
        # Read edited labels from table
        for row in range(self._table.rowCount()):
            sensor_id = self._table.item(row, 0).text()
            edited_label = self._table.item(row, 1).text()
            
            if sensor_id in self._mappings:
                original_label, emoji = self._mappings[sensor_id]
                self._mappings[sensor_id] = (edited_label, emoji)
        
        # Save mappings
        discovery = SensorDiscovery()
        discovery.save_mappings(self._mappings)
        
        self.accept()
    
    def get_mappings(self) -> Dict[str, Tuple[str, str]]:
        """Return the discovered (and possibly edited) mappings."""
        return self._mappings