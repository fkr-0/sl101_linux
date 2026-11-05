#!/usr/bin/env python3
"""Read-only, bounded SL101 health sampling over SSH.

Writes results only on the *host* where this program runs. The remote payload
reads /proc, sysfs, and a single renderer config file. It never reads evdev
payloads, starts Cog, mounts anything, or changes desktop/kernel configuration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

TARGET = "user@192.168.23.106"
EXPECTED = {
    "hostname": "sl101-nura",
    "kernel": "7.0.1-postmarketos-grate",
    "cid": "035344534c31323880ac79a543010300",
}
FAULT_PATTERN = re.compile(
    r"(?:host1x.*(?:fault|timeout)|gr3d.*(?:timeout|reset)|"
    r"tegra_drm_sched_timedout_job|gpu fault|watchdog|oom.kill|"
    r"blocked for more than)", re.IGNORECASE
)
REMOTE_PY = r"""
import json, os, platform, socket, time
from datetime import datetime, timezone

def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, UnicodeError):
        return None

def proc():
    result = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        comm = read("/proc/%s/comm" % name)
        if comm not in ("labwc", "cog", "WPEWebProcess"):
            continue
        stat = read("/proc/%s/stat" % name)
        if not stat:
            continue
        after = stat[stat.rfind(")") + 2:].split()
        if len(after) < 20:
            continue
        result.append({"pid": int(name), "comm": comm,
                       "state": after[0], "start_ticks": after[19]})
    return sorted(result, key=lambda x: x["pid"])

def memory():
    result = {}
    for line in (read("/proc/meminfo") or "").splitlines():
        key, _, value = line.partition(":")
        if key in ("MemAvailable", "SwapFree", "MemTotal"):
            result[key] = value.strip()
    return result

def psi(which):
    text = read("/proc/pressure/" + which)
    if text is None:
        return None
    return [line[:180] for line in text.splitlines()[:2]]

def mounts():
    text = read("/proc/self/mountinfo") or ""
    prefix = "/opt/sl101-cog-wpe-debian/"
    n = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) > 4 and parts[4].startswith(prefix):
            n += 1
    return n

output = {
    "utc": datetime.now(timezone.utc).isoformat(),
    "hostname": socket.gethostname(),
    "kernel": platform.release(),
    "cid": read("/sys/block/mmcblk1/device/cid"),
    "boot_id": read("/proc/sys/kernel/random/boot_id"),
    "uptime": (read("/proc/uptime") or "").split(" ")[0],
    "renderer": read("/etc/sl101-desktop-renderer.conf"),
    "processes": proc(),
    "memory": memory(),
    "psi": {kind: psi(kind) for kind in ("cpu", "memory", "io")},
    "chroot_mount_count": mounts(),
}
print(json.dumps(output, sort_keys=True))
"""


class SafetyGate(RuntimeError):
    """Identity or runtime inconsistency; never continue collecting."""


def validate(sample: dict, *, first_boot: str | None = None) -> str:
    for name, expected in EXPECTED.items():
        if sample.get(name) != expected:
            raise SafetyGate(f"identity_mismatch:{name}")
    boot_id = sample.get("boot_id")
    if not isinstance(boot_id, str) or len(boot_id) < 30:
        raise SafetyGate("missing_boot_identity")
    if first_boot is not None and boot_id != first_boot:
        raise SafetyGate("boot_changed")
    if sample.get("renderer") != "SL101_DESKTOP_RENDERER=grate":
        raise SafetyGate("renderer_changed")
    processes = sample.get("processes")
    if not isinstance(processes, list):
        raise SafetyGate("missing_process_data")
    if not any(p.get("comm") in ("labwc", "cog") for p in processes):
        raise SafetyGate("no_desktop_or_browser")
    return boot_id


def fetch(*, target: str = TARGET) -> dict:
    # The remote process reads fixed paths only; input is Python source over stdin.
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "ConnectTimeout=4", target, "/usr/sbin/python3", "-"]
    result = subprocess.run(cmd, input=REMOTE_PY, text=True,
                            capture_output=True, timeout=9, check=False)
    if result.returncode != 0:
        raise SafetyGate("ssh_or_remote_probe_failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SafetyGate("invalid_remote_probe_payload") from exc


def kernel_fault_count(*, target: str = TARGET) -> int:
    """Read kernel ring without storing messages; count relevant faults only."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "ConnectTimeout=4", target, "sudo", "-n", "dmesg"]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=9, check=False)
    if result.returncode != 0:
        raise SafetyGate("kernel_log_unavailable")
    return sum(bool(FAULT_PATTERN.search(line)) for line in result.stdout.splitlines())


def collect(*, samples: int = 5, interval: float = 1.0,
            runner=fetch, pause=time.sleep) -> list[dict]:
    if not (1 <= samples <= 12) or not (0.5 <= interval <= 2.0):
        raise ValueError("samples 1..12, interval 0.5..2.0 seconds")
    records = []
    boot = None
    for i in range(samples):
        start = time.monotonic()
        record = runner()
        boot = validate(record, first_boot=boot)
        record["sample_index"] = i
        records.append(record)
        if i < samples - 1:
            pause(max(0.0, interval - (time.monotonic() - start)))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    try:
        kernel_before = kernel_fault_count()
        rows = collect(samples=options.samples, interval=options.interval)
        kernel_after = kernel_fault_count()
    except (SafetyGate, subprocess.TimeoutExpired) as exc:
        print(f"FAIL_CLOSED: {exc}", flush=True)
        return 2
    rows[0]["kernel_faults_before"] = kernel_before
    rows[-1]["kernel_faults_after"] = kernel_after
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    processes = [p["comm"] for p in rows[-1]["processes"]]
    result = "PASS_READ_ONLY" if kernel_after <= kernel_before else "ALERT_NEW_KERNEL_FAULTS"
    print(json.dumps({"result": result, "samples": len(rows),
                      "kernel_faults_before": kernel_before,
                      "kernel_faults_after": kernel_after,
                      "boot_id": rows[0]["boot_id"],
                      "renderer": rows[-1]["renderer"],
                      "processes": processes,
                      "chroot_mount_count": rows[-1]["chroot_mount_count"],
                      "host_output": str(options.output)}, sort_keys=True))
    return 0 if result == "PASS_READ_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
