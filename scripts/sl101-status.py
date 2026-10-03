#!/usr/bin/env python3
"""Compact dependency-free ASUS SL101 system health/status report.

Reads Linux /proc and /sys directly. Suitable for the minimal Debian image.
Reports battery/AC, RAM, CPU load, thermal zones, Wi-Fi, Bluetooth and the
SL101 EC/keyboard presence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import socket
import time

PROC = Path("/proc")
SYS = Path("/sys")


def text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return None


def integer(path: Path) -> int | None:
    v = text(path)
    try:
        return None if v is None else int(v)
    except ValueError:
        return None


def meminfo(proc: Path = PROC) -> dict:
    out = {}
    raw = text(proc / "meminfo") or ""
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fields = v.strip().split()
        if not fields:
            continue
        try:
            n = int(fields[0])
        except ValueError:
            continue
        out[k] = n * 1024 if len(fields) > 1 and fields[1].lower() == "kb" else n
    total = out.get("MemTotal")
    avail = out.get("MemAvailable")
    used = total - avail if total is not None and avail is not None else None
    pct = (used / total * 100.0) if total and used is not None else None
    return {"total_bytes": total, "available_bytes": avail, "used_bytes": used, "used_percent": pct}


def load(proc: Path = PROC) -> dict:
    raw = (text(proc / "loadavg") or "").split()
    vals = []
    for x in raw[:3]:
        try:
            vals.append(float(x))
        except ValueError:
            vals.append(None)
    while len(vals) < 3:
        vals.append(None)
    return {"load1": vals[0], "load5": vals[1], "load15": vals[2], "cpu_count": (os_cpu_count() or 1)}


def os_cpu_count() -> int | None:
    try:
        import os
        return os.cpu_count()
    except Exception:
        return None


def uptime(proc: Path = PROC) -> float | None:
    raw = (text(proc / "uptime") or "").split()
    try:
        return float(raw[0]) if raw else None
    except ValueError:
        return None


def power(sysroot: Path = SYS) -> dict:
    root = sysroot / "class/power_supply"
    supplies = []
    if root.exists():
        for p in sorted(root.iterdir()):
            typ = text(p / "type") or "Unknown"
            d = {"name": p.name, "type": typ}
            for key in ("status", "model_name", "manufacturer"):
                v = text(p / key)
                if v is not None:
                    d[key] = v
            for key in ("online", "capacity", "cycle_count"):
                v = integer(p / key)
                if v is not None:
                    d[key] = v
            for key, div, outk in (
                ("voltage_now", 1_000_000, "voltage_v"),
                ("current_now", 1_000_000, "current_a"),
                ("power_now", 1_000_000, "power_w"),
                ("charge_now", 1_000_000, "charge_now_ah"),
                ("charge_full", 1_000_000, "charge_full_ah"),
                ("temp", 10, "temperature_c"),
            ):
                v = integer(p / key)
                if v is not None:
                    d[outk] = v / div
            supplies.append(d)
    return {
        "battery": [s for s in supplies if s["type"] == "Battery"],
        "external": [s for s in supplies if s["type"] in {"Mains", "USB", "USB_C", "USB_PD"}],
    }


def thermal(sysroot: Path = SYS) -> list[dict]:
    out = []
    root = sysroot / "class/thermal"
    if not root.exists():
        return out
    for p in sorted(root.glob("thermal_zone*")):
        t = integer(p / "temp")
        out.append({
            "name": p.name,
            "type": text(p / "type") or p.name,
            "temperature_c": None if t is None else t / 1000.0,
        })
    return out


def wifi(proc: Path = PROC, sysroot: Path = SYS) -> list[dict]:
    quality = {}
    raw = text(proc / "net/wireless") or ""
    for line in raw.splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        f = rest.split()
        if len(f) >= 3:
            try:
                quality[name.strip()] = {"link": float(f[0].rstrip(".")), "level_dbm": float(f[1].rstrip("."))}
            except ValueError:
                pass
    out = []
    netroot = sysroot / "class/net"
    if not netroot.exists():
        return out
    for p in sorted(netroot.iterdir()):
        if not (p / "wireless").exists():
            continue
        d = {
            "interface": p.name,
            "operstate": text(p / "operstate"),
            "carrier": integer(p / "carrier"),
            "mac": text(p / "address"),
        }
        d.update(quality.get(p.name, {}))
        out.append(d)
    return out


def bluetooth(sysroot: Path = SYS) -> dict:
    btroot = sysroot / "class/bluetooth"
    adapters = []
    if btroot.exists():
        for p in sorted(btroot.iterdir()):
            adapters.append({"name": p.name, "address": text(p / "address")})
    rfkill = []
    rroot = sysroot / "class/rfkill"
    if rroot.exists():
        for p in sorted(rroot.iterdir()):
            typ = text(p / "type")
            if typ == "bluetooth":
                rfkill.append({
                    "name": text(p / "name") or p.name,
                    "soft": integer(p / "soft"),
                    "hard": integer(p / "hard"),
                })
    return {"adapters": adapters, "rfkill": rfkill}


def input_ec(sysroot: Path = SYS) -> dict:
    dt = sysroot / "firmware/devicetree/base"
    ec_nodes = [str(p) for p in dt.rglob("embedded-controller@19")] if dt.exists() else []
    i2c = sysroot / "bus/i2c/devices"
    i2c19 = [p.name for p in i2c.glob("*-0019")] if i2c.exists() else []
    bypath = Path("/dev/input/by-path")
    keyboard = []
    if bypath.exists():
        keyboard = sorted(p.name for p in bypath.iterdir() if "kbd" in p.name or "serio" in p.name)
    return {"ec_dt_nodes": ec_nodes, "i2c_0019": i2c19, "keyboard_paths": keyboard}


def collect(proc: Path = PROC, sysroot: Path = SYS) -> dict:
    return {
        "host": socket.gethostname(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "uptime_seconds": uptime(proc),
        "cpu": load(proc),
        "memory": meminfo(proc),
        "power": power(sysroot),
        "thermal": thermal(sysroot),
        "wifi": wifi(proc, sysroot),
        "bluetooth": bluetooth(sysroot),
        "input": input_ec(sysroot),
    }


def human_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    return f"{n / (1024**2):.0f} MiB"


def render(d: dict) -> str:
    lines = [f"{d['host']}  kernel {d['kernel']}  {d['machine']}"]
    up = d.get("uptime_seconds")
    if up is not None:
        lines.append(f"Uptime: {up/3600:.1f} h")

    cpu = d["cpu"]
    lines.append(f"CPU: load {cpu.get('load1', '-')} {cpu.get('load5', '-')} {cpu.get('load15', '-')}  cores {cpu.get('cpu_count', '-')}")

    mem = d["memory"]
    pct = mem.get("used_percent")
    lines.append(f"RAM: {human_bytes(mem.get('used_bytes'))} / {human_bytes(mem.get('total_bytes'))}" + (f" ({pct:.1f}%)" if pct is not None else ""))

    bats = d["power"]["battery"]
    if bats:
        for b in bats:
            label = b.get("model_name") or b["name"]
            parts = [b.get("status", "-")]
            if "capacity" in b:
                parts.append(f"{b['capacity']}%")
            if "voltage_v" in b:
                parts.append(f"{b['voltage_v']:.2f} V")
            if "temperature_c" in b:
                parts.append(f"{b['temperature_c']:.1f} C")
            lines.append(f"Battery {label}: " + ", ".join(parts))
    else:
        lines.append("Battery: not found")
    ext = d["power"]["external"]
    lines.append("AC/external: " + (", ".join(f"{x['name']}={'online' if x.get('online') == 1 else 'offline'}" for x in ext) if ext else "not found"))

    temps = [x for x in d["thermal"] if x.get("temperature_c") is not None]
    lines.append("Thermal: " + (", ".join(f"{x['type']}={x['temperature_c']:.1f} C" for x in temps) if temps else "not found"))

    lines.append("Wi-Fi: " + (", ".join(f"{x['interface']} {x.get('operstate','?')}" + (f" {x['level_dbm']:.0f} dBm" if 'level_dbm' in x else "") for x in d["wifi"]) if d["wifi"] else "not found"))

    bt = d["bluetooth"]
    bt_parts = [x["name"] for x in bt["adapters"]]
    bt_parts += [f"{x['name']} soft={x.get('soft','?')} hard={x.get('hard','?')}" for x in bt["rfkill"]]
    lines.append("Bluetooth: " + (", ".join(bt_parts) if bt_parts else "not found"))

    inp = d["input"]
    ec = bool(inp["ec_dt_nodes"] or inp["i2c_0019"])
    lines.append(f"EC/keyboard: EC={'yes' if ec else 'no'}, keyboard paths={len(inp['keyboard_paths'])}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--watch", type=float, metavar="SECONDS")
    args = ap.parse_args()
    while True:
        d = collect()
        print(json.dumps(d, indent=2, sort_keys=True) if args.json else render(d))
        if args.watch is None:
            return 0
        time.sleep(max(0.5, args.watch))
        if not args.json:
            print()


if __name__ == "__main__":
    raise SystemExit(main())
