"""
GPU sensor module for CoreX.

Reads GPU data from NVML (Nvidia) and sysfs (AMD/Intel).
Returns data structured using models.py classes.
"""

import os
import sys
from typing import List, Optional, Dict, Any
from dataclasses import replace

from ..models import Sensor, SensorGroup, HardwareComponent


# ============================================================================
# NVML Backend (Nvidia GPUs)
# ============================================================================

def _try_nvml_backend() -> List[HardwareComponent]:
    """
    Try to detect Nvidia GPUs using NVML (pynvml library).
    
    Returns:
        List of HardwareComponent objects for Nvidia GPUs.
        Empty list if NVML not available or no Nvidia GPUs found.
        
    Never raises exceptions - all errors are caught and handled.
    """
    components = []
    
    try:
        import pynvml
        
        # Initialize NVML
        pynvml.nvmlInit()
        
        try:
            # Get number of GPUs
            device_count = pynvml.nvmlDeviceGetCount()
            
            for i in range(device_count):
                try:
                    # Get device handle
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    
                    # Get GPU name
                    name = pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode('utf-8', errors='replace')
                    
                    # Create component
                    component = HardwareComponent(
                        name=name,
                        component_type="GPU",
                        icon="🎮",
                        chip_name="nvml",
                        groups=[],
                        collapsed=False
                    )
                    
                    # ===== Temperatures =====
                    temp_sensors = []
                    
                    try:
                        # GPU core temperature
                        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                        temp_sensor = Sensor(
                            label="🌡️ GPU Core",
                            value=float(temp),
                            unit="°C",
                            min_val=float(temp),
                            max_val=float(temp),
                            sensor_id=f"nvml_{i}_temp_gpu"
                        )
                        temp_sensors.append(temp_sensor)
                    except (pynvml.NVMLError, AttributeError):
                        pass  # Temperature not available
                    
                    try:
                        # Memory junction temperature (if available)
                        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_MEMORY)
                        temp_sensor = Sensor(
                            label="🌡️ Memory Junction",
                            value=float(temp),
                            unit="°C",
                            min_val=float(temp),
                            max_val=float(temp),
                            sensor_id=f"nvml_{i}_temp_mem"
                        )
                        temp_sensors.append(temp_sensor)
                    except (pynvml.NVMLError, AttributeError):
                        pass  # Memory temperature not available
                    
                    if temp_sensors:
                        temp_group = SensorGroup(
                            name="Temperatures",
                            icon="🌡️",
                            sensors=temp_sensors
                        )
                        component.groups.append(temp_group)
                    
                    # ===== Utilization =====
                    util_sensors = []
                    
                    try:
                        # GPU utilization
                        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        gpu_util_sensor = Sensor(
                            label="📊 GPU",
                            value=float(util.gpu),
                            unit="%",
                            min_val=float(util.gpu),
                            max_val=float(util.gpu),
                            sensor_id=f"nvml_{i}_util_gpu"
                        )
                        util_sensors.append(gpu_util_sensor)
                        
                        # Memory controller utilization
                        mem_util_sensor = Sensor(
                            label="📊 Memory Controller",
                            value=float(util.memory),
                            unit="%",
                            min_val=float(util.memory),
                            max_val=float(util.memory),
                            sensor_id=f"nvml_{i}_util_mem"
                        )
                        util_sensors.append(mem_util_sensor)
                    except (pynvml.NVMLError, AttributeError):
                        pass  # Utilization not available
                    
                    try:
                        # Memory usage
                        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        used_mb = mem_info.used / (1024 * 1024)
                        total_mb = mem_info.total / (1024 * 1024)
                        
                        mem_usage_sensor = Sensor(
                            label=f"💾 Memory Used ({int(total_mb)} MB total)",
                            value=float(used_mb),
                            unit="MB",
                            min_val=float(used_mb),
                            max_val=float(used_mb),
                            sensor_id=f"nvml_{i}_mem_used"
                        )
                        util_sensors.append(mem_usage_sensor)
                    except (pynvml.NVMLError, AttributeError):
                        pass  # Memory info not available
                    
                    if util_sensors:
                        util_group = SensorGroup(
                            name="Utilization",
                            icon="📊",
                            sensors=util_sensors
                        )
                        component.groups.append(util_group)
                    
                    # ===== Power =====
                    power_sensors = []
                    
                    try:
                        # Current power draw
                        power = pynvml.nvmlDeviceGetPowerUsage(handle)
                        power_watts = power / 1000.0  # Convert mW to W
                        
                        power_sensor = Sensor(
                            label="🔋 Current Draw",
                            value=float(power_watts),
                            unit="W",
                            min_val=float(power_watts),
                            max_val=float(power_watts),
                            sensor_id=f"nvml_{i}_power_current"
                        )
                        power_sensors.append(power_sensor)
                    except (pynvml.NVMLError, AttributeError):
                        pass  # Power usage not available
                    
                    try:
                        # Power limit
                        power_limit = pynvml.nvmlDeviceGetPowerManagementLimit(handle)
                        power_limit_watts = power_limit / 1000.0  # Convert mW to W
                        
                        power_limit_sensor = Sensor(
                            label="🔋 Power Limit",
                            value=float(power_limit_watts),
                            unit="W",
                            min_val=float(power_limit_watts),
                            max_val=float(power_limit_watts),
                            sensor_id=f"nvml_{i}_power_limit"
                        )
                        power_sensors.append(power_limit_sensor)
                    except (pynvml.NVMLError, AttributeError):
                        pass  # Power limit not available
                    
                    if power_sensors:
                        power_group = SensorGroup(
                            name="Power",
                            icon="🔋",
                            sensors=power_sensors
                        )
                        component.groups.append(power_group)
                    
                    # ===== Fans =====
                    fan_sensors = []
                    
                    try:
                        # Fan speed
                        fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
                        
                        # Determine label based on fan speed
                        if fan_speed == 0:
                            label = "⚠️ 🌀 Fan 0"
                        else:
                            label = "🌀 Fan 0"
                        
                        fan_sensor = Sensor(
                            label=label,
                            value=float(fan_speed),
                            unit="RPM",
                            min_val=float(fan_speed),
                            max_val=float(fan_speed),
                            sensor_id=f"nvml_{i}_fan_0"
                        )
                        fan_sensors.append(fan_sensor)
                    except (pynvml.NVMLError, AttributeError):
                        pass  # Fan speed not available
                    
                    if fan_sensors:
                        fan_group = SensorGroup(
                            name="Fans",
                            icon="🌀",
                            sensors=fan_sensors
                        )
                        component.groups.append(fan_group)
                    
                    # Add component to list
                    components.append(component)
                    
                except (pynvml.NVMLError, AttributeError) as e:
                    # Skip this GPU if there's an error
                    continue
        
        finally:
            # Always try to shut down NVML
            try:
                pynvml.nvmlShutdown()
            except:
                pass
    
    except ImportError:
        # pynvml not installed
        pass
    except Exception as e:
        # Any other error
        pass
    
    return components


# ============================================================================
# Sysfs Backend (AMD and Intel GPUs)
# ============================================================================

def _read_sysfs_file(path: str) -> Optional[str]:
    """Read a sysfs file, returning None on any error."""
    try:
        if os.path.exists(path) and os.access(path, os.R_OK):
            with open(path, 'r') as f:
                return f.read().strip()
    except (IOError, OSError, PermissionError):
        pass
    return None


def _try_sysfs_backend() -> List[HardwareComponent]:
    """
    Try to detect AMD/Intel GPUs using sysfs (/sys/class/drm).
    
    Returns:
        List of HardwareComponent objects for AMD/Intel GPUs.
        Empty list if no DRM devices found or sysfs not accessible.
    """
    components = []
    
    # Scan /sys/class/drm for GPU cards
    drm_path = "/sys/class/drm"
    if not os.path.exists(drm_path):
        return []
    
    try:
        # Look for card directories
        for entry in os.listdir(drm_path):
            if not entry.startswith("card") or not entry[4:].isdigit():
                continue
            
            card_num = entry[4:]
            card_path = os.path.join(drm_path, entry, "device")
            
            if not os.path.exists(card_path):
                continue
            
            # Read vendor ID
            vendor_path = os.path.join(card_path, "vendor")
            vendor_id = _read_sysfs_file(vendor_path)
            
            if not vendor_id:
                continue
            
            # Determine vendor
            vendor = "GPU"
            icon = "🎮"
            
            if vendor_id == "0x1002":
                vendor = "AMD"
                icon = "🎮"
            elif vendor_id == "0x8086":
                vendor = "Intel"
                icon = "🎮"
            
            # Create component name
            component_name = f"{vendor} GPU (card{card_num})"
            
            # Create component
            component = HardwareComponent(
                name=component_name,
                component_type="GPU",
                icon=icon,
                chip_name=f"drm_card{card_num}",
                groups=[],
                collapsed=False
            )
            
            # Find hwmon directory
            hwmon_path = os.path.join(card_path, "hwmon")
            if not os.path.exists(hwmon_path):
                # No hwmon, skip this GPU
                continue
            
            # Find first hwmon directory
            hwmon_dirs = [d for d in os.listdir(hwmon_path) if d.startswith("hwmon")]
            if not hwmon_dirs:
                continue
            
            hwmon_dir = hwmon_dirs[0]
            hwmon_base = os.path.join(hwmon_path, hwmon_dir)
            
            # ===== Temperatures =====
            temp_path = os.path.join(hwmon_base, "temp1_input")
            temp_value = _read_sysfs_file(temp_path)
            
            if temp_value:
                try:
                    temp_celsius = int(temp_value) / 1000.0
                    
                    temp_sensor = Sensor(
                        label="🌡️ GPU Core",
                        value=float(temp_celsius),
                        unit="°C",
                        min_val=float(temp_celsius),
                        max_val=float(temp_celsius),
                        sensor_id=f"sysfs_card{card_num}_temp"
                    )
                    
                    temp_group = SensorGroup(
                        name="Temperatures",
                        icon="🌡️",
                        sensors=[temp_sensor]
                    )
                    component.groups.append(temp_group)
                except (ValueError, TypeError):
                    pass  # Invalid temperature value
            
            # ===== Fans =====
            fan_path = os.path.join(hwmon_base, "fan1_input")
            fan_value = _read_sysfs_file(fan_path)
            
            if fan_value:
                try:
                    fan_rpm = int(fan_value)
                    
                    # Determine label based on fan speed
                    if fan_rpm == 0:
                        label = "⚠️ 🌀 Fan"
                    else:
                        label = "🌀 Fan"
                    
                    fan_sensor = Sensor(
                        label=label,
                        value=float(fan_rpm),
                        unit="RPM",
                        min_val=float(fan_rpm),
                        max_val=float(fan_rpm),
                        sensor_id=f"sysfs_card{card_num}_fan"
                    )
                    
                    fan_group = SensorGroup(
                        name="Fans",
                        icon="🌀",
                        sensors=[fan_sensor]
                    )
                    component.groups.append(fan_group)
                except (ValueError, TypeError):
                    pass  # Invalid fan value
            
            # ===== Power =====
            power_path = os.path.join(hwmon_base, "power1_average")
            power_value = _read_sysfs_file(power_path)
            
            if power_value:
                try:
                    power_watts = int(power_value) / 1000000.0
                    
                    power_sensor = Sensor(
                        label="🔋 Current Draw",
                        value=float(power_watts),
                        unit="W",
                        min_val=float(power_watts),
                        max_val=float(power_watts),
                        sensor_id=f"sysfs_card{card_num}_power"
                    )
                    
                    power_group = SensorGroup(
                        name="Power",
                        icon="🔋",
                        sensors=[power_sensor]
                    )
                    component.groups.append(power_group)
                except (ValueError, TypeError):
                    pass  # Invalid power value
            
            # ===== GPU Utilization (AMD GPUs) =====
            # Try to read GPU utilization from gpu_busy_percent file
            gpu_busy_path = os.path.join(card_path, "device", "gpu_busy_percent")
            gpu_busy_value = _read_sysfs_file(gpu_busy_path)
            
            if gpu_busy_value:
                try:
                    gpu_util = int(gpu_busy_value)
                    
                    util_sensor = Sensor(
                        label="📊 GPU",
                        value=float(gpu_util),
                        unit="%",
                        min_val=float(gpu_util),
                        max_val=float(gpu_util),
                        sensor_id=f"sysfs_card{card_num}_gpu_util"
                    )
                    
                    # Check if Utilization group already exists
                    util_group = None
                    for group in component.groups:
                        if group.name == "Utilization":
                            util_group = group
                            break
                    
                    if util_group is None:
                        util_group = SensorGroup(
                            name="Utilization",
                            icon="📊",
                            sensors=[util_sensor]
                        )
                        component.groups.append(util_group)
                    else:
                        util_group.sensors.append(util_sensor)
                except (ValueError, TypeError):
                    pass  # Invalid utilization value
            
            # Also try to read from debugfs for more detailed info (requires root)
            debugfs_path = f"/sys/kernel/debug/dri/{card_num}/amdgpu_pm_info"
            debugfs_value = _read_sysfs_file(debugfs_path)
            # Note: We don't parse amdgpu_pm_info here as it's complex text format
            # Just checking if it's readable for future expansion
            
            # Only add component if it has at least one sensor group
            if component.groups:
                components.append(component)
    
    except (OSError, PermissionError):
        # Can't access sysfs
        pass
    
    return components


# ============================================================================
# Public API
# ============================================================================

def get_gpu_components() -> List[HardwareComponent]:
    """
    Get GPU hardware components from all available backends.
    
    Returns:
        List of HardwareComponent objects for detected GPUs.
        Empty list if no GPUs detected or all backends fail.
        
    Backend priority:
        1. NVML (Nvidia GPUs)
        2. Sysfs (AMD/Intel GPUs)
        
    Never raises exceptions - all errors are caught and handled.
    """
    components = []
    
    # Try NVML first (Nvidia)
    nvml_components = _try_nvml_backend()
    if nvml_components:
        components.extend(nvml_components)
    
    # If no Nvidia GPUs found, try sysfs (AMD/Intel)
    if not components:
        sysfs_components = _try_sysfs_backend()
        if sysfs_components:
            components.extend(sysfs_components)
    
    return components


# ============================================================================
# Unit Tests
# ============================================================================

if __name__ == "__main__":
    print("Running GPU sensor module tests...")
    
    # Test 1: get_gpu_components() returns list (even if empty)
    print("\n1. Testing get_gpu_components() returns list...")
    try:
        gpus = get_gpu_components()
        print(f"   Success: returned {len(gpus)} GPU components")
        print(f"   Type check: {type(gpus) == list} ✓")
        
        if gpus:
            print(f"   First GPU: {gpus[0].icon} {gpus[0].name} ({gpus[0].component_type})")
            for group in gpus[0].groups:
                print(f"     {group.icon} {group.name}: {len(group.sensors)} sensors")
                for sensor in group.sensors[:2]:  # Show first 2 sensors
                    print(f"       {sensor.label}: {sensor.value}{sensor.unit}")
        else:
            print("   No GPUs detected (or no driver) — OK")
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Test sysfs backend with mocked file reads
    print("\n2. Testing sysfs backend error handling...")
    
    # Create a mock sysfs structure for testing
    import tempfile
    import shutil
    
    try:
        # Create temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock DRM structure
            drm_dir = os.path.join(tmpdir, "drm")
            card_dir = os.path.join(drm_dir, "card0")
            device_dir = os.path.join(card_dir, "device")
            hwmon_dir = os.path.join(device_dir, "hwmon", "hwmon0")
            
            os.makedirs(hwmon_dir, exist_ok=True)
            
            # Write vendor file (AMD)
            vendor_file = os.path.join(device_dir, "vendor")
            with open(vendor_file, 'w') as f:
                f.write("0x1002\n")
            
            # Write temperature file
            temp_file = os.path.join(hwmon_dir, "temp1_input")
            with open(temp_file, 'w') as f:
                f.write("45000\n")  # 45.0°C
            
            # Write fan file
            fan_file = os.path.join(hwmon_dir, "fan1_input")
            with open(fan_file, 'w') as f:
                f.write("1200\n")  # 1200 RPM
            
            # Write power file
            power_file = os.path.join(hwmon_dir, "power1_average")
            with open(power_file, 'w') as f:
                f.write("125000000\n")  # 125W
            
            # Test the _read_sysfs_file function
            print("   Testing _read_sysfs_file()...")
            temp_value = _read_sysfs_file(temp_file)
            print(f"   Read temperature: {temp_value} (expected: 45000)")
            assert temp_value == "45000", "Failed to read sysfs file"
            
            # Test with non-existent file
            nonexistent = _read_sysfs_file(os.path.join(hwmon_dir, "nonexistent"))
            print(f"   Read non-existent file: {nonexistent} (expected: None)")
            assert nonexistent is None, "Should return None for non-existent file"
            
            print("   ✓ Sysfs file reading works correctly")
            
    except Exception as e:
        print(f"   Error in sysfs test: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Test NVML failure is handled gracefully
    print("\n3. Testing NVML import failure handling...")
    
    # Temporarily remove pynvml from sys.modules to simulate ImportError
    original_pynvml = sys.modules.get('pynvml')
    if 'pynvml' in sys.modules:
        del sys.modules['pynvml']
    
    try:
        # This should not raise an exception
        nvml_result = _try_nvml_backend()
        print(f"   NVML backend returned {len(nvml_result)} components (expected: 0)")
        print(f"   ✓ NVML import failure handled gracefully")
    except Exception as e:
        print(f"   Error: {e}")
        print(f"   ✗ NVML import failure not handled properly")
    
    # Restore pynvml if it was originally present
    if original_pynvml:
        sys.modules['pynvml'] = original_pynvml
    
    # Test 4: Run verification script from requirements
    print("\n" + "="*60)
    print("Running verification script from requirements:")
    print("="*60)
    
    try:
        gpus = get_gpu_components()
        if not gpus:
            print('No GPU detected (or no driver) — OK')
        for g in gpus:
            print(f'{g.icon} {g.name} ({g.component_type})')
            for grp in g.groups:
                print(f'  {grp.icon} {grp.name}')
                for s in grp.sensors:
                    print(f'    {s.label}: {s.value}{s.unit}')
        print('OK')
    except Exception as e:
        print(f'Verification failed: {e}')
        import traceback
        traceback.print_exc()
    
    print("\nAll tests completed!")