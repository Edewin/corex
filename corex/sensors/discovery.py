import json
import os
import threading
import time
from dataclasses import replace
from typing import Dict, List, Tuple

from corex.models import HardwareComponent
from corex.sensors.lm_reader import get_all_lm_components


class SensorDiscovery:
    def run_discovery(
        self, 
        lm_components: List[HardwareComponent],
        duration_secs: float = 3.0
    ) -> Dict[str, Tuple[str, str]]:
        # Step 1: Identify candidate sensors
        candidates = []
        for comp in lm_components:
            for group in comp.groups:
                for sensor in group.sensors:
                    label = sensor.label.lower()
                    # chip derived from sensor_id prefix
                    chip = sensor.sensor_id.split("_")[0].lower() if sensor.sensor_id else ""
                    
                    generic_label = any(
                        f"temperature {i}" in label or label.endswith(f"temp{i}")
                        for i in (1, 2, 3)
                    ) or "unidentified" in label
                    
                    motherboard_chip = any(
                        chip.startswith(prefix)
                        for prefix in ("nct6", "it8", "acpitz", "w83")
                    )
                    
                    if generic_label and motherboard_chip:
                        candidates.append((comp, sensor))

        # Step 2: Record baselines
        baselines = {(id(c), s.sensor_id): s.value for c, s in candidates}

        # Step 3: Spawn CPU load threads
        def cpu_load():
            end = time.time() + duration_secs
            while time.time() < end:
                _ = sum(range(50000))

        threads = [threading.Thread(target=cpu_load) for _ in range(2)]
        [t.start() for t in threads]

        # Step 4: Poll sensors during load
        time.sleep(duration_secs + 0.5)
        updated = get_all_lm_components(cpu_component=lm_components[0] if lm_components else None)

        # Step 5: Calculate deltas
        mappings = {}
        for comp in updated:
            for group in comp.groups:
                for sensor in group.sensors:
                    key = (id(comp), sensor.sensor_id)
                    if key in baselines:
                        delta = sensor.value - baselines[key]
                        
                        if delta > 3.0:
                            label = "CPU Temperature (Socket)"
                        elif 1.0 <= delta <= 3.0:
                            label = "System Temperature"
                        else:
                            label = "PCH / Chipset Temperature"
                        
                        mappings[sensor.sensor_id] = (label, "🌡️")

        return mappings

    def load_saved_mappings(
        self, 
        path: str = "~/.config/corex/sensor_mappings.json"
    ) -> Dict[str, Tuple[str, str]]:
        expanded = os.path.expanduser(path)
        try:
            with open(expanded, 'r') as f:
                data = json.load(f)
                return {k: tuple(v) for k, v in data.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_mappings(
        self,
        mappings: Dict[str, Tuple[str, str]],
        path: str = "~/.config/corex/sensor_mappings.json"
    ) -> None:
        expanded = os.path.expanduser(path)
        os.makedirs(os.path.dirname(expanded), exist_ok=True)
        
        with open(expanded, 'w') as f:
            json.dump(
                {k: list(v) for k, v in mappings.items()},
                f,
                indent=2
            )

    def apply_mappings(
        self,
        components: List[HardwareComponent],
        mappings: Dict[str, Tuple[str, str]]
    ) -> List[HardwareComponent]:
        updated = []
        for comp in components:
            new_groups = []
            for group in comp.groups:
                new_sensors = []
                for sensor in group.sensors:
                    if sensor.sensor_id in mappings:
                        label, emoji = mappings[sensor.sensor_id]
                        new_sensor = replace(
                            sensor,
                            label=f"{emoji} {label}"
                        )
                        new_sensors.append(new_sensor)
                    else:
                        new_sensors.append(sensor)
                new_groups.append(replace(group, sensors=new_sensors))
            updated.append(replace(comp, groups=new_groups))
        return updated


def needs_discovery(components: List[HardwareComponent]) -> bool:
    patterns = (
        "Temperature 1",
        "Temperature 2", 
        "Temperature 3",
        "Temperature (unidentified)"
    )
    
    for comp in components:
        for group in comp.groups:
            for sensor in group.sensors:
                if any(p in sensor.label for p in patterns):
                    return True
    return False


if __name__ == "__main__":
    import unittest
    from unittest.mock import Mock

    class TestDiscovery(unittest.TestCase):
        def test_needs_discovery(self):
            mock_comp = Mock(sensors=[
                Mock(label="Temperature 1", value=40),
                Mock(label="Ambient", value=30)
            ])
            self.assertTrue(needs_discovery([mock_comp]))
            
            mock_comp = Mock(sensors=[
                Mock(label="CPU Temp", value=40)
            ])
            self.assertFalse(needs_discovery([mock_comp]))

        def test_save_load_mappings(self):
            sd = SensorDiscovery()
            test_path = "/tmp/test_mappings.json"
            mappings = {"s1": ("Test", "🌡️")}
            
            sd.save_mappings(mappings, test_path)
            loaded = sd.load_saved_mappings(test_path)
            self.assertEqual(loaded, mappings)

    unittest.main()
