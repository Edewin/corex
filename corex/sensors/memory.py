"""
Memory sensor module for CoreX.

Reads memory data from /proc/meminfo.
Returns data structured using models.py classes.
"""

import re
from typing import Dict, Optional

from ..models import Sensor, SensorGroup, HardwareComponent


def _read_meminfo() -> Dict[str, int]:
    """
    Read /proc/meminfo and parse key-value pairs.
    
    Returns:
        Dictionary mapping meminfo keys to integer values (in kB).
        Empty dict on error.
    """
    meminfo = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Parse lines like "MemTotal:       16384000 kB"
                match = re.match(r'^([^:]+):\s+(\d+)\s*(kB)?$', line)
                if match:
                    key = match.group(1).strip()
                    value = int(match.group(2))
                    meminfo[key] = value
    except (IOError, OSError, ValueError):
        # Return empty dict on any error
        pass
    
    return meminfo


def _create_ram_group(meminfo: Dict[str, int]) -> Optional[SensorGroup]:
    """
    Create RAM sensor group from meminfo data.
    
    Returns:
        SensorGroup for RAM metrics, or None if insufficient data.
    """
    # Check required keys
    required_keys = ["MemTotal", "MemAvailable"]
    if not all(key in meminfo for key in required_keys):
        return None
    
    sensors = []
    
    # 1. Total RAM
    mem_total_kb = meminfo.get("MemTotal", 0)
    mem_total_mb = mem_total_kb / 1024.0
    total_sensor = Sensor(
        label="🧮 Total",
        value=round(mem_total_mb, 1),
        unit="MB",
        min_val=round(mem_total_mb, 1),
        max_val=round(mem_total_mb, 1),
        sensor_id="mem_total"
    )
    sensors.append(total_sensor)
    
    # 2. Available RAM
    mem_available_kb = meminfo.get("MemAvailable", 0)
    mem_available_mb = mem_available_kb / 1024.0
    available_sensor = Sensor(
        label="✅ Available",
        value=round(mem_available_mb, 1),
        unit="MB",
        min_val=round(mem_available_mb, 1),
        max_val=round(mem_available_mb, 1),
        sensor_id="mem_available"
    )
    sensors.append(available_sensor)
    
    # 3. Used RAM
    mem_used_kb = mem_total_kb - mem_available_kb
    mem_used_mb = mem_used_kb / 1024.0
    used_sensor = Sensor(
        label="📊 Used",
        value=round(mem_used_mb, 1),
        unit="MB",
        min_val=round(mem_used_mb, 1),
        max_val=round(mem_used_mb, 1),
        sensor_id="mem_used"
    )
    sensors.append(used_sensor)
    
    # 4. Usage percentage
    if mem_total_kb > 0:
        usage_percent = (mem_used_kb / mem_total_kb) * 100.0
    else:
        usage_percent = 0.0
    usage_sensor = Sensor(
        label="📈 Usage",
        value=round(usage_percent, 1),
        unit="%",
        min_val=round(usage_percent, 1),
        max_val=round(usage_percent, 1),
        sensor_id="mem_usage"
    )
    sensors.append(usage_sensor)
    
    return SensorGroup(name="RAM", icon="🧮", sensors=sensors)


def _create_swap_group(meminfo: Dict[str, int]) -> Optional[SensorGroup]:
    """
    Create Swap sensor group from meminfo data.
    
    Returns:
        SensorGroup for Swap metrics, or None if SwapTotal is 0 or missing.
    """
    # Check if swap exists
    swap_total_kb = meminfo.get("SwapTotal", 0)
    if swap_total_kb <= 0:
        return None
    
    sensors = []
    
    # 1. Total Swap
    swap_total_mb = swap_total_kb / 1024.0
    total_sensor = Sensor(
        label="♻️ Total",
        value=round(swap_total_mb, 1),
        unit="MB",
        min_val=round(swap_total_mb, 1),
        max_val=round(swap_total_mb, 1),
        sensor_id="swap_total"
    )
    sensors.append(total_sensor)
    
    # 2. Free Swap
    swap_free_kb = meminfo.get("SwapFree", 0)
    
    # 3. Used Swap
    swap_used_kb = swap_total_kb - swap_free_kb
    swap_used_mb = swap_used_kb / 1024.0
    used_sensor = Sensor(
        label="📊 Used",
        value=round(swap_used_mb, 1),
        unit="MB",
        min_val=round(swap_used_mb, 1),
        max_val=round(swap_used_mb, 1),
        sensor_id="swap_used"
    )
    sensors.append(used_sensor)
    
    # 4. Usage percentage
    if swap_total_kb > 0:
        swap_usage_percent = (swap_used_kb / swap_total_kb) * 100.0
    else:
        swap_usage_percent = 0.0
    usage_sensor = Sensor(
        label="📈 Usage",
        value=round(swap_usage_percent, 1),
        unit="%",
        min_val=round(swap_usage_percent, 1),
        max_val=round(swap_usage_percent, 1),
        sensor_id="swap_usage"
    )
    sensors.append(usage_sensor)
    
    return SensorGroup(name="Swap", icon="♻️", sensors=sensors)


