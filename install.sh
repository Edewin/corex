#!/bin/bash
set -e
echo "Installing CoreX dependencies..."

# Detect distro
if command -v apt &> /dev/null; then
    sudo apt install -y lm-sensors libxcb-cursor0 python3-pip
elif command -v dnf &> /dev/null; then
    sudo dnf install -y lm_sensors python3-pip
elif command -v pacman &> /dev/null; then
    sudo pacman -S --noconfirm lm_sensors python-pip
fi

# Install Python deps
pip3 install PyQt6 pyqtgraph pynvml \
    --break-system-packages 2>/dev/null || \
pip3 install PyQt6 pyqtgraph pynvml

# sensors-detect if not already done
if ! sensors &>/dev/null; then
    echo "Running sensors-detect..."
    sudo sensors-detect --auto
fi

echo ""
echo "CoreX installed successfully!"
echo "Run with: bash run.sh"