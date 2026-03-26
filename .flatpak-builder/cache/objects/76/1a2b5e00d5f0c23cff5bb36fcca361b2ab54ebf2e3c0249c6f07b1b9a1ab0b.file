from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Sensor:
    """Represents a single hardware sensor measurement."""
    label: str          # "Package (CPU die)", "Core 0", etc.
    value: float
    unit: str           # "°C", "%", "RPM", "GHz", "W", "MB/s"
    min_val: float      # session minimum (reset on app start)
    max_val: float      # session maximum
    sensor_id: str      # internal unique id e.g. "coretemp_0_temp1"

    def update(self, new_value: float) -> None:
        """Update sensor value and track min/max values."""
        self.value = new_value
        if new_value < self.min_val:
            self.min_val = new_value
        if new_value > self.max_val:
            self.max_val = new_value

@dataclass
class SensorGroup:
    """Group of related sensors with display metadata."""
    name: str           # "Temperatures", "Fans", "Utilization" etc.
    icon: str           # emoji for this group type
    sensors: List[Sensor] = field(default_factory=list)

    GROUP_ICONS = {
        "Temperatures":  "🌡️",
        "Fans":          "🌀",
        "Utilization":   "📊",
        "Frequencies":   "⚡",
        "Power":         "🔋",
        "Memory":        "🧮",
        "Voltages":      "⚡",
        "Traffic":       "🔄",
        "Status":        "🔗",
        "Usage":         "💿",
        "Activity":      "📈",
        "RAM":           "🧮",
        "Swap":          "♻️",
    }

@dataclass
class HardwareComponent:
    """Represents a physical hardware component with sensor groups."""
    name: str           # "Intel Core i7-12700K"
    component_type: str # "CPU", "GPU", "Motherboard", etc.
    chip_name: str      # raw lm-sensors chip name
    icon: str           # emoji for component type
    groups: List[SensorGroup] = field(default_factory=list)
    collapsed: bool = False

    COMPONENT_ICONS = {
        "CPU":         "🔲",
        "GPU":         "🎮",
        "Motherboard": "⚙️",
        "Storage":     "💾",
        "Network":     "🌐",
        "System":      "🖥️",
        "Battery":     "🔋",
    }

    def get_primary_temp(self) -> Optional[float]:
        """Get most relevant temperature for quick display."""
        for group in self.groups:
            if group.name == "Temperatures":
                for sensor in group.sensors:
                    if "Package" in sensor.label:
                        return sensor.value
                    if "CPU die" in sensor.label:
                        return sensor.value
                return group.sensors[0].value if group.sensors else None
        return None

    def get_primary_util(self) -> Optional[float]:
        """Get most relevant utilization percentage."""
        for group in self.groups:
            if group.name == "Utilization":
                for sensor in group.sensors:
                    if "Total" in sensor.label:
                        return sensor.value
                    if "GPU" in sensor.label:
                        return sensor.value
                return group.sensors[0].value if group.sensors else None
        return None

@dataclass
class HardwareTree:
    """Top-level container for all hardware components."""
    components: List[HardwareComponent] = field(default_factory=list)
    last_updated: float = 0.0  # unix timestamp

    def get_component(self, component_type: str) -> Optional[HardwareComponent]:
        """Get first component of specified type."""
        return next(
            (c for c in self.components if c.component_type == component_type),
            None
        )

    def all_sensors(self) -> List[Sensor]:
        """Get flattened list of all sensors in the system."""
        return [
            sensor
            for component in self.components
            for group in component.groups
            for sensor in group.sensors
        ]

    def to_widget_summary(self) -> Dict[str, float]:
        """Create simplified summary for display widgets."""
        summary = {}
        for component in self.components:
            if temp := component.get_primary_temp():
                summary[f"{component.component_type} Temp"] = temp
            if util := component.get_primary_util():
                summary[f"{component.component_type} %"] = util
        return summary

# Unit tests
if __name__ == "__main__":
    # Test Sensor update functionality
    sensor = Sensor(
        label="Test Sensor",
        value=25.0,
        unit="°C",
        min_val=25.0,
        max_val=25.0,
        sensor_id="test_sensor"
    )
    sensor.update(30.0)
    assert sensor.value == 30.0
    assert sensor.min_val == 25.0
    assert sensor.max_val == 30.0
    sensor.update(20.0)
    assert sensor.min_val == 20.0

    # Test HardwareTree summary generation
    cpu_group = SensorGroup(
        name="Temperatures",
        icon=SensorGroup.GROUP_ICONS["Temperatures"],
        sensors=[Sensor(
            label="Package",
            value=45.0,
            unit="°C",
            min_val=40.0,
            max_val=50.0,
            sensor_id="cpu_temp"
        )]
    )
    cpu = HardwareComponent(
        name="Test CPU",
        component_type="CPU",
        chip_name="cpu_chip",
        icon=HardwareComponent.COMPONENT_ICONS["CPU"],
        groups=[cpu_group]
    )
    tree = HardwareTree(components=[cpu])
    summary = tree.to_widget_summary()
    assert "CPU Temp" in summary
    assert summary["CPU Temp"] == 45.0

    print("All tests passed!")