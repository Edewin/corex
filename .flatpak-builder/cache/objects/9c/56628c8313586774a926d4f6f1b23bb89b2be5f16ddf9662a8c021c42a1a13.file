"""
LM-Sensors reader for CoreX.

Reads hardware sensor data via 'sensors -j' command and
structures it into HardwareComponent objects using models.py.
"""

import json
import subprocess
from typing import List, Dict, Any, Optional
from dataclasses import replace

from ..models import Sensor, SensorGroup, HardwareComponent
from .chip_registry import translate_label, get_chip_metadata


def parse_sensors_output(raw_json: str) -> List[HardwareComponent]:
    """
    Parses JSON string from 'sensors -j' command and structures it into
    HardwareComponent objects.
    
    Args:
        raw_json: JSON string output from 'sensors -j' command
        
    Returns:
        List of HardwareComponent objects, one per chip
        
    Logic:
        1. Parse JSON string
        2. For each chip in JSON:
            a. Extract base chip name (before dash)
            b. Call get_chip_metadata(chip_name) for metadata
            c. Group features by type into SensorGroups:
                - features containing "_input" + type temp → "Temperatures"
                - features containing "_input" + type fan → "Fans"
                - features containing "_input" + type in → "Voltages"
                - features containing "_input" + type power → "Power"
            d. For each feature call translate_label(chip_name, label)
                → returns (human_name, emoji)
                → Sensor.label = f"{emoji} {human_name}"
                → sensor_id = f"{chip_name}_{feature_name}"
            e. Skip sensors with value 0.0 AND type "in" (voltages)
            f. Fan speed 0 RPM → prefix label with "⚠️ "
               e.g. "⚠️ 🌀 Chassis Fan 2"
            g. Create HardwareComponent per chip using metadata
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    
    components = []
    
    for chip_name, chip_data in data.items():
        # Extract base chip name (before dash)
        # Example: "k10temp-pci-00c3" → "k10temp"
        # Example: "nct6795-isa-0290" → "nct6795"
        base_chip_name = chip_name.split('-')[0]
        
        # Get metadata for this chip using base name
        metadata = get_chip_metadata(base_chip_name)
        
        # Initialize sensor groups
        groups = {
            "Temperatures": [],
            "Fans": [],
            "Voltages": [],
            "Power": [],
            "Other": []  # For sensors that don't fit other categories
        }
        
        # Process each adapter/feature in the chip data
        for adapter_name, adapter_data in chip_data.items():
            # Skip the "Adapter" field which is metadata
            if adapter_name == "Adapter":
                continue
            
            # Process each feature in this adapter
            for feature_name, feature_data in adapter_data.items():
                if not isinstance(feature_data, dict):
                    continue
                
                # Check if this is a sensor with an input value
                for sensor_key, sensor_value in feature_data.items():
                    if not sensor_key.endswith("_input"):
                        continue
                    
                    # Determine sensor type based on feature name AND sensor key
                    sensor_type = "Other"
                    if "temp" in feature_name.lower():
                        sensor_type = "Temperatures"
                    elif "fan" in feature_name.lower():
                        sensor_type = "Fans"
                    elif feature_name.startswith("in"):
                        sensor_type = "Voltages"
                    elif "power" in feature_name.lower():
                        sensor_type = "Power"
                    # ThinkPad special: CPU/GPU labels contain temp_input
                    elif "temp" in sensor_key.lower():
                        sensor_type = "Temperatures"
                    
                    # Skip voltage sensors with value 0.0
                    if sensor_type == "Voltages" and sensor_value == 0.0:
                        continue
                    
                    # Get human-readable label and emoji
                    human_name, emoji = translate_label(chip_name, feature_name)
                    
                    # For fan sensors with 0 RPM, add warning prefix
                    label = f"{emoji} {human_name}"
                    if sensor_type == "Fans" and sensor_value == 0.0:
                        label = f"⚠️ {label}"
                    
                    # Determine unit based on sensor type
                    unit = ""
                    if sensor_type == "Temperatures":
                        unit = "°C"
                    elif sensor_type == "Fans":
                        unit = "RPM"
                    elif sensor_type == "Voltages":
                        unit = "V"
                    elif sensor_type == "Power":
                        unit = "W"
                    
                    # Create sensor ID
                    sensor_id = f"{chip_name}_{feature_name}"
                    
                    # Create sensor object
                    sensor = Sensor(
                        label=label,
                        value=float(sensor_value),
                        unit=unit,
                        min_val=float(sensor_value),
                        max_val=float(sensor_value),
                        sensor_id=sensor_id
                    )
                    
                    # Add to appropriate group
                    groups[sensor_type].append(sensor)
        
        # Create SensorGroup objects for non-empty groups
        sensor_groups = []
        
        # Define group metadata
        group_metadata = {
            "Temperatures": ("Temperatures", "🌡️"),
            "Fans": ("Fans", "🌀"),
            "Voltages": ("Voltages", "⚡"),
            "Power": ("Power", "🔋"),
            "Other": ("Other", "❓")
        }
        
        for group_type, sensors in groups.items():
            if sensors:
                group_name, group_icon = group_metadata[group_type]
                sensor_groups.append(SensorGroup(
                    name=group_name,
                    icon=group_icon,
                    sensors=sensors
                ))
        
        # Create HardwareComponent with base chip name
        component = HardwareComponent(
            name=metadata["name_hint"],
            component_type=metadata["group"],
            chip_name=base_chip_name,
            icon=metadata["component_icon"],
            groups=sensor_groups,
            collapsed=False
        )
        
        components.append(component)
    
    return components


def merge_cpu_temperatures(
    cpu_component: HardwareComponent,
    lm_components: List[HardwareComponent]
) -> HardwareComponent:
    """
    Merges CPU temperature sensors from lm-sensors into the CPU component.
    
    Args:
        cpu_component: CPU HardwareComponent from build_cpu_component()
        lm_components: List of HardwareComponent from parse_sensors_output()
        
    Returns:
        Modified cpu_component with temperature group added at index 0
        
    Logic:
        - Finds components where chip_name contains "coretemp", "k10temp", or "thinkpad" in lm_components
        - Extracts their "Temperatures" SensorGroup
        - Adds that group to cpu_component.groups (insert at index 0 — temperatures first)
        - Returns modified cpu_component
        - If no CPU temp chip found → returns cpu_component unchanged
    """
    cpu_temp_chips = ["coretemp", "k10temp", "thinkpad"]
    
    for component in lm_components:
        if any(name in component.chip_name for name in cpu_temp_chips):
            for group in component.groups:
                if group.name == "Temperatures":
                    cpu_component.groups.insert(0, group)
                    print(f"DEBUG: merged {len(group.sensors)} temp sensors into CPU")
                    return cpu_component
    
    # No CPU temperature chip found
    return cpu_component


def get_all_lm_components(
    cpu_component: HardwareComponent = None
) -> List[HardwareComponent]:
    """
    Runs 'sensors -j' command and parses output into HardwareComponent objects.
    
    Args:
        cpu_component: Optional CPU component to merge temperatures into
        
    Returns:
        List of HardwareComponent objects
        
    Logic:
        - Runs: subprocess.run(['sensors', '-j'],
            capture_output=True, text=True, timeout=5)
        - Calls parse_sensors_output() on stdout
        - If cpu_component provided:
            calls merge_cpu_temperatures() and returns
            modified cpu_component + remaining lm components
            (excluding the coretemp/k10temp component itself)
        - Handles errors gracefully:
            FileNotFoundError → print warning, return []
            subprocess timeout → print warning, return []
            JSON parse error → print warning, return []
        - Never crashes regardless of hardware
    """
    try:
        # Run sensors command
        result = subprocess.run(
            ['sensors', '-j'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            print(f"Warning: 'sensors -j' command failed with return code {result.returncode}")
            return []
        
        # Parse the output
        all_components = parse_sensors_output(result.stdout)

        # CPU temp chips are now handled directly by cpu.py — exclude them here
        CPU_TEMP_CHIPS = ['coretemp', 'k10temp', 'zenpower', 'thinkpad']
        non_cpu_components = [
            c for c in all_components
            if not any(chip in c.chip_name for chip in CPU_TEMP_CHIPS)
        ]

        # If CPU component is provided, merge temperatures (legacy path kept
        # for callers that still pass cpu_component, but temperatures are
        # already embedded by build_cpu_component() so we just prepend it)
        if cpu_component is not None:
            return [cpu_component] + non_cpu_components
        else:
            return non_cpu_components
            
    except FileNotFoundError:
        print("Warning: 'sensors' command not found. Is lm-sensors installed?")
        return []
    except subprocess.TimeoutExpired:
        print("Warning: 'sensors -j' command timed out after 5 seconds")
        return []
    except Exception as e:
        print(f"Warning: Error reading sensors data: {e}")
        return []


# Unit tests
if __name__ == "__main__":
    print("Running lm_reader tests...")
    
    # Test 1: parse_sensors_output with sample JSON
    print("\n1. Testing parse_sensors_output() with sample JSON...")
    
    sample_json = """{
      "coretemp-isa-0000": {
        "Adapter": "ISA adapter",
        "Package id 0": {"temp1_input": 45.0, "temp1_max": 100.0},
        "Core 0": {"temp2_input": 42.0, "temp2_max": 100.0},
        "Core 1": {"temp3_input": 43.0, "temp3_max": 100.0}
      },
      "nct6795-isa-0290": {
        "Adapter": "ISA adapter",
        "SYSTIN": {"temp1_input": 33.0},
        "CPUTIN": {"temp2_input": 40.0},
        "fan1": {"fan1_input": 1200.0},
        "fan2": {"fan2_input": 0.0}
      }
    }"""
    
    components = parse_sensors_output(sample_json)
    print(f"   Parsed {len(components)} components")
    
    for i, comp in enumerate(components):
        print(f"   Component {i}: {comp.icon} {comp.name} ({comp.component_type})")
        for group in comp.groups:
            print(f"     {group.icon} {group.name}: {len(group.sensors)} sensors")
            for sensor in group.sensors[:2]:  # Show first 2 sensors
                print(f"       {sensor.label}: {sensor.value}{sensor.unit}")
    
    # Verify coretemp component
    coretemp_comps = [c for c in components if c.chip_name == "coretemp-isa-0000"]
    if coretemp_comps:
        coretemp = coretemp_comps[0]
        print(f"\n   coretemp component found:")
        print(f"     Name: {coretemp.name}")
        print(f"     Type: {coretemp.component_type}")
        print(f"     Groups: {[g.name for g in coretemp.groups]}")
        
        # Check that fan2 has warning prefix
        nct_comps = [c for c in components if "nct6795" in c.chip_name]
        if nct_comps:
            nct = nct_comps[0]
            for group in nct.groups:
                if group.name == "Fans":
                    for sensor in group.sensors:
                        if "0.0" in str(sensor.value):
                            print(f"\n   Fan with 0 RPM: {sensor.label}")
                            if "⚠️" in sensor.label:
                                print("   ✓ Warning prefix correctly added")
                            else:
                                print("   ✗ Warning prefix missing!")
    
    # Test 2: merge_cpu_temperatures
    print("\n2. Testing merge_cpu_temperatures()...")
    
    # Create a mock CPU component
    from .cpu import build_cpu_component
    try:
        cpu = build_cpu_component()
        print(f"   Created CPU component: {cpu.name}")
        print(f"   Original groups: {[g.name for g in cpu.groups]}")
        
        # Merge temperatures
        merged = merge_cpu_temperatures(cpu, components)
        print(f"   After merge groups: {[g.name for g in merged.groups]}")
        
        # Check if Temperatures group was added
        temp_groups = [g for g in merged.groups if g.name == "Temperatures"]
        if temp_groups:
            print(f"   ✓ Temperatures group added with {len(temp_groups[0].sensors)} sensors")
        else:
            print("   ✗ Temperatures group not added")
    except Exception as e:
        print(f"   Error creating CPU component: {e}")
        print("   Using mock CPU component instead")
        
        # Create a mock CPU component for testing
        mock_cpu = HardwareComponent(
            name="Test CPU",
            component_type="CPU",
            chip_name="cpu",
            icon="🔲",
            groups=[
                SensorGroup(name="Utilization", icon="📊", sensors=[]),
                SensorGroup(name="Frequencies", icon="⚡", sensors=[])
            ]
        )
        
        merged = merge_cpu_temperatures(mock_cpu, components)
        print(f"   After merge groups: {[g.name for g in merged.groups]}")
    
    # Test 3: get_all_lm_components error handling
    print("\n3. Testing get_all_lm_components error handling...")
    
    # Test with CPU component
    print("   Testing with CPU component...")
    try:
        all_components = get_all_lm_components(cpu_component=cpu if 'cpu' in locals() else None)
        print(f"   Retrieved {len(all_components)} components")
        
        if all_components:
            print("   First few components:")
            for i, comp in enumerate(all_components[:3]):
                print(f"     {i}: {comp.icon} {comp.name} ({comp.component_type})")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test without CPU component
    print("\n   Testing without CPU component...")
    try:
        all_components = get_all_lm_components()
        print(f"   Retrieved {len(all_components)} components")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\nAll tests completed!")
    
    # Run the verification script from requirements
    print("\n" + "="*60)
    print("Running verification script from requirements:")
    print("="*60)
    
    try:
        from .cpu import build_cpu_component
        cpu = build_cpu_component()
        components = get_all_lm_components(cpu_component=cpu)
        print(f'Components found: {len(components)}')
        for c in components:
            print(f'  {c.icon} {c.name} ({c.component_type})')
            for g in c.groups:
                print(f'    {g.icon} {g.name}: {len(g.sensors)} sensors')
                for s in g.sensors[:2]:
                    print(f'      {s.label}: {s.value}{s.unit}')
        print('OK')
    except Exception as e:
        print(f'Verification failed: {e}')
        import traceback
        traceback.print_exc()