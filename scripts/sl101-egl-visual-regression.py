#!/usr/bin/env python3
"""Hardware pixel gate: isolated pixman/Grate composition of a fixed wl_shm image.

Run on the SL101 with the separately built fixture client. Exit 0 requires the
CPU control and GPU pixels to match the independently specified fixture, stable
captures, no new kernel faults, and survival of the visible desktop. Merely
returning a framebuffer or completing GPU jobs is not a visual pass.
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

CID = "035344534c31323880ac79a543010300"
FAULT = re.compile(r"(?:host1x|gr3d|gr2d|gpu|drm).*(?:fault|reset|timeout)|segfault|oom|killed process", re.I)


def oracle(width: int, height: int) -> bytes:
    """Public fixture specification in BGRA memory order, opaque alpha."""
    if not 1 <= width <= 2048 or not 1 <= height <= 2048:
        raise ValueError("unexpected framebuffer dimensions")
    frame = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            if x % 127 == 0 or y % 61 == 0:
                pixel = (255, 255, 255, 255)
            else:
                pixel = (224 if (x // 17 + y // 13) & 1 else 32, y % 241, x % 251, 255)
            i = (y * width + x) * 4
            frame[i:i + 4] = bytes(pixel)
    return bytes(frame)


def compare(actual: bytes, expected: bytes, tolerance: int = 2) -> dict:
    if not actual or len(actual) != len(expected) or len(actual) % 4:
        raise ValueError("missing, truncated or mismatched framebuffer")
    wrong = total_error = maximum = 0
    for i in range(0, len(actual), 4):
        errors = [abs(actual[i + c] - expected[i + c]) for c in range(3)]
        wrong += max(errors) > tolerance
        total_error += sum(errors)
        maximum = max(maximum, *errors)
    pixels = len(actual) // 4
    return {
        "pixels": pixels, "wrong_pixels": wrong,
        "wrong_fraction": wrong / pixels,
        "mean_channel_error": total_error / (pixels * 3),
        "maximum_channel_error": maximum, "channel_tolerance": tolerance,
        "pass": wrong / pixels <= 0.001,
    }


def nonblank(pixels: bytes) -> bool:
    # R/G carry the coordinate ramps. B deliberately has only checker values
    # 32/224 plus white 255, so requiring many blue values rejects the fixture.
    return len(set(pixels[2::4])) > 4 and len(set(pixels[1::4])) > 4


def read_exact(sock: socket.socket, n: int) -> bytes:
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
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
        if 1 not in read_exact(sock, count):
            raise RuntimeError("test server does not offer loopback no-auth RFB")
        sock.sendall(b"\x01")
        if read_exact(sock, 4) != bytes(4):
            raise RuntimeError("RFB security negotiation failed")
        sock.sendall(b"\x01")
        header = read_exact(sock, 24)
        width, height = struct.unpack(">HH", header[:4])
        read_exact(sock, struct.unpack(">I", header[20:24])[0])
        if not 1 <= width <= 2048 or not 1 <= height <= 2048:
            raise RuntimeError("unexpected RFB size")
        sock.sendall(bytes(4) + struct.pack(">BBBBHHHBBB3x", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
        sock.sendall(struct.pack(">BBHi", 2, 0, 1, 0))  # raw encoding only
        sock.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, width, height))
        frame = bytearray(width * height * 4)
        covered = bytearray(width * height)
        covered_count = 0
        # Count covered pixels, not summed rectangle areas: overlap cannot make
        # an incomplete framebuffer look complete.
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
            _, count = struct.unpack(">BH", read_exact(sock, 3))
            for _ in range(count):
                x, y, rw, rh, encoding = struct.unpack(">HHHHi", read_exact(sock, 12))
                if encoding != 0 or x + rw > width or y + rh > height or not rw or not rh:
                    raise RuntimeError("invalid framebuffer rectangle")
                raw = read_exact(sock, rw * rh * 4)
                for row in range(rh):
                    start = (y + row) * width + x
                    frame[start * 4:(start + rw) * 4] = raw[row * rw * 4:(row + 1) * rw * 4]
                    covered_count += rw - sum(covered[start:start + rw])
                    covered[start:start + rw] = b"\x01" * rw
        return width, height, bytes(frame)


def wait_for(predicate, processes: list[subprocess.Popen], seconds: int = 15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError("test process exited early; inspect its log")
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
    cfg = out / "config"
    cfg.mkdir()
    (cfg / "rc.xml").write_text("<labwc_config/>\n")
    (cfg / "autostart").write_text("")
    (cfg / "autostart").chmod(0o755)
    env = os.environ.copy()
    for key in ("LD_LIBRARY_PATH", "GBM_BACKENDS_PATH", "LIBGL_DRIVERS_PATH", "MESA_LOADER_DRIVER_OVERRIDE", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
        env.pop(key, None)
    env.update(XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1", WLR_LIBINPUT_NO_DEVICES="1", WLR_RENDERER="pixman" if mode == "pixman" else "gles2")
    if mode == "grate":
        env.update(LD_LIBRARY_PATH=str(args.prefix / "lib"), GBM_BACKENDS_PATH=str(args.prefix / "lib/gbm"), LIBGL_DRIVERS_PATH=str(args.prefix / "lib"), MESA_LOADER_DRIVER_OVERRIDE="grate")
    processes = []
    logs = []

    def start(name: str, command: list[str], child_env: dict):
        log = (out / f"{name}.log").open("wb")
        logs.append(log)
        process = subprocess.Popen(command, env=child_env, stdout=log, stderr=subprocess.STDOUT, close_fds=True)
        processes.append(process)
        return process

    try:
        compositor = start("labwc", ["labwc", "-V", "-C", str(cfg)], env)
        wait_for(lambda: list(runtime.glob("wayland-*")) and any(p.is_socket() for p in runtime.glob("wayland-*")), processes)
        display = next(p.name for p in runtime.glob("wayland-*") if p.is_socket())
        client_env = env.copy()
        # Fixture and capture client use the system libraries. Only labwc gets
        # the candidate EGL loader, so this gate tests its composition path.
        for key in ("LD_LIBRARY_PATH", "GBM_BACKENDS_PATH", "LIBGL_DRIVERS_PATH", "MESA_LOADER_DRIVER_OVERRIDE"):
            client_env.pop(key, None)
        client_env["WAYLAND_DISPLAY"] = display
        start("fixture", [str(args.client)], client_env)
        wait_for(lambda: "FIXTURE_COMMITTED" in (out / "fixture.log").read_text(), processes)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        conf = out / "wayvnc.conf"
        conf.write_text(f"address=127.0.0.1\nport={port}\nenable_auth=false\n")
        start("wayvnc", ["wayvnc", "-d", "-R", "-f", "1", "-C", str(conf), "-S", str(runtime / "capture-control")], client_env)
        time.sleep(2)
        frames = []
        for attempt in range(4):
            wait_for(lambda: True, processes)
            width, height, pixels = capture(port)
            normalized = bytearray(pixels)
            normalized[3::4] = b"\xff" * (len(pixels) // 4)
            pixels = bytes(normalized)
            (out / f"capture-{attempt}.bgra").write_bytes(pixels)
            (out / f"capture-{attempt}.json").write_text(json.dumps({
                "width": width, "height": height,
                "blue_values": len(set(pixels[0::4])),
                "green_values": len(set(pixels[1::4])),
                "sha256": hashlib.sha256(pixels).hexdigest(),
            }, indent=2) + "\n")
            if nonblank(pixels):
                frames.append(pixels)
                if len(frames) == 2 and frames[-1] == frames[-2]:
                    break
                frames = frames[-1:]
            time.sleep(1)
        if len(frames) != 2 or frames[0] != frames[1]:
            raise RuntimeError("fixture did not produce two stable nonblank captures")
        (out / "frame.bgra").write_bytes(pixels)
        renderer = (out / "labwc.log").read_text()
        if mode == "grate":
            if "GL vendor: Grate" not in renderer or "GL renderer: Tegra" not in renderer:
                raise RuntimeError("missing Grate/Tegra renderer identity")
            maps = Path(f"/proc/{compositor.pid}/maps").read_text()
            if str(args.prefix / "lib/libgallium") not in maps:
                raise RuntimeError("candidate libgallium was not mapped")
            (out / "maps").write_text(maps)
        elif "creating pixman renderer" not in renderer.lower():
            raise RuntimeError("missing pixman control identity")
        result = compare(pixels, oracle(width, height))
        result.update(mode=mode, width=width, height=height, stable_frames=2, sha256=hashlib.sha256(pixels).hexdigest(), compositor_pid=compositor.pid)
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
    args = parser.parse_args()
    args.client = args.client.resolve(strict=True)
    args.prefix = args.prefix.resolve(strict=True)
    args.output = args.output.absolute()
    if os.geteuid() != 0 or os.uname().release != "7.0.1-postmarketos-grate":
        parser.error("run this hardware gate as root on the canonical SL101 kernel")
    if Path("/sys/block/mmcblk1/device/cid").read_text().strip() != CID:
        parser.error("wrong SD/device identity")
    gallium = args.prefix / "lib/libgallium-25.0.7.so"
    if hashlib.sha256(gallium.read_bytes()).hexdigest() != args.expected_gallium_sha256:
        parser.error("candidate hash mismatch")
    with open("/run/lock/sl101-nura-qualification.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        visible_pid = int(Path("/run/sl101-desktop.pid").read_text())
        visible_start = Path(f"/proc/{visible_pid}/stat").read_text().split()[21]
        args.output.mkdir()  # never overwrite an earlier run
        before = subprocess.check_output(["dmesg"], text=True)
        (args.output / "dmesg.before").write_text(before)
        summary = {"driver_sha256": args.expected_gallium_sha256, "visible_pid": visible_pid, "pass": False}
        try:
            control = run_mode("pixman", args, args.output)
            summary["pixman"] = control
            print(json.dumps(control), flush=True)
            if not control["pass"]:
                raise RuntimeError("CPU control fails the pixel oracle; GPU result cannot qualify")
            gpu = run_mode("grate", args, args.output)
            summary["grate"] = gpu
            print(json.dumps(gpu), flush=True)
            summary["pass"] = gpu["pass"]
        except Exception as error:
            summary["error"] = str(error)
        finally:
            after = subprocess.check_output(["dmesg"], text=True)
            (args.output / "dmesg.after").write_text(after)
            old_lines = before.splitlines()
            new_lines = after.splitlines()
            # Do not assume the ring buffer never wraps.
            delta = new_lines[len(old_lines):] if new_lines[:len(old_lines)] == old_lines else [line for line in new_lines if line not in set(old_lines)]
            faults = [line for line in delta if FAULT.search(line)]
            (args.output / "dmesg.faults").write_text("\n".join(faults))
            summary["kernel_faults"] = faults
            try:
                survival = Path(f"/proc/{visible_pid}/stat").read_text().split()[21] == visible_start
            except OSError:
                survival = False
            summary["visible_desktop_survived"] = survival
            summary["pass"] = summary["pass"] and survival and not faults
            (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary), flush=True)
        return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
