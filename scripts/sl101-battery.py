#!/usr/bin/env python3
"""Report ASUS SL101 battery and external-power state from Linux sysfs.

The SL101 native-Linux stack exposes power through the kernel power_supply
subsystem (SBS battery + GPIO mains/charger), not through userspace ACPI.
No external Python packages are required.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

SYSFS = Path("/sys/class/power_supply")


def read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def read_int(path: Path) -> int | None:
    value = read_text(path)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def scaled(value: int | None, divisor: float) -> float | None:
    return None if value is None else value / divisor


def supply_info(path: Path) -> dict:
    typ = read_text(path / "type") or "Unknown"
    info = {
        "name": path.name,
        "type": typ,
        "status": read_text(path / "status"),
        "online": read_int(path / "online"),
        "capacity_percent": read_int(path / "capacity"),
        "voltage_v": scaled(read_int(path / "voltage_now"), 1_000_000),
        "current_a": scaled(read_int(path / "current_now"), 1_000_000),
        "power_w": scaled(read_int(path / "power_now"), 1_000_000),
        "charge_now_ah": scaled(read_int(path / "charge_now"), 1_000_000),
        "charge_full_ah": scaled(read_int(path / "charge_full"), 1_000_000),
        "charge_full_design_ah": scaled(read_int(path / "charge_full_design"), 1_000_000),
        "energy_now_wh": scaled(read_int(path / "energy_now"), 1_000_000),
        "energy_full_wh": scaled(read_int(path / "energy_full"), 1_000_000),
        "energy_full_design_wh": scaled(read_int(path / "energy_full_design"), 1_000_000),
        "temperature_c": scaled(read_int(path / "temp"), 10),
        "cycle_count": read_int(path / "cycle_count"),
        "model_name": read_text(path / "model_name"),
        "manufacturer": read_text(path / "manufacturer"),
        "serial_number": read_text(path / "serial_number"),
    }
    return {k: v for k, v in info.items() if v is not None}


def collect(root: Path = SYSFS) -> dict:
    supplies = []
    if root.exists():
        for path in sorted(p for p in root.iterdir() if p.is_dir() or p.is_symlink()):
            supplies.append(supply_info(path))
    batteries = [s for s in supplies if s.get("type") == "Battery"]
    external = [s for s in supplies if s.get("type") in {"Mains", "USB", "USB_C", "USB_PD"}]
    return {
        "batteries": batteries,
        "external_power": external,
        "supplies": supplies,
    }


def fmt_num(value: float | int | None, unit: str = "", digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value}{unit}"
    return f"{value:.{digits}f}{unit}"


def render(data: dict) -> str:
    lines = []
    batteries = data["batteries"]
    external = data["external_power"]

    if not batteries:
        lines.append("Battery: not found")
    for b in batteries:
        name = b.get("model_name") or b["name"]
        lines.append(f"Battery {name}")
        lines.append(f"  status:      {b.get('status', '-')}")
        lines.append(f"  capacity:    {fmt_num(b.get('capacity_percent'), '%', 0)}")
        lines.append(f"  voltage:     {fmt_num(b.get('voltage_v'), ' V')}")
        lines.append(f"  current:     {fmt_num(b.get('current_a'), ' A')}")
        lines.append(f"  power:       {fmt_num(b.get('power_w'), ' W')}")
        if "charge_now_ah" in b:
            lines.append(f"  charge:      {fmt_num(b.get('charge_now_ah'), ' Ah')} / {fmt_num(b.get('charge_full_ah'), ' Ah')}")
        if "energy_now_wh" in b:
            lines.append(f"  energy:      {fmt_num(b.get('energy_now_wh'), ' Wh')} / {fmt_num(b.get('energy_full_wh'), ' Wh')}")
        lines.append(f"  temperature: {fmt_num(b.get('temperature_c'), ' °C', 1)}")
        lines.append(f"  cycles:      {fmt_num(b.get('cycle_count'), '', 0)}")

    if not external:
        lines.append("External power: not found")
    for p in external:
        state = "online" if p.get("online") == 1 else "offline"
        lines.append(f"External power {p['name']}: {state}")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--watch", type=float, metavar="SECONDS", help="refresh continuously")
    ap.add_argument("--sysfs", type=Path, default=SYSFS, help=argparse.SUPPRESS)
    args = ap.parse_args()

    while True:
        data = collect(args.sysfs)
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(render(data))
        if args.watch is None:
            return 0
        time.sleep(max(0.2, args.watch))
        if not args.json:
            print()


if __name__ == "__main__":
    raise SystemExit(main())
