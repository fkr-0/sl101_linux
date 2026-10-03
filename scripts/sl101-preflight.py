#!/usr/bin/env python3
"""Capture a read-only ASUS SL101 Linux/recovery preflight report over ADB.

The probe intentionally avoids root escalation and all device-writing ADB
operations.  It records only command output that can be used to decide whether
later backup/boot work is safe enough to plan.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from android_infra.runner import adb_devices, run  # noqa: E402


@dataclass(frozen=True)
class Probe:
    key: str
    argv: tuple[str, ...]


# Keep this list boring on purpose.  Every command is observational, requires
# no root escalation, and is useful on old Android/Tegra kernels where modern
# /dev/block/by-name layouts cannot be assumed.
PROBES: tuple[Probe, ...] = (
    Probe("manufacturer", ("getprop", "ro.product.manufacturer")),
    Probe("model", ("getprop", "ro.product.model")),
    Probe("device", ("getprop", "ro.product.device")),
    Probe("product", ("getprop", "ro.product.name")),
    Probe("android_release", ("getprop", "ro.build.version.release")),
    Probe("build_fingerprint", ("getprop", "ro.build.fingerprint")),
    Probe("bootloader", ("getprop", "ro.bootloader")),
    Probe("boot_mode", ("getprop", "ro.bootmode")),
    Probe("secure", ("getprop", "ro.secure")),
    Probe("debuggable", ("getprop", "ro.debuggable")),
    Probe("build_type", ("getprop", "ro.build.type")),
    Probe("recovery_version", ("getprop", "ro.recovery.version")),
    Probe("twrp_version", ("getprop", "ro.twrp.version")),
    Probe("kernel", ("uname", "-a")),
    Probe("identity", ("id",)),
    Probe("cpuinfo", ("cat", "/proc/cpuinfo")),
    Probe("kernel_cmdline", ("cat", "/proc/cmdline")),
    Probe("partitions", ("cat", "/proc/partitions")),
    Probe("emmc_layout", ("cat", "/proc/emmc")),
    Probe("mtd_layout", ("cat", "/proc/mtd")),
    Probe("mounts", ("cat", "/proc/mounts")),
    Probe("mount_command", ("mount",)),
    Probe("filesystem_space", ("df", "-h")),
    Probe("data_space_kib", ("df", "-k", "/data")),
    Probe("block_root", ("ls", "-l", "/dev/block")),
    Probe("block_by_name", ("ls", "-l", "/dev/block/by-name")),
    Probe("block_platform", ("ls", "-l", "/dev/block/platform")),
    Probe(
        "su_indicators",
        ("ls", "-l", "/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su"),
    ),
    Probe("recovery_indicators", ("ls", "-ld", "/cache/recovery", "/data/linuxroot")),
)


def safe_serial_component(serial: str) -> str:
    """Return a filesystem-safe representation without changing ADB identity."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", serial).strip("._") or "unknown"


def default_output_path(serial: str, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "state" / "sl101-preflight" / safe_serial_component(serial) / f"{stamp}.json"


def require_connected(serial: str) -> dict[str, str]:
    transports = {item["serial"]: item for item in adb_devices()}
    transport = transports.get(serial)
    if not transport or transport.get("state") != "device":
        state = transport.get("state", "absent") if transport else "absent"
        raise RuntimeError(f"authorized ADB device required: {serial}={state}")
    return transport


def run_probe(serial: str, probe: Probe) -> dict[str, Any]:
    argv = ("adb", "-s", serial, "shell", *probe.argv)
    result = run(argv)
    return {
        "argv": list(probe.argv),
        "returncode": result.returncode,
        "stdout": result.stdout.rstrip(),
        "stderr": result.stderr.rstrip(),
    }


def _probe_stdout(probes: dict[str, dict[str, Any]], key: str) -> str:
    value = probes.get(key, {}).get("stdout", "")
    return value.strip() if isinstance(value, str) else ""


def build_assessment(probes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manufacturer = _probe_stdout(probes, "manufacturer")
    model = _probe_stdout(probes, "model")
    device = _probe_stdout(probes, "device")
    product = _probe_stdout(probes, "product")
    fingerprint = _probe_stdout(probes, "build_fingerprint")
    cpuinfo = _probe_stdout(probes, "cpuinfo").lower()
    partitions = _probe_stdout(probes, "partitions")
    by_name = _probe_stdout(probes, "block_by_name")
    warnings: list[str] = []
    asus = "asus" in manufacturer.lower()
    exact_model = "sl101" in model.lower()
    corroborated_sl101 = any("sl101" in value.lower() for value in (device, product, fingerprint))
    generic_transformer_label = "transformer" in model.lower() and not exact_model
    looks_like_sl101 = asus and (exact_model or corroborated_sl101)
    if not looks_like_sl101:
        warnings.append("ADB properties do not positively identify this transport as an ASUS SL101; do not assign an SL101 inventory serial rule from this report alone.")
    if "vfpv3" not in cpuinfo:
        warnings.append("CPU feature output did not expose vfpv3; verify the Debian armhf baseline before preparing a modern armhf rootfs.")
    if not partitions:
        warnings.append("/proc/partitions was unavailable; partition/backup planning remains blocked.")
    if not by_name:
        warnings.append("No /dev/block/by-name listing was available; map partition labels from additional read-only evidence before any boot/recovery backup or write.")

    return {
        "looks_like_sl101": looks_like_sl101,
        "identity_evidence": "exact-model" if asus and exact_model else "corroborated-generic-transformer-label" if asus and generic_transformer_label and corroborated_sl101 else "unconfirmed",
        "generic_transformer_label_is_cosmetic": asus and generic_transformer_label and corroborated_sl101,
        "armhf_vfpv3_observed": "vfpv3" in cpuinfo,
        "partition_table_observed": bool(partitions),
        "by_name_links_observed": bool(by_name),
        "su_path_indicator_observed": bool(_probe_stdout(probes, "su_indicators")),
        "warnings": warnings,
    }


def build_report(serial: str) -> dict[str, Any]:
    transport = require_connected(serial)
    probes = {probe.key: run_probe(serial, probe) for probe in PROBES}
    return {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "mode": "read-only-no-root-escalation",
        "serial": serial,
        "transport": transport,
        "probes": probes,
        "assessment": build_assessment(probes),
        "safety": {
            "device_writes_performed": False,
            "root_escalation_attempted": False,
            "scope": "ADB shell metadata, procfs, mount/storage listings, and filesystem-presence indicators only",
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture read-only SL101 identity, kernel, partition, mount, CPU, and root/recovery indicators over an already-authorized ADB transport."
    )
    parser.add_argument("--serial", required=True, help="exact ADB transport serial observed in `adb devices -l`")
    parser.add_argument(
        "--out",
        type=Path,
        help="host-side JSON path (default: state/sl101-preflight/<serial>/<UTC timestamp>.json)",
    )
    parser.add_argument("--stdout", action="store_true", help="print JSON instead of writing a host-side report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args.serial)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.stdout:
        print(payload, end="")
        return 0

    output = args.out or default_output_path(args.serial)
    if not output.is_absolute():
        output = REPO_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
