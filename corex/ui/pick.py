"""Which readings represent a device best (tiles, sidebar summary, default widget)."""

from __future__ import annotations

from corex.core.model import Device, DeviceKind, Kind, Reading, Snapshot
from corex.core.units import format_reading


def _first(device: Device, kind: str, group: str | None = None) -> Reading | None:
    for g in device.groups:
        if group and g.name != group:
            continue
        for r in g.readings:
            if r.kind == kind and r.value is not None:
                return r
    return None


def _by_suffix(device: Device, *suffixes: str) -> list[Reading]:
    out = []
    for suffix in suffixes:
        for g in device.groups:
            for r in g.readings:
                if r.id.endswith(suffix) and r not in out:
                    out.append(r)
    return out


def tiles(device: Device) -> list[list[str]]:
    """
    Tiles for a device page; each tile is a list of reading ids drawn
    together (download+upload share one chart).
    """
    k = device.kind
    out: list[list[str]] = []
    if k == DeviceKind.CPU:
        out += [[r.id] for r in _by_suffix(device, "/load/total")]
        t = _first(device, Kind.TEMP)
        if t:
            out.append([t.id])
        out += [[r.id] for r in _by_suffix(device, "/clock/avg")]
        p = _first(device, Kind.POWER)
        if p:
            out.append([p.id])
    elif k == DeviceKind.GPU:
        out += [[r.id] for r in _by_suffix(device, "/load")]
        t = _first(device, Kind.TEMP)
        if t:
            out.append([t.id])
        out += [[r.id] for r in _by_suffix(device, "/power", "/vram_load")]
    elif k == DeviceKind.MEMORY:
        out += [[r.id] for r in _by_suffix(device, "/ram/load", "/swap/load")]
        t = _first(device, Kind.TEMP)
        if t:
            out.append([t.id])
    elif k == DeviceKind.STORAGE:
        rw = [r.id for r in _by_suffix(device, "/read", "/write")]
        if rw:
            out.append(rw)
        out += [[r.id] for r in _by_suffix(device, "/busy")]
        t = _first(device, Kind.TEMP)
        if t:
            out.append([t.id])
    elif k == DeviceKind.NETWORK:
        ud = [r.id for r in _by_suffix(device, "/down", "/up")]
        if ud:
            out.append(ud)
        s = _by_suffix(device, "/signal")
        if s:
            out.append([s[0].id])
    else:
        temps = [r for g in device.groups for r in g.readings if r.kind == Kind.TEMP][:3]
        fans = [r for g in device.groups for r in g.readings if r.kind == Kind.FAN and r.value][:2]
        out += [[r.id] for r in temps + fans]
    return out[:4]


def summary(device: Device) -> str:
    """One short line for the sidebar."""
    k, parts = device.kind, []
    if k in (DeviceKind.CPU, DeviceKind.GPU):
        for r in _by_suffix(device, "/load/total" if k == DeviceKind.CPU else "/load")[:1]:
            parts.append(format_reading(r))
        t = _first(device, Kind.TEMP)
        if t:
            parts.append(format_reading(t))
    elif k == DeviceKind.MEMORY:
        parts += [format_reading(r) for r in _by_suffix(device, "/ram/load", "/ram/used")]
    elif k == DeviceKind.STORAGE:
        for r in _by_suffix(device, "/read", "/write"):
            parts.append(("R " if r.id.endswith("/read") else "W ") + format_reading(r))
    elif k == DeviceKind.NETWORK:
        for r in _by_suffix(device, "/down", "/up"):
            parts.append(("↓ " if r.id.endswith("/down") else "↑ ") + format_reading(r))
    else:
        t = _first(device, Kind.TEMP)
        if t:
            parts.append(format_reading(t))
        fans = [r for g in device.groups for r in g.readings if r.kind == Kind.FAN and r.value]
        if fans:
            parts.append(f"{len(fans)} fan{'s' if len(fans) > 1 else ''}")
    return "  ·  ".join(parts)


def overview_tiles(snap: Snapshot, custom: list[list[str]] | None = None) -> list[tuple[str, list[str]]]:
    """
    (device id, reading ids) for the Overview page: the user's own list, or
    the first tile of every device; charts of devices that are gone are skipped.
    """
    if custom is not None:
        out = []
        for ids in custom:
            dev = next((d for d in snap.devices if ids and d.reading(ids[0])), None)
            if dev:
                out.append((dev.id, [i for i in ids if dev.reading(i)]))
        return out
    out = []
    for d in snap.devices:
        t = tiles(d)
        if d.kind in (DeviceKind.CPU, DeviceKind.GPU):
            out += [(d.id, ids) for ids in t[:2]]
        elif t:
            out.append((d.id, t[0]))
    return out


def device_label(device: Device) -> str:
    """Device name, with the drive's own name where several drives look alike."""
    if device.kind == DeviceKind.STORAGE and device.detail:
        return f"{device.name} ({device.detail.split(' · ')[-1]})"
    return device.name


def tile_name(device: Device, ids: list[str]) -> str:
    """Device · group · value, to tell the charts apart in a list."""
    name = device_label(device)
    if len(ids) > 1:
        what = "Traffic" if ids[0].endswith(("/down", "/up")) else "Read / write"
        return f"{name} · {what}"
    for g in device.groups:
        for r in g.readings:
            if r.id == ids[0]:
                return f"{name} · {g.name} · {r.label}"
    return name


def overview_candidates(snap: Snapshot) -> list[tuple[str, list[str], str]]:
    """Every chart the Overview can show: the device tiles first, then each value on its own."""
    out = []
    for d in snap.devices:
        seen = set()
        for ids in tiles(d):
            out.append((d.id, ids, tile_name(d, ids)))
            if len(ids) == 1:
                seen.add(ids[0])
        for g in d.groups:
            for r in g.readings:
                if r.kind != Kind.INFO and r.id not in seen:
                    out.append((d.id, [r.id], f"{device_label(d)} · {g.name} · {r.label}"))
    return out


def default_widget(snap: Snapshot) -> list[str]:
    ids = []
    for d in snap.devices:
        if d.kind in (DeviceKind.CPU, DeviceKind.GPU):
            ids += [r.id for r in _by_suffix(d, "/load/total", "/load")[:1]]
            t = _first(d, Kind.TEMP)
            if t:
                ids.append(t.id)
        elif d.kind == DeviceKind.MEMORY:
            ids += [r.id for r in _by_suffix(d, "/ram/load")]
        elif d.kind == DeviceKind.NETWORK and d.reading(f"{d.id}/link") and \
                (d.reading(f"{d.id}/link").text or "").startswith("Connected"):
            ids += [r.id for r in _by_suffix(d, "/down", "/up")]
    return ids[:8]
