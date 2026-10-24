"""User settings in ~/.config/corex/settings.json (XDG_CONFIG_HOME respected)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

INTERVALS_S = (0.5, 1.0, 2.0, 5.0)
VIEW_MODES = ("list", "dashboard")


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "corex"


@dataclass
class Settings:
    interval_s: float = 1.0
    labels: dict[str, str] = field(default_factory=dict)          # reading id -> user label
    widget_readings: list[str] | None = None                      # None = pick on first run
    widget_pos: list[int] | None = None
    widget_visible: bool = True
    widget_opacity: float = 0.92
    last_page: str = "overview"
    view_mode: str | None = None                                  # "list" / "dashboard"; None = ask on first run
    hidden: list[str] = field(default_factory=list)               # reading ids hidden from the tables
    show_hidden: bool = False
    collapsed: list[str] = field(default_factory=list)            # folded device / group rows
    charts: list[str] = field(default_factory=list)               # reading ids charted in the List view
    columns: dict[str, list[int]] = field(default_factory=dict)   # table -> widths of Value, Min, Max
    autostart: bool = False
    theme: str = "dark"                                           # "dark" / "light" / "system"
    history_days: int = 30
    alerts: dict[str, dict] = field(default_factory=dict)         # reading id -> {"above": x, "below": y}

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or config_dir() / "settings.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        s = cls(**known)
        if s.interval_s not in INTERVALS_S:
            s.interval_s = 1.0
        if s.view_mode not in VIEW_MODES:
            s.view_mode = None
        if s.theme not in ("dark", "light", "system"):
            s.theme = "dark"
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or config_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)                                         # never a half-written file
