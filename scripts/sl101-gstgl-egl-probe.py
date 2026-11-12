#!/usr/bin/env python3
# scripts/sl101-gstgl-egl-probe.py
"""Fail-closed .106 GstGL/eglinfo EGL comparison; no video acceptance claim.

Run only as the unprivileged physical Sway user. The lock covers BOTH GPU
processes. No KMS, reboot, driver install, compositor stop, or CPU video sink.
Save artifacts in /tmp; upstream review can consume the JSON and both logs.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time

RUNTIME = Path("/run/sl101-desktop-user")
LOCK = RUNTIME / "sl101-gpu-video-e2e.lock"
PREFIX = Path("/opt/grate-mesa25-musl-prod70-20261109/lib")
SHAS = {
    "libEGL.so.1.0.0": "ed10793c3186acdd3ff808f13ea6fabc1dcf9daf4d83ae925df5eda3cebb554c",
    "libGLESv2.so.2.0.0": "9903d65b8cae3621262f225c981277da28d14a46f91a371f9699af62a1f31e61",
    "libgallium-25.0.7.so": "be30623c7e753122dc95470a0829802fe9371dbdc93a6a9e081f3159e6d2fa89",
}
FIXTURE = [
    "gst-launch-1.0", "-v", "videotestsrc", "num-buffers=3", "pattern=smpte",
    "!", "video/x-raw,format=I420,width=64,height=64,framerate=1/1",
    "!", "glupload", "!", "glcolorconvert", "!",
    "video/x-raw(memory:GLMemory),format=RGBA", "!",
    "glimagesink", "sync=false",
]
KEYS = ("LD_LIBRARY_PATH", "LIBGL_DRIVERS_PATH", "GBM_BACKENDS_PATH",
        "LD_PRELOAD")


class GateError(RuntimeError):
    pass


def parse_env(raw):
    return dict(item.split("=", 1) for item in
                (entry.decode("utf-8", "surrogateescape")
                 for entry in raw.split(b"\0") if b"=" in entry))


def valid_env(data):
    if any(data.get(key) != val for key, val in
           (("WLR_RENDERER", "gles2"),
            ("WLR_RENDERER_ALLOW_SOFTWARE", "0"),
            ("MESA_LOADER_DRIVER_OVERRIDE", "grate"))):
        raise GateError("Sway does not attest Grate-only GLES2")
    if data.get("LIBGL_DRIVERS_PATH") != str(PREFIX):
        raise GateError("Mesa prefix does not match compositor")
    if data.get("GBM_BACKENDS_PATH") != str(PREFIX / "gbm"):
        raise GateError("GBM path mismatch")
    if any(not data.get(key) or "\n" in data[key] for key in KEYS):
        raise GateError("missing or invalid Sway graphics environment")
    if str(PREFIX) not in data["LD_LIBRARY_PATH"].split(":"):
        raise GateError("Mesa prefix absent from LD_LIBRARY_PATH")
    if "/usr/local/lib/gr3d_serialize.so" not in data["LD_PRELOAD"].split():
        raise GateError("GR3D serialization interposer missing")
    if data.get("GALLIUM_DRIVER") or data.get("LIBGL_ALWAYS_SOFTWARE"):
        raise GateError("software override in compositor environment")
    return {k: data[k] for k in KEYS}


def preflight():
    if os.geteuid() == 0 or socket.gethostname() != "sl101-nura":
        raise GateError("not unprivileged .106 Nura")
    if os.uname().release != "7.0.1-postmarketos-grate-dmavde1":
        raise GateError("unqualified .106 kernel")
    for dev, value in (
        ("mmcblk1", "035344534c31323880ac79a543010300"),
        ("mmcblk0", "7001004d4d43333247448d402a656e00"),
    ):
        if Path("/sys/block", dev, "device/cid").read_text().strip().lower() != value:
            raise GateError("physical media identity mismatch")
    if RUNTIME.is_symlink() or RUNTIME.stat().st_uid != os.geteuid():
        raise GateError("untrusted compositor runtime directory")
    wayland = RUNTIME / "wayland-1"
    if not stat.S_ISSOCK(wayland.stat().st_mode) or wayland.stat().st_uid != os.geteuid():
        raise GateError("Wayland socket absent/untrusted")
    pids = subprocess.check_output(["pgrep", "-xo", "sl101-sway"], text=True).strip()
    if not pids.isdigit() or os.readlink("/proc/" + pids + "/exe") != "/usr/local/bin/sl101-sway":
        raise GateError("unrecognized Sway process")
    proc = Path("/proc") / pids
    if proc.stat().st_uid != os.geteuid():
        raise GateError("Sway UID mismatch")
    gfx = valid_env(parse_env((proc / "environ").read_bytes()))
    for lib, digest in SHAS.items():
        path = PREFIX / lib
        if not path.is_file() or path.is_symlink():
            raise GateError("unqualified library " + lib)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise GateError("library hash mismatch " + lib)
    for cmd in ("eglinfo", "gst-launch-1.0"):
        if not shutil.which(cmd):
            raise GateError("missing executable " + cmd)
    env = os.environ.copy()
    env.update(gfx)
    env.update(XDG_RUNTIME_DIR=str(RUNTIME), WAYLAND_DISPLAY="wayland-1",
               MESA_LOADER_DRIVER_OVERRIDE="grate", EGL_PLATFORM="wayland",
               GST_GL_API="gles2", GST_GL_PLATFORM="egl",
               GST_GL_WINDOW="wayland", GST_DEBUG_NO_COLOR="1",
               GST_DEBUG="*:2,gl*:6")
    for bad in ("LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER"):
        env.pop(bad, None)
    return env


def recorded_run(command, env, log, timeout=12):
    """Bounded GPU child; recorded *child* signal, maps, stderr and full output."""
    start = time.monotonic()
    maps = set()
    with log.open("wb") as fd:
        proc = subprocess.Popen(command, env=env, stdout=fd,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while proc.poll() is None and time.monotonic() - start < timeout:
                try:
                    mm = (Path("/proc") / str(proc.pid) / "maps").read_text()
                    maps.update(re.findall(r"/[^\s]+\.so(?:\.[\w.]+)?", mm))
                except (FileNotFoundError, PermissionError):
                    pass
                time.sleep(0.025)
            timed_out = proc.poll() is None
            if timed_out:
                proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    data = log.read_text(errors="replace")
    needed_egl = [str(PREFIX / n) for n in
                  ("libEGL.so.1.0.0", "libgallium-25.0.7.so")]
    needed_gles = str(PREFIX / "libGLESv2.so.2.0.0")
    system_gallium = any(re.search(r"/libgallium-(?!25\.0\.7)[^/]*\.so", x)
                          for x in maps)
    return {
        "argv": command, "rc": proc.returncode, "timeout": timed_out,
        "elapsed_s": round(time.monotonic() - start, 3),
        "mapped_pinned_egl_gallium": all(any(p in x for x in maps) for p in needed_egl),
        "mapped_private_gles2": any(needed_gles in x for x in maps),
        "mixed_system_gallium": system_gallium,
        "mapped_libs": sorted(x for x in maps if
                             any(s in x for s in ("EGL", "GLES", "gallium", "dri", "wayland", "libGL.so"))),
        "egl_error": "failed to create dri2 screen" in data,
        "glmemory_caps": bool(re.search(r"caps\s*=\s*video/x-raw\(memory:GLMemory\)", data)),
        "log": str(log),
    }


def run_suite(env, out, c_binary=None, native_only=False):
    rows = {}
    cases = [] if native_only else [
        ("eglinfo", ["eglinfo", "-p", "wayland", "-a", "gles", "-B"]),
        ("gst_fixture", FIXTURE)]
    if c_binary is not None:
        if not c_binary.is_file() or not os.access(c_binary, os.X_OK):
            raise GateError("requested native EGL reference executable missing")
        cases += [
            ("native", [str(c_binary), "native"]),
            ("platform", [str(c_binary), "platform"]),
            ("platform_glx_load", [str(c_binary), "platform-glx"]),
        ]
    for name, argv in cases:
        rows[name] = recorded_run(argv, env, out / (name + ".log"))
    report = {
        "schema": "sl101.grate-gstgl-egl-diagnostic/v1",
        "hardware": ".106 Alpine musl, kernel dmavde1",
        "mesa_sha256": SHAS,
        "cases": rows,
        "gpu_video_accepted": False,
        "mixed_gallium_risk": any(v["mixed_system_gallium"] for v in rows.values()),
        "limits": ["GstGL fixture has no VDE", "No on-screen pixel oracle",
                   "No frame timing, DMA plane pitch or A/V qualification"],
    }
    (out / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-fixture", action="store_true",
                   help="run bounded GPU tests on verified .106 (default: dry-run)")
    p.add_argument("--out", type=Path)
    p.add_argument("--c-binary", type=Path)
    p.add_argument("--native-only", action="store_true",
                   help="run only the C EGL discriminants, still behind device lock")
    args = p.parse_args(argv)
    if args.native_only and not args.c_binary:
        p.error("--native-only requires --c-binary")
    if not args.run_fixture:
        print(json.dumps({"fixture": FIXTURE, "device_touched": False,
                          "accepted": False}, indent=2))
        return 0
    try:
        # Existing lock only; never create a lock that might alias another seat.
        fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GateError("another GPU lane owns the device lock") from exc
        try:
            env = preflight()
            if args.out:
                if args.out.exists():
                    raise GateError("evidence directory exists; never overwrite")
                args.out.mkdir(parents=True, mode=0o700)
                out = args.out
                report = run_suite(env, out, args.c_binary, args.native_only)
            else:
                with tempfile.TemporaryDirectory(prefix="sl101-gstgl-egl-") as directory:
                    report = run_suite(env, Path(directory), args.c_binary, args.native_only)
            print(json.dumps(report, indent=2))
            if args.native_only:
                ok = all(r["rc"] == 0 for r in report["cases"].values())
            else:
                gst = report["cases"]["gst_fixture"]
                ok = (gst["rc"] == 0 and gst["glmemory_caps"] and
                      gst["mapped_pinned_egl_gallium"] and
                      not gst["mixed_system_gallium"])
            return 0 if ok else 3
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except (OSError, GateError, subprocess.SubprocessError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
