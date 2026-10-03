#!/usr/bin/env python3
"""SL101 compositor-semantics hardware pixel gate.

The gate compares the same wl_shm/subsurface scene through an isolated pixman
labwc control and the candidate Grate GLES2 renderer. It intentionally covers
little-endian ARGB/XRGB memory layout, a padded XRGB row stride, premultiplied
source-over blending, overlapping subsurfaces, and a second bounded-damage
commit.

Passing means pixel equivalence for this compositor workload, not blanket EGL
or wlroots conformance.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import time
from typing import Callable

CID = "035344534c31323880ac79a543010300"
KERNEL = "7.0.1-postmarketos-grate"
FAULT = re.compile(
    r"(?:host1x|gr3d|gr2d|gpu|drm).*(?:fault|reset|timeout)|"
    r"segfault|oom|killed process",
    re.I,
)

XRGB_X, XRGB_Y = 83, 71
XRGB_W, XRGB_H = 173, 97
XRGB_PAD = 52
ARGB_X, ARGB_Y = 170, 110
ARGB_W, ARGB_H = 191, 121
XRGB_PATCH_X, XRGB_PATCH_Y = 15, 12
XRGB_PATCH_W, XRGB_PATCH_H = 47, 31
PARENT_PATCH_W, PARENT_PATCH_H = 91, 53


def premul(channel: int, alpha: int) -> int:
    return (channel * alpha + 127) // 255


def parent_rgb(x: int, y: int, width: int, height: int) -> tuple[int, int, int]:
    patch_x, patch_y = width - 140, height - 95
    if (
        patch_x <= x < patch_x + PARENT_PATCH_W
        and patch_y <= y < patch_y + PARENT_PATCH_H
    ):
        return 7, 211, 79
    return 17, 53, 91


def xrgb_rgb(x: int, y: int) -> tuple[int, int, int]:
    if (
        XRGB_PATCH_X <= x < XRGB_PATCH_X + XRGB_PATCH_W
        and XRGB_PATCH_Y <= y < XRGB_PATCH_Y + XRGB_PATCH_H
    ):
        return 201, 33, 149
    return (
        (x * 3 + 11) & 0xFF,
        (y * 5 + 37) & 0xFF,
        (x + y * 2 + 73) & 0xFF,
    )


def argb_premul(x: int, y: int) -> tuple[int, int, int, int]:
    alpha = (64, 128, 192)[((x // 16) + (y // 12)) % 3]
    r = 220 - ((x // 23) % 4) * 17
    g = 41 + ((y // 19) % 5) * 19
    b = 137 + ((x + y) % 5) * 13
    return premul(r, alpha), premul(g, alpha), premul(b, alpha), alpha


def source_over(
    src: tuple[int, int, int], alpha: int, dst: tuple[int, int, int]
) -> tuple[int, int, int]:
    inv = 255 - alpha
    return tuple(
        min(255, src[c] + (dst[c] * inv + 127) // 255) for c in range(3)
    )


def expected_rgb(x: int, y: int, width: int, height: int) -> tuple[int, int, int]:
    rgb = parent_rgb(x, y, width, height)
    if XRGB_X <= x < XRGB_X + XRGB_W and XRGB_Y <= y < XRGB_Y + XRGB_H:
        rgb = xrgb_rgb(x - XRGB_X, y - XRGB_Y)
    if ARGB_X <= x < ARGB_X + ARGB_W and ARGB_Y <= y < ARGB_Y + ARGB_H:
        sr, sg, sb, a = argb_premul(x - ARGB_X, y - ARGB_Y)
        rgb = source_over((sr, sg, sb), a, rgb)
    return rgb


def oracle(width: int, height: int) -> bytes:
    if width < 400 or height < 300 or width > 2048 or height > 2048:
        raise ValueError("unexpected framebuffer dimensions")
    frame = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            r, g, b = expected_rgb(x, y, width, height)
            i = (y * width + x) * 4
            frame[i : i + 4] = bytes((b, g, r, 255))
    return bytes(frame)


def region_predicates(width: int, height: int) -> dict[str, Callable[[int, int], bool]]:
    parent_patch_x, parent_patch_y = width - 140, height - 95

    def in_xrgb(x: int, y: int) -> bool:
        return XRGB_X <= x < XRGB_X + XRGB_W and XRGB_Y <= y < XRGB_Y + XRGB_H

    def in_argb(x: int, y: int) -> bool:
        return ARGB_X <= x < ARGB_X + ARGB_W and ARGB_Y <= y < ARGB_Y + ARGB_H

    return {
        "background": lambda x, y: not in_xrgb(x, y)
        and not in_argb(x, y)
        and not (
            parent_patch_x <= x < parent_patch_x + PARENT_PATCH_W
            and parent_patch_y <= y < parent_patch_y + PARENT_PATCH_H
        ),
        "parent_damage": lambda x, y: parent_patch_x
        <= x
        < parent_patch_x + PARENT_PATCH_W
        and parent_patch_y <= y < parent_patch_y + PARENT_PATCH_H,
        "xrgb_all": in_xrgb,
        "xrgb_patch": lambda x, y: XRGB_X + XRGB_PATCH_X
        <= x
        < XRGB_X + XRGB_PATCH_X + XRGB_PATCH_W
        and XRGB_Y + XRGB_PATCH_Y
        <= y
        < XRGB_Y + XRGB_PATCH_Y + XRGB_PATCH_H,
        "argb_all": in_argb,
        "overlap": lambda x, y: in_xrgb(x, y) and in_argb(x, y),
    }


def compare(actual: bytes, expected: bytes, width: int, height: int, tolerance: int = 3) -> dict:
    if not actual or len(actual) != len(expected) or len(actual) != width * height * 4:
        raise ValueError("missing, truncated or mismatched framebuffer")

    wrong = total_error = maximum = 0
    regions = {
        name: {"pixels": 0, "wrong_pixels": 0, "maximum_channel_error": 0}
        for name in region_predicates(width, height)
    }
    predicates = region_predicates(width, height)

    for y in range(height):
        for x in range(width):
            i = (y * width + x) * 4
            errors = [abs(actual[i + c] - expected[i + c]) for c in range(3)]
            pixel_error = max(errors)
            is_wrong = pixel_error > tolerance
            wrong += is_wrong
            total_error += sum(errors)
            maximum = max(maximum, pixel_error)

            for name, predicate in predicates.items():
                if predicate(x, y):
                    regions[name]["pixels"] += 1
                    regions[name]["wrong_pixels"] += is_wrong
                    regions[name]["maximum_channel_error"] = max(
                        regions[name]["maximum_channel_error"], pixel_error
                    )

    for stats in regions.values():
        pixels = stats["pixels"]
        stats["wrong_fraction"] = stats["wrong_pixels"] / pixels if pixels else 0.0
        stats["pass"] = bool(pixels) and stats["wrong_fraction"] <= 0.001

    pixels = width * height
    return {
        "pixels": pixels,
        "wrong_pixels": wrong,
        "wrong_fraction": wrong / pixels,
        "mean_channel_error": total_error / (pixels * 3),
        "maximum_channel_error": maximum,
        "channel_tolerance": tolerance,
        "pass": wrong / pixels <= 0.001
        and all(stats["pass"] for stats in regions.values()),
        "regions": regions,
    }


def read_exact(sock: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError("RFB connection closed")
        data.extend(chunk)
    return bytes(data)


def capture(port: int) -> tuple[int, int, bytes]:
    with socket.create_connection(("127.0.0.1", port), timeout=15) as sock:
        version = read_exact(sock, 12)
        if version != b"RFB 003.008\n":
            raise RuntimeError(f"unexpected RFB version {version!r}")
        sock.sendall(version)

        count = read_exact(sock, 1)[0]
        security = read_exact(sock, count)
        if 1 not in security:
            raise RuntimeError("loopback test server does not offer no-auth RFB")
        sock.sendall(b"\x01")
        if read_exact(sock, 4) != bytes(4):
            raise RuntimeError("RFB security negotiation failed")

        sock.sendall(b"\x01")
        header = read_exact(sock, 24)
        width, height = struct.unpack(">HH", header[:4])
        read_exact(sock, struct.unpack(">I", header[20:24])[0])
        if width < 1 or height < 1 or width > 2048 or height > 2048:
            raise RuntimeError("unexpected RFB dimensions")

        # 32 bpp little-endian B,G,R,unused byte.
        sock.sendall(
            bytes(4)
            + struct.pack(">BBBBHHHBBB3x", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        )
        sock.sendall(struct.pack(">BBHi", 2, 0, 1, 0))
        sock.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, width, height))

        frame = bytearray(width * height * 4)
        covered = bytearray(width * height)
        covered_count = 0
        while covered_count < width * height:
            message = read_exact(sock, 1)[0]
            if message == 2:
                continue
            if message == 3:
                text_header = read_exact(sock, 7)
                read_exact(sock, struct.unpack(">I", text_header[3:])[0])
                continue
            if message != 0:
                raise RuntimeError(f"unexpected RFB message {message}")

            _, rectangles = struct.unpack(">BH", read_exact(sock, 3))
            for _ in range(rectangles):
                x, y, rw, rh, encoding = struct.unpack(">HHHHi", read_exact(sock, 12))
                if (
                    encoding != 0
                    or not rw
                    or not rh
                    or x + rw > width
                    or y + rh > height
                ):
                    raise RuntimeError("invalid framebuffer rectangle")
                raw = read_exact(sock, rw * rh * 4)
                for row in range(rh):
                    start = (y + row) * width + x
                    frame[start * 4 : (start + rw) * 4] = raw[
                        row * rw * 4 : (row + 1) * rw * 4
                    ]
                    covered_count += rw - sum(covered[start : start + rw])
                    covered[start : start + rw] = b"\x01" * rw

        frame[3::4] = b"\xff" * (width * height)
        return width, height, bytes(frame)


def wait_for(predicate, processes: list[subprocess.Popen], seconds: float = 15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(
                    f"test process pid={process.pid} exited rc={process.returncode}"
                )
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise TimeoutError("test readiness timed out")


def run_mode(mode: str, args, root: Path) -> dict:
    out = root / mode
    out.mkdir()
    runtime = out / "runtime"
    runtime.mkdir(mode=0o700)
    config = out / "config"
    config.mkdir()
    (config / "rc.xml").write_text("<labwc_config/>\n")
    (config / "autostart").write_text("")
    (config / "autostart").chmod(0o755)

    env = os.environ.copy()
    for key in (
        "LD_LIBRARY_PATH",
        "GBM_BACKENDS_PATH",
        "LIBGL_DRIVERS_PATH",
        "MESA_LOADER_DRIVER_OVERRIDE",
        "LIBGL_ALWAYS_SOFTWARE",
        "WAYLAND_DISPLAY",
        "DBUS_SESSION_BUS_ADDRESS",
    ):
        env.pop(key, None)
    env.update(
        XDG_RUNTIME_DIR=str(runtime),
        WLR_BACKENDS="headless",
        WLR_HEADLESS_OUTPUTS="1",
        WLR_LIBINPUT_NO_DEVICES="1",
        WLR_RENDERER="pixman" if mode == "pixman" else "gles2",
        WLR_RENDERER_ALLOW_SOFTWARE="0",
    )
    if mode == "grate":
        env.update(
            LD_LIBRARY_PATH=str(args.prefix / "lib"),
            GBM_BACKENDS_PATH=str(args.prefix / "lib/gbm"),
            LIBGL_DRIVERS_PATH=str(args.prefix / "lib"),
            MESA_LOADER_DRIVER_OVERRIDE="grate",
        )

    processes: list[subprocess.Popen] = []
    logs = []

    def start(name: str, command: list[str], child_env: dict) -> subprocess.Popen:
        log = (out / f"{name}.log").open("wb")
        logs.append(log)
        process = subprocess.Popen(
            command,
            env=child_env,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        processes.append(process)
        return process

    try:
        compositor = start("labwc", [args.labwc, "-V", "-C", str(config)], env)
        wait_for(
            lambda: next(
                (p for p in runtime.glob("wayland-*") if p.is_socket()), None
            ),
            processes,
        )
        display_path = next(p for p in runtime.glob("wayland-*") if p.is_socket())

        client_env = env.copy()
        for key in (
            "LD_LIBRARY_PATH",
            "GBM_BACKENDS_PATH",
            "LIBGL_DRIVERS_PATH",
            "MESA_LOADER_DRIVER_OVERRIDE",
            "LIBGL_ALWAYS_SOFTWARE",
        ):
            client_env.pop(key, None)
        client_env["WAYLAND_DISPLAY"] = display_path.name

        fixture = start("fixture", [str(args.client)], client_env)
        wait_for(
            lambda: "FIXTURE_COMMITTED" in (out / "fixture.log").read_text(),
            processes,
        )

        fixture_log = (out / "fixture.log").read_text()
        if "PHASE1_COMMITTED" not in fixture_log or "PHASE2_COMMITTED" not in fixture_log:
            raise RuntimeError("fixture did not complete both synchronized commits")
        if "formats=ARGB8888,XRGB8888" not in fixture_log:
            raise RuntimeError("fixture did not advertise both required shm formats")
        if f"padded_stride={XRGB_W * 4 + XRGB_PAD}" not in fixture_log:
            raise RuntimeError("fixture padded stride marker mismatch")

        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        wayvnc_conf = out / "wayvnc.conf"
        wayvnc_conf.write_text(
            f"address=127.0.0.1\nport={port}\nenable_auth=false\n"
        )
        start(
            "wayvnc",
            [
                args.wayvnc,
                "-d",
                "-R",
                "-f",
                "1",
                "-C",
                str(wayvnc_conf),
                "-S",
                str(runtime / "capture-control"),
            ],
            client_env,
        )

        time.sleep(1.0)
        stable: list[bytes] = []
        width = height = 0
        for attempt in range(5):
            width, height, pixels = capture(port)
            (out / f"capture-{attempt}.bgra").write_bytes(pixels)
            (out / f"capture-{attempt}.json").write_text(
                json.dumps(
                    {
                        "width": width,
                        "height": height,
                        "sha256": hashlib.sha256(pixels).hexdigest(),
                        "unique_b": len(set(pixels[0::4])),
                        "unique_g": len(set(pixels[1::4])),
                        "unique_r": len(set(pixels[2::4])),
                    },
                    indent=2,
                )
                + "\n"
            )
            if len(set(pixels[0::4])) > 8 and len(set(pixels[2::4])) > 8:
                stable.append(pixels)
                if len(stable) >= 2 and stable[-1] == stable[-2]:
                    break
                stable = stable[-1:]
            time.sleep(0.5)

        if len(stable) < 2 or stable[-1] != stable[-2]:
            raise RuntimeError("no two stable nonblank compositor captures")

        pixels = stable[-1]
        expected = oracle(width, height)
        (out / "frame.bgra").write_bytes(pixels)
        (out / "oracle.bgra").write_bytes(expected)

        renderer_log = (out / "labwc.log").read_text(errors="replace")
        lower_log = renderer_log.lower()
        if mode == "grate":
            if "gl vendor: grate" not in lower_log or "gl renderer: tegra" not in lower_log:
                raise RuntimeError("missing Grate/Tegra renderer identity")
            if "llvmpipe" in lower_log or "softpipe" in lower_log:
                raise RuntimeError("software renderer fallback detected")
            maps = Path(f"/proc/{compositor.pid}/maps").read_text()
            expected_mapping = str(args.prefix / "lib/libgallium")
            if expected_mapping not in maps:
                raise RuntimeError("candidate libgallium was not mapped by labwc")
            (out / "maps").write_text(maps)
        elif "creating pixman renderer" not in lower_log:
            raise RuntimeError("missing pixman control identity")

        result = compare(pixels, expected, width, height)
        result.update(
            mode=mode,
            width=width,
            height=height,
            stable_frames=2,
            frame_sha256=hashlib.sha256(pixels).hexdigest(),
            oracle_sha256=hashlib.sha256(expected).hexdigest(),
            compositor_pid=compositor.pid,
            fixture_pid=fixture.pid,
            fixture_log_markers={
                "phase1": "PHASE1_COMMITTED" in fixture_log,
                "phase2": "PHASE2_COMMITTED" in fixture_log,
                "formats": "ARGB8888,XRGB8888",
                "xrgb_stride": XRGB_W * 4 + XRGB_PAD,
            },
        )
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()


def dmesg_delta(before: str, after: str) -> list[str]:
    old_lines = before.splitlines()
    new_lines = after.splitlines()
    if new_lines[: len(old_lines)] == old_lines:
        return new_lines[len(old_lines) :]
    old_set = set(old_lines)
    return [line for line in new_lines if line not in old_set]


def main() -> int:
    def interrupted(signum, _frame):
        raise RuntimeError(f"qualification interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, type=Path)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--expected-gallium-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--labwc", default="labwc")
    parser.add_argument("--wayvnc", default="wayvnc")
    args = parser.parse_args()

    args.client = args.client.resolve(strict=True)
    args.prefix = args.prefix.resolve(strict=True)
    args.output = args.output.absolute()

    if os.geteuid() != 0:
        parser.error("run this hardware gate as root")
    if os.uname().release != KERNEL:
        parser.error(f"wrong kernel: expected {KERNEL}")
    if Path("/sys/block/mmcblk1/device/cid").read_text().strip() != CID:
        parser.error("wrong SL101 SD/device identity")

    gallium = args.prefix / "lib/libgallium-25.0.7.so"
    if not gallium.is_file():
        parser.error("candidate libgallium is missing")
    actual_hash = hashlib.sha256(gallium.read_bytes()).hexdigest()
    if actual_hash != args.expected_gallium_sha256:
        parser.error(
            f"candidate hash mismatch expected={args.expected_gallium_sha256} "
            f"actual={actual_hash}"
        )

    with open("/run/lock/sl101-nura-qualification.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        visible_pid = int(Path("/run/sl101-desktop.pid").read_text())
        visible_start = Path(f"/proc/{visible_pid}/stat").read_text().split()[21]

        args.output.mkdir()
        before = subprocess.check_output(["dmesg"], text=True)
        (args.output / "dmesg.before").write_text(before)

        summary = {
            "schema": "sl101-grate-compositor-semantics",
            "version": 1,
            "kernel": KERNEL,
            "sd_cid": CID,
            "driver_sha256": actual_hash,
            "fixture_sha256": hashlib.sha256(args.client.read_bytes()).hexdigest(),
            "qualification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "prefix": str(args.prefix),
            "visible_pid": visible_pid,
            "pass": False,
        }

        try:
            control = run_mode("pixman", args, args.output)
            summary["pixman"] = control
            print(json.dumps(control), flush=True)
            if not control["pass"]:
                raise RuntimeError(
                    "pixman control fails the independent compositor oracle"
                )

            gpu = run_mode("grate", args, args.output)
            summary["grate"] = gpu
            print(json.dumps(gpu), flush=True)
            summary["pass"] = gpu["pass"]
        except Exception as error:
            summary["error"] = str(error)
        finally:
            after = subprocess.check_output(["dmesg"], text=True)
            (args.output / "dmesg.after").write_text(after)
            delta = dmesg_delta(before, after)
            faults = [line for line in delta if FAULT.search(line)]
            (args.output / "dmesg.delta").write_text("\n".join(delta) + ("\n" if delta else ""))
            (args.output / "dmesg.faults").write_text(
                "\n".join(faults) + ("\n" if faults else "")
            )
            summary["kernel_faults"] = faults
            try:
                survived = (
                    Path(f"/proc/{visible_pid}/stat").read_text().split()[21]
                    == visible_start
                )
            except OSError:
                survived = False
            summary["visible_desktop_survived"] = survived
            summary["pass"] = bool(summary["pass"] and survived and not faults)
            (args.output / "summary.json").write_text(
                json.dumps(summary, indent=2) + "\n"
            )

        print(json.dumps(summary), flush=True)
        return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
