#!/usr/bin/env python3
"""Read-only Tegra20 local-video prerequisite report; no GPU/video decode is started."""
import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys


EXPECTED_CID = "035344534c31323880ac79a543010300"
EXPECTED_KERNEL = "7.0.1-postmarketos-grate"


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, ValueError):
        return None


def bounded_command(argv, timeout=4):
    try:
        result = subprocess.run(
            argv, check=False, capture_output=True, text=True, errors="replace",
            timeout=timeout,
        )
        return {"exit_code": result.returncode, "output": (result.stdout + result.stderr)[:4000]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}


def vde_config(kernel):
    candidates = [
        Path("/proc/config.gz"),
        Path("/boot") / ("config-" + kernel),
        Path("/lib/modules") / kernel / "build" / ".config",
    ]
    for path in candidates:
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
                    data = handle.read()
            else:
                data = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for option in ("CONFIG_VIDEO_TEGRA_VDE", "CONFIG_TEGRA_VDE"):
            for value in ("y", "m", "n"):
                if option + "=" + value in data:
                    return {"source": str(path), "option": option, "value": value}
            if "# " + option + " is not set" in data:
                return {"source": str(path), "option": option, "value": "n"}
        return {"source": str(path), "value": "unknown"}
    return {"source": None, "value": "unknown"}


def wayland_socket():
    display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    path = Path(display) if display.startswith("/") else Path(runtime or "/nonexistent") / display
    try:
        socket_exists = stat.S_ISSOCK(path.stat().st_mode)
        accessible = os.access(path, os.R_OK | os.W_OK)
    except OSError:
        socket_exists = accessible = False
    return {"path": str(path), "is_socket": socket_exists, "accessible": accessible}


def collect():
    kernel = os.uname().release
    cid = read_text("/sys/block/mmcblk1/device/cid")
    cpu = read_text("/proc/cpuinfo") or ""
    features = []
    for line in cpu.splitlines():
        if line.lower().startswith("features") and ":" in line:
            features = line.split(":", 1)[1].strip().split()
            break
    player = shutil.which("mpv")
    vo = bounded_command([player, "--no-config", "--vo=help"]) if player else None
    has_wlshm = bool(vo and vo.get("exit_code") == 0 and
                     any(line.split()[0] == "wlshm" for line in vo.get("output", "").splitlines()
                         if line.split()))
    video_nodes = []
    for path in sorted(Path("/dev").glob("video[0-9]*")):
        name = read_text(Path("/sys/class/video4linux") / path.name / "name")
        video_nodes.append({"path": str(path), "name": name})
    wayland = wayland_socket()
    config = vde_config(kernel)
    report = {
        "schema": "sl101.local-video-probe/v1",
        "readonly": True,
        "identity": {
            "kernel": kernel, "kernel_matches_expected": kernel == EXPECTED_KERNEL,
            "sd_cid_matches_expected": cid == EXPECTED_CID,
            "sd_cid_present": cid is not None,
        },
        "cpu": {"features": features, "neon_advertised": "neon" in features},
        "software": {
            "mpv_path": player, "mpv_wlshm_available": has_wlshm,
            "wayland": wayland,
            "ready_for_software_launch": bool(player and has_wlshm and
                                              wayland["is_socket"] and wayland["accessible"]),
        },
        "vde": {
            "kernel_config": config,
            "video_nodes": video_nodes,
            "hardware_decoding_status": "unqualified",
            "note": "VDE requires decoder device and working V4L2 request userspace; Grate GLES2 does not prove VDE.",
        },
        "audio": {
            "pulse_server_variable_set": bool(os.environ.get("PULSE_SERVER")),
            "default_pulse_socket": str(Path(os.environ.get("XDG_RUNTIME_DIR") or "/nonexistent") / "pulse/native"),
            "verified_playback": False,
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write JSON receipt to an existing output directory")
    args = parser.parse_args()
    payload = json.dumps(collect(), indent=2, sort_keys=True) + "\n"
    if args.output:
        if not args.output.parent.is_dir():
            parser.error("output parent directory must already exist")
        # File is written only when explicitly requested; never to the device by default.
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