def build_memory_component() -> HardwareComponent:
    """
    Builds a complete Memory hardware component.
    
    Returns:
        HardwareComponent representing the Memory (RAM) with sensor groups.
        
    Groups:
        - RAM: Total, Used, Available, Usage %
        - Swap: Only if SwapTotal > 0
    """
    # Read meminfo
    meminfo = _read_meminfo()
    
    # Create groups
    groups = []
    
    # RAM group
    ram_group = _create_ram_group(meminfo)
    if ram_group:
        groups.append(ram_group)
    
    # Swap group (only if swap exists)
    swap_group = _create_swap_group(meminfo)
    if swap_group:
        groups.append(swap_group)
    
    return HardwareComponent(
        name="Memory (RAM)",
        component_type="System",
        icon="🧮",
        chip_name="memory",
        groups=groups,
        collapsed=False
    )


# Unit tests
if __name__ == "__main__":
    print("Running Memory sensor module tests...")
    
    # Test 1: _read_meminfo() returns dict
    print("\n1. Testing _read_meminfo()...")
    try:
        meminfo = _read_meminfo()
        print(f"   Successfully read meminfo with {len(meminfo)} entries")
        if meminfo:
            print(f"   Sample keys: {list(meminfo.keys())[:5]}")
            if "MemTotal" in meminfo:
                print(f"   MemTotal: {meminfo['MemTotal']} kB")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: _create_ram_group() with mock data
    print("\n2. Testing _create_ram_group() with mock data...")
    mock_meminfo = {
        "MemTotal": 16384000,  # 16GB in kB
        "MemAvailable": 8192000,  # 8GB available
        "SwapTotal": 8388608,  # 8GB swap
        "SwapFree": 4194304,   # 4GB free
    }
    
    ram_group = _create_ram_group(mock_meminfo)
    if ram_group:
        print(f"   Created RAM group: {ram_group.name} ({ram_group.icon})")
        print(f"   Number of sensors: {len(ram_group.sensors)}")
        for sensor in ram_group.sensors:
            print(f"     {sensor.label}: {sensor.value}{sensor.unit} (id: {sensor.sensor_id})")
        
        # Verify calculations
        expected_total = 16384000 / 1024  # 16000 MB
        expected_available = 8192000 / 1024  # 8000 MB
        expected_used = (16384000 - 8192000) / 1024  # 8000 MB
        expected_usage = ((16384000 - 8192000) / 16384000) * 100  # 50%
        
        # Find sensors by label
        for sensor in ram_group.sensors:
            if "Total" in sensor.label:
                assert abs(sensor.value - expected_total) < 0.1, f"Total mismatch: {sensor.value} vs {expected_total}"
            elif "Available" in sensor.label:
                assert abs(sensor.value - expected_available) < 0.1, f"Available mismatch: {sensor.value} vs {expected_available}"
            elif "Used" in sensor.label and "Usage" not in sensor.label:
                assert abs(sensor.value - expected_used) < 0.1, f"Used mismatch: {sensor.value} vs {expected_used}"
            elif "Usage" in sensor.label:
                assert abs(sensor.value - expected_usage) < 0.1, f"Usage mismatch: {sensor.value} vs {expected_usage}"
        
        print("   ✓ All calculations correct")
    else:
        print("   ✗ Failed to create RAM group")
    
    # Test 3: _create_swap_group() with mock data
    print("\n3. Testing _create_swap_group() with mock data...")
    swap_group = _create_swap_group(mock_meminfo)
    if swap_group:
        print(f"   Created Swap group: {swap_group.name} ({swap_group.icon})")
        print(f"   Number of sensors: {len(swap_group.sensors)}")
        for sensor in swap_group.sensors:
            print(f"     {sensor.label}: {sensor.value}{sensor.unit} (id: {sensor.sensor_id})")
        
        # Verify calculations
        expected_swap_total = 8388608 / 1024  # 8192 MB
        expected_swap_used = (8388608 - 4194304) / 1024  # 4096 MB
        expected_swap_usage = ((8388608 - 4194304) / 8388608) * 100  # 50%
        
        for sensor in swap_group.sensors:
            if "Total" in sensor.label:
                assert abs(sensor.value - expected_swap_total) < 0.1, f"Swap total mismatch: {sensor.value} vs {expected_swap_total}"
            elif "Used" in sensor.label and "Usage" not in sensor.label:
                assert abs(sensor.value - expected_swap_used) < 0.1, f"Swap used mismatch: {sensor.value} vs {expected_swap_used}"
            elif "Usage" in sensor.label:
                assert abs(sensor.value - expected_swap_usage) < 0.1, f"Swap usage mismatch: {sensor.value} vs {expected_swap_usage}"
        
        print("   ✓ All swap calculations correct")
    else:
        print("   ✗ Failed to create Swap group")
    
    # Test 4: _create_swap_group() with no swap
    print("\n4. Testing _create_swap_group() with no swap...")
    no_swap_meminfo = {"MemTotal": 16384000, "MemAvailable": 8192000}
    no_swap_group = _create_swap_group(no_swap_meminfo)
    if no_swap_group is None:
        print("   ✓ Correctly returned None when SwapTotal is 0/missing")
    else:
        print("   ✗ Should return None when no swap")
    
    # Test 5: build_memory_component() integration
    print("\n5. Testing build_memory_component()...")
    try:
        memory_component = build_memory_component()
        print(f"   Memory component created: {memory_component.name}")
        print(f"   Component type: {memory_component.component_type}")
        print(f"   Icon: {memory_component.icon}")
        print(f"   Chip name: {memory_component.chip_name}")
        print(f"   Number of groups: {len(memory_component.groups)}")
        
        for i, group in enumerate(memory_component.groups):
            print(f"   Group {i}: {group.name} ({group.icon}) with {len(group.sensors)} sensors")
            for sensor in group.sensors[:2]:  # Show first 2 sensors
                print(f"     {sensor.label}: {sensor.value}{sensor.unit}")
        
        # Verify structure
        assert memory_component.name == "Memory (RAM)", "Wrong component name"
        assert memory_component.component_type == "System", "Wrong component type"
        assert memory_component.icon == "🧮", "Wrong icon"
        assert memory_component.chip_name == "memory", "Wrong chip name"
        
        print("   ✓ Component structure correct")
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 6: Test swap group absence when SwapTotal = 0
    print("\n6. Testing swap group absence when SwapTotal = 0...")
    
    # We can't easily mock /proc/meminfo, but we can test the logic
    # by checking that _create_swap_group returns None when SwapTotal is 0
    zero_swap_meminfo = {"SwapTotal": 0, "SwapFree": 0}
    zero_swap_group = _create_swap_group(zero_swap_meminfo)
    if zero_swap_group is None:
        print("   ✓ Correctly returns None when SwapTotal = 0")
    else:
        print("   ✗ Should return None when SwapTotal = 0")
    
    print("\nAll tests completed!")
    
    # Run the verification script from requirements
    print("\n" + "="*60)
    print("Running verification script from requirements:")
    print("="*60)
    
    try:
        mem = build_memory_component()
        print(f'{mem.icon} {mem.name}')
        for g in mem.groups:
            print(f'  {g.icon} {g.name}')
            for s in g.sensors:
                print(f'    {s.label}: {s.value}{s.unit}')
        print('OK')
    except Exception as e:
        print(f'Verification failed: {e}')
        import traceback
        traceback.print_exc()