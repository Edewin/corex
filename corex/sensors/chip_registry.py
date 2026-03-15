"""
Chip registry for CoreX sensor system.

Maps raw lm-sensors chip names and feature labels to
human-readable names and emoji icons.
"""

import fnmatch
from typing import Dict, Tuple, Any

# Maps chip name patterns to metadata
CHIP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "coretemp": {
        "group": "CPU",
        "name_hint": "Intel CPU",
        "component_icon": "🔲",
        "group_icon": "🌡️"
    },
    "k10temp": {
        "group": "CPU",
        "name_hint": "AMD CPU",
        "component_icon": "🔲",
        "group_icon": "🌡️"
    },
    "amdgpu": {
        "group": "GPU",
        "name_hint": "AMD GPU",
        "component_icon": "🎮",
        "group_icon": "🌡️"
    },
    "nouveau": {
        "group": "GPU",
        "name_hint": "Nvidia GPU",
        "component_icon": "🎮",
        "group_icon": "🌡️"
    },
    "nvme": {
        "group": "Storage",
        "name_hint": "NVMe SSD",
        "component_icon": "💾",
        "group_icon": "🌡️"
    },
    "acpitz": {
        "group": "System",
        "name_hint": "System",
        "component_icon": "🖥️",
        "group_icon": "🌡️"
    },
    "it8*": {
        "group": "Motherboard",
        "name_hint": "Motherboard",
        "component_icon": "⚙️",
        "group_icon": "🌡️"
    },
    "nct6*": {
        "group": "Motherboard",
        "name_hint": "Motherboard",
        "component_icon": "⚙️",
        "group_icon": "🌡️"
    },
    "iwlwifi*": {
        "group": "Network",
        "name_hint": "WiFi",
        "component_icon": "📶",
        "group_icon": "🌡️"
    },
    "BAT*": {
        "group": "System",
        "name_hint": "Battery",
        "component_icon": "🔋",
        "group_icon": "⚡"
    }
}

# Maps raw kernel labels to (human_name, emoji) tuples
LABEL_TRANSLATIONS: Dict[str, Tuple[str, str]] = {
    # Temperatures
    "SYSTIN": ("System Temperature", "🌡️"),
    "CPUTIN": ("CPU Temperature (Socket)", "🌡️"),
    "AUXTIN0": ("Auxiliary Temperature", "🌡️"),
    "AUXTIN1": ("PCH Temperature", "🌡️"),
    "temp1": ("Temperature 1", "🌡️"),
    "temp2": ("Temperature 2", "🌡️"),
    "temp3": ("Temperature 3", "🌡️"),
    
    # Fans
    "fan1": ("CPU Fan", "🌀"),
    "fan2": ("Chassis Fan 1", "🌀"),
    "fan3": ("Chassis Fan 2", "🌀"),
    "fan4": ("Chassis Fan 3", "🌀"),
    "fan5": ("Chassis Fan 4", "🌀"),
    
    # Voltages
    "in0": ("CPU Vcore", "⚡"),
    "in1": ("DRAM Voltage", "⚡"),
    "in3": ("3.3V Rail", "⚡"),
    "in5": ("5V Rail", "⚡"),
    "in7": ("12V Rail", "⚡")
}


def translate_label(chip_name: str, raw_label: str) -> Tuple[str, str]:
    """
    Translate raw kernel sensor label to human-readable name and emoji.
    
    Args:
        chip_name: The chip name (for context, not currently used)
        raw_label: The raw kernel label (e.g., "temp1", "fan2", "in0")
        
    Returns:
        Tuple of (human_label, emoji)
        
    Logic:
        1. Check LABEL_TRANSLATIONS for exact match first
        2. If no match and label starts with "temp" → 
           return ("Temperature (unidentified)", "🌡️")
        3. If no match and label starts with "fan" →
           return ("Fan (unidentified)", "🌀")
        4. If no match and label starts with "in" →
           return ("Voltage (unidentified)", "⚡")
        5. Truly unknown → ("Unknown Sensor", "❓")
    """
    # Step 1: Check for exact match
    if raw_label in LABEL_TRANSLATIONS:
        return LABEL_TRANSLATIONS[raw_label]
    
    # Step 2: Check for temperature patterns
    if raw_label.startswith("temp"):
        return ("Temperature (unidentified)", "🌡️")
    
    # Step 3: Check for fan patterns
    if raw_label.startswith("fan"):
        return ("Fan (unidentified)", "🌀")
    
    # Step 4: Check for voltage patterns
    if raw_label.startswith("in"):
        return ("Voltage (unidentified)", "⚡")
    
    # Step 5: Truly unknown
    return ("Unknown Sensor", "❓")


def get_chip_metadata(chip_name: str) -> Dict[str, Any]:
    """
    Get metadata for a chip name, supporting glob matching.
    
    Args:
        chip_name: The raw chip name from lm-sensors
        
    Returns:
        Dictionary with metadata fields:
        - group: Component group (e.g., "CPU", "GPU", "System")
        - name_hint: Human-readable name hint
        - component_icon: Emoji for the component
        - group_icon: Emoji for the sensor group
        
    Supports glob matching for patterns like "nct6*", "it8*".
    Returns default metadata if no match found:
        { group:"System", name_hint:chip_name,
          component_icon:"🖥️", group_icon:"🌡️" }
    """
    # Check for exact matches first
    if chip_name in CHIP_REGISTRY:
        return CHIP_REGISTRY[chip_name].copy()
    
    # Check for glob pattern matches
    for pattern, metadata in CHIP_REGISTRY.items():
        if "*" in pattern:
            if fnmatch.fnmatch(chip_name, pattern):
                return metadata.copy()
    
    # Default metadata for unknown chips
    return {
        "group": "System",
        "name_hint": chip_name,
        "component_icon": "🖥️",
        "group_icon": "🌡️"
    }


# Unit tests
if __name__ == "__main__":
    print("Running chip_registry tests...")
    
    # Test translate_label function
    # Exact matches
    assert translate_label("coretemp", "SYSTIN") == ("System Temperature", "🌡️")
    assert translate_label("coretemp", "fan1") == ("CPU Fan", "🌀")
    assert translate_label("coretemp", "in0") == ("CPU Vcore", "⚡")
    
    # Pattern matches
    assert translate_label("coretemp", "temp4") == ("Temperature (unidentified)", "🌡️")
    assert translate_label("coretemp", "fan6") == ("Fan (unidentified)", "🌀")
    assert translate_label("coretemp", "in8") == ("Voltage (unidentified)", "⚡")
    
    # Unknown
    assert translate_label("coretemp", "unknown_sensor") == ("Unknown Sensor", "❓")
    
    # Test get_chip_metadata function
    # Exact matches
    coretemp_meta = get_chip_metadata("coretemp")
    assert coretemp_meta["group"] == "CPU"
    assert coretemp_meta["name_hint"] == "Intel CPU"
    assert coretemp_meta["component_icon"] == "🔲"
    
    amdgpu_meta = get_chip_metadata("amdgpu")
    assert amdgpu_meta["group"] == "GPU"
    assert amdgpu_meta["name_hint"] == "AMD GPU"
    assert amdgpu_meta["component_icon"] == "🎮"
    
    # Glob pattern matches
    it8_meta = get_chip_metadata("it8772")
    assert it8_meta["group"] == "Motherboard"
    assert it8_meta["name_hint"] == "Motherboard"
    assert it8_meta["component_icon"] == "⚙️"
    
    nct6_meta = get_chip_metadata("nct6779")
    assert nct6_meta["group"] == "Motherboard"
    assert nct6_meta["name_hint"] == "Motherboard"
    assert nct6_meta["component_icon"] == "⚙️"
    
    bat_meta = get_chip_metadata("BAT0")
    assert bat_meta["group"] == "System"
    assert bat_meta["name_hint"] == "Battery"
    assert bat_meta["component_icon"] == "🔋"
    
    # Default metadata for unknown chips
    unknown_meta = get_chip_metadata("unknown_chip")
    assert unknown_meta["group"] == "System"
    assert unknown_meta["name_hint"] == "unknown_chip"
    assert unknown_meta["component_icon"] == "🖥️"
    assert unknown_meta["group_icon"] == "🌡️"
    
    print("All tests passed!")
    print("\nExample usage:")
    print(f"translate_label('coretemp', 'temp1'): {translate_label('coretemp', 'temp1')}")
    print(f"translate_label('k10temp', 'fan2'): {translate_label('k10temp', 'fan2')}")
    print(f"get_chip_metadata('nvme'): {get_chip_metadata('nvme')}")
    print(f"get_chip_metadata('BAT0'): {get_chip_metadata('BAT0')}")