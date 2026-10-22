"""Start CoreX with the desktop session (XDG autostart, or the Background portal inside Flatpak)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_ID = "io.github.edewin.corex"


def in_flatpak() -> bool:
    return os.path.exists("/.flatpak-info")


def _autostart_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "autostart" / f"{APP_ID}.desktop"


def _command() -> str:
    exe = shutil.which("corex")
    return f"{exe} --hidden" if exe else f"{sys.executable} -m corex --hidden"


def set_enabled(on: bool) -> str | None:
    """Turn autostart on or off; returns an error message for the user, or None."""
    if in_flatpak():
        return _portal(on)
    path = _autostart_file()
    try:
        if on:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("[Desktop Entry]\nType=Application\nName=CoreX\n"
                            "Comment=Hardware monitor\n"
                            f"Exec={_command()}\nIcon={APP_ID}\n"
                            "X-GNOME-Autostart-enabled=true\nTerminal=false\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except OSError as e:
        return f"Could not change {path}: {e.strerror}"
    return None


def _portal(on: bool) -> str | None:
    """org.freedesktop.portal.Background.RequestBackground; the portal writes the autostart entry."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusMessage
    except ImportError:
        return "Starting with the system needs Qt D-Bus support."
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return "Could not reach the desktop session bus."
    msg = QDBusMessage.createMethodCall("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                                        "org.freedesktop.portal.Background", "RequestBackground")
    options = {"reason": "Show the CoreX widget when you log in",
               "autostart": on, "commandline": ["corex", "--hidden"], "dbus-activatable": False}
    msg.setArguments(["", options])
    reply = bus.call(msg)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return f"The desktop refused: {reply.errorMessage()}"
    return None
