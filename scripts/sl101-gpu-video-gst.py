#!/usr/bin/env python3
# scripts/sl101-gpu-video-gst.py
"""Strict Grate GLES2 video experiment: VDE H.264 -> GLMemory -> GL Sway.

This is NOT a verified player until device pixel and frame-progress gates pass.
Never changes DRM master, stops Sway, modifies the kernel, or picks a CPU sink.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

KERNEL_RE = re.compile(r"^7\.0\.1-postmarketos-grate-dmavde1(?:-minus-cma)?$")
IDENTITY_106 = ("sl101-nura", "035344534c31323880ac79a543010300",
                "7001004d4d43333247448d402a656e00")
REQUIRED = ("gst-launch-1.0", "gst-inspect-1.0", "ffprobe")
ELEMENTS = ("filesrc", "qtdemux", "queue", "h264parse", "v4l2slh264dec",
            "glupload", "glcolorconvert", "glimagesink")
GRAPHICS_ENV_KEYS = ("LD_LIBRARY_PATH", "LIBGL_DRIVERS_PATH",
                     "GBM_BACKENDS_PATH", "LD_PRELOAD")
# The *observed* .106 musl Grate Mesa prefix (not a guessed content-hash name).
GRATE_PREFIX_106 = "/opt/grate-mesa25-musl-prod70-20261109/lib"
GRATE_ELF_SHA256 = {
    "libgallium-25.0.7.so": "be30623c7e753122dc95470a0829802fe9371dbdc93a6a9e081f3159e6d2fa89",
    "libEGL.so.1.0.0": "ed10793c3186acdd3ff808f13ea6fabc1dcf9daf4d83ae925df5eda3cebb554c",
    "libGLESv2.so.2.0.0": "9903d65b8cae3621262f225c981277da28d14a46f91a371f9699af62a1f31e61",
}


class GateError(Exception):
    pass


def video_profile(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,profile,pix_fmt,field_order,width,height",
         "-of", "json", str(path)], capture_output=True, text=True, timeout=15,
        check=False)
    if proc.returncode:
        raise GateError("ffprobe could not inspect input")
    try:
        stream = json.loads(proc.stdout)["streams"][0]
    except (ValueError, IndexError, KeyError, TypeError):
        raise GateError("no verifiable video stream")
    if stream.get("codec_name") != "h264":
        raise GateError("only VDE H.264 is allowed")
    if stream.get("profile") not in ("Baseline", "Constrained Baseline", "Main"):
        raise GateError("unsupported Tegra20 H.264 profile")
    if stream.get("pix_fmt") != "yuv420p":
        raise GateError("8-bit 4:2:0 is required")
    if stream.get("field_order") not in (None, "", "unknown", "progressive"):
        raise GateError("interlaced video unsupported")
    if not all(isinstance(stream.get(k), int) and stream[k] > 0 for k in ("width", "height")):
        raise GateError("invalid video dimensions")
    return stream


def pipeline_args(path, memory, audio_sink):
    """Explicit typed GStreamer graph; there are no autoplugged video sinks."""
    if memory not in ("dmabuf", "system"):
        raise GateError("memory must be dmabuf or system")
    if audio_sink not in ("none", "pulsesink", "alsasink"):
        raise GateError("unsupported audio sink")
    caps = ("video/x-raw(memory:DMABuf),format=DMA_DRM" if memory == "dmabuf"
            else "video/x-raw,format=I420")
    argv = [
        "gst-launch-1.0", "-f", "-e", "-m", "-v", "filesrc", "location=" + str(path),
        "!", "qtdemux", "name=demux",
        "demux.video_0", "!", "queue", "max-size-buffers=3",
        "!", "h264parse", "!", "v4l2slh264dec",
        "!", caps, "!", "glupload",
        "!", "video/x-raw(memory:GLMemory)",
        "!", "glcolorconvert",
        "!", "video/x-raw(memory:GLMemory),format=RGBA",
        "!", "glimagesink", "sync=true", "force-aspect-ratio=true"
    ]
    if audio_sink != "none":
        argv += [
            "demux.audio_0", "!", "queue", "!", "aacparse", "!",
            "avdec_aac", "!", "audioconvert", "!", "audioresample",
            "!", audio_sink, "sync=true"
        ]
    return argv


def verify_identity(host, kernel, sd_cid, emmc_cid):
    if not KERNEL_RE.fullmatch(kernel):
        raise GateError("not a pinned dmavde1 kernel; requalify exact kernel")
    if (host, sd_cid.lower(), emmc_cid.lower()) != IDENTITY_106:
        raise GateError("physical .106 hostname/SD/eMMC identity mismatch; "
                        "Debian .100 requires separate CID qualification")


def validate_compositor_env(values):
    """Pin the player to the ACTIVE compositor's exact Grate stack.

    A software/Pixman Sway session is NEVER accepted even if a separate
    GLES context might be created inside the video player's process.
    """
    if (values.get("WLR_RENDERER") != "gles2"
            or values.get("WLR_RENDERER_ALLOW_SOFTWARE") != "0"
            or values.get("MESA_LOADER_DRIVER_OVERRIDE") != "grate"):
        raise GateError("active Sway not strictly Grate GLES2 with software forbidden")
    if values.get("LIBGL_ALWAYS_SOFTWARE") or values.get("GALLIUM_DRIVER"):
        raise GateError("active compositor uses or exports a software rendering override")
    for key in GRAPHICS_ENV_KEYS:
        if not values.get(key) or any(c in values[key] for c in ("\x00", "\n", "\r")):
            raise GateError("active compositor missing safe pinned " + key)
    driver = values["LIBGL_DRIVERS_PATH"]
    if driver != GRATE_PREFIX_106:
        raise GateError("active compositor does not use the independently observed .106 Grate prefix")
    if values["GBM_BACKENDS_PATH"] != driver + "/gbm":
        raise GateError("GBM backend differs from compositor's pinned Mesa")
    ld_dirs = values["LD_LIBRARY_PATH"].split(":")
    if (driver not in ld_dirs or
            not any(re.fullmatch(r"/usr/local/lib/sl101-libdrm-import-lists-[a-f0-9]{16}",
                                 x) for x in ld_dirs)):
        raise GateError("compositor is missing pinned Mesa/libdrm link paths")
    if "/usr/local/lib/gr3d_serialize.so" not in values["LD_PRELOAD"].split():
        raise GateError("cross-process GR3D serialization interposer is missing")
    return {key: values[key] for key in GRAPHICS_ENV_KEYS}


def verify_grate_libraries(prefix):
    """Require the EXACT live .106 Grate runtime, not merely a promising name."""
    if prefix != GRATE_PREFIX_106:
        raise GateError("unqualified Grate library directory")
    for name, expected_sha in GRATE_ELF_SHA256.items():
        path = Path(prefix) / name
        if not path.is_file() or path.is_symlink():
            raise GateError("missing pinned Grate ELF: " + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected_sha:
            raise GateError("installed Grate ELF SHA256 mismatch: " + name)


def parse_proc_environment(raw):
    """Linux /proc/PID/environ uses NUL-delimited KEY=VALUE pairs."""
    entries = (item.split(b"=", 1) for item in raw.split(b"\x00") if b"=" in item)
    return {key.decode("utf-8", "surrogateescape"):
            value.decode("utf-8", "surrogateescape") for key, value in entries}


def compositor_gpu_environment(pid):
    """Read the observed renderer of the owned, trusted Sway process."""
    try:
        proc = Path("/proc") / str(pid)
        if proc.stat().st_uid != os.geteuid():
            raise GateError("Sway process belongs to another UID")
        if os.readlink(proc / "exe") != "/usr/local/bin/sl101-sway":
            raise GateError("unrecognized desktop Sway executable")
        raw = (proc / "environ").read_bytes()
        values = parse_proc_environment(raw)
        graphics = validate_compositor_env(values)
        verify_grate_libraries(graphics["LIBGL_DRIVERS_PATH"])
        return graphics
    except (OSError, ValueError) as exc:
        raise GateError("cannot attest running GPU Sway environment") from exc


def sway_pid():
    for name in ("sl101-sway", "sway"):
        check = subprocess.run(["pgrep", "-xo", name], capture_output=True, text=True,
                               timeout=3)
        if check.returncode == 0 and check.stdout.strip().isdigit():
            return int(check.stdout.strip())
    raise GateError("Sway is not running")


def preflight(path, audio_sink):
    try:
        sd_cid = Path("/sys/block/mmcblk1/device/cid").read_text().strip()
        emmc_cid = Path("/sys/block/mmcblk0/device/cid").read_text().strip()
    except OSError:
        raise GateError("required physical MMC identity unavailable")
    verify_identity(socket.gethostname(), os.uname().release, sd_cid, emmc_cid)
    if os.geteuid() == 0:
        raise GateError("run unprivileged as the active Sway user")
    if not Path("/dev/video0").exists() or not Path("/dev/dri/card0").exists():
        raise GateError("VDE or DRM node missing")
    # SSH/pam can set a different runtime dir than the *existing* Sway seat.
    # This launcher targets only the verified .106 system desktop runtime.
    runtime = "/run/sl101-desktop-user"
    root = Path(runtime)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise GateError("invalid Wayland runtime directory")
    if root.stat().st_uid != os.geteuid() or (root.stat().st_mode & 0o077):
        raise GateError("runtime directory must be private and owned by caller")
    display = os.environ.get("WAYLAND_DISPLAY")
    if not display:
        display = next((v for v in ("wayland-1", "wayland-0", "wayland-2")
                        if (root / v).is_socket()), None)
    if not display or "/" in display or display in (".", ".."):
        raise GateError("no safe Sway Wayland display name")
    sock = root / display
    if not sock.is_socket() or sock.stat().st_uid != os.geteuid():
        raise GateError("untrusted Wayland socket")
    pinned_graphics = compositor_gpu_environment(sway_pid())
    for cmd in REQUIRED:
        if not shutil.which(cmd):
            raise GateError("missing " + cmd)
    extras = () if audio_sink == "none" else ("aacparse", "avdec_aac",
                                               "audioconvert", "audioresample", audio_sink)
    for element in (*ELEMENTS, *extras):
        ok = subprocess.run(["gst-inspect-1.0", "--exists", element],
                            capture_output=True, timeout=6)
        if ok.returncode:
            raise GateError("missing GStreamer element: " + element)
    if not path.is_file() or not os.access(path, os.R_OK):
        raise GateError("unreadable input")
    video_profile(path)
    return runtime, display, pinned_graphics


def gpu_environment(runtime, display, pinned_graphics=None):
    env = os.environ.copy()
    for var in ("LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER"):
        if env.get(var):
            raise GateError("software Mesa environment is forbidden: " + var)
    if env.get("MESA_LOADER_DRIVER_OVERRIDE", "grate") != "grate":
        raise GateError("Mesa override is not grate")
    if env.get("GST_GL_API", "gles2") != "gles2":
        raise GateError("Gst GL must use GLES2")
    if env.get("GST_GL_PLATFORM", "egl") != "egl":
        raise GateError("Gst GL must use EGL")
    if env.get("GST_GL_WINDOW", "wayland") != "wayland":
        raise GateError("Gst GL must use Wayland")
    if pinned_graphics is not None:
        env.update(pinned_graphics)
    env.update(XDG_RUNTIME_DIR=runtime, WAYLAND_DISPLAY=display,
               MESA_LOADER_DRIVER_OVERRIDE="grate", GST_GL_API="gles2",
               GST_GL_PLATFORM="egl", GST_GL_WINDOW="wayland",
               GST_DEBUG_NO_COLOR="1", GST_DEBUG="*:2,gl*:6")
    # Gst cap negotiation is also recorded by -v. Never set LIBGL_ALWAYS_SOFTWARE.
    return env


def gpu_maps(pid, prefix):
    """A Grate process maps a matched EGL + GLES + Gallium ABI, not grate_dri.so."""
    try:
        maps = Path("/proc/%d/maps" % pid).read_text(errors="replace")
    except (FileNotFoundError, PermissionError):
        return False, False
    reject = bool(re.search(r"/(?:swrast|kms_swrast|softpipe|llvmpipe)_dri\.so\b", maps))
    required = ("libgallium-25.0.7.so", "libEGL.so.1.0.0", "libGLESv2.so.2.0.0")
    matched = all(str(Path(prefix) / name) in maps for name in required)
    return matched, reject


def run_qualified(argv, env, seconds, evidence_dir):
    evidence = Path(evidence_dir) if evidence_dir else None
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sl101-gpu-video-") as tmp:
        logfile = (evidence / "gst.log") if evidence else (Path(tmp) / "gst.log")
        with logfile.open("wb") as log:
            child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                     env=env, start_new_session=True)
            driver_seen = False
            rejected = False
            deadline = time.monotonic() + seconds
            timed_out = False
            try:
                while child.poll() is None and time.monotonic() < deadline:
                    a, b = gpu_maps(child.pid, env["LIBGL_DRIVERS_PATH"])
                    driver_seen |= a
                    rejected |= b
                    if rejected:
                        break
                    time.sleep(0.1)
                if child.poll() is None:
                    timed_out = time.monotonic() >= deadline
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=3)
            except KeyboardInterrupt:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=4)
                raise GateError("operator interrupted; only this player was terminated")
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        output = logfile.read_text(errors="replace")
        # Pad caps, not a static element template, must show GLMemory.
        gl_caps = bool(re.search(r"caps\s*=\s*video/x-raw\(memory:GLMemory\)", output))
        soft = bool(re.search(r"(?i)(?:OpenGL renderer|GL_RENDERER)[^\n]*(?:llvmpipe|softpipe|swrast)", output))
        receipt = {
            "exit_code": child.returncode, "timeout": timed_out,
            "pinned_grate_egl_gles_gallium_mapped": driver_seen, "software_dri_mapped": rejected,
            "software_gl_renderer": soft, "negotiated_glmemory_caps": gl_caps,
            "success": child.returncode == 0 and not timed_out and driver_seen
                       and not rejected and not soft and gl_caps,
            "limitations": "Does not prove rendered pixel correctness, FPS or zero-copy import"
        }
        if evidence:
            (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
        if not receipt["success"]:
            raise GateError("GPU qualification failed; inspect Gst log (no CPU fallback)")
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--mode", choices=("sway", "kms"), default="sway")
    parser.add_argument("--memory", choices=("dmabuf", "system"), default="dmabuf")
    parser.add_argument("--audio-sink", choices=("none", "pulsesink", "alsasink"), default="none")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--evidence-dir")
    parser.add_argument("--dry-run", action="store_true")
    a = parser.parse_args(argv)
    try:
        if a.mode != "sway":
            raise GateError("direct KMS Grate EGL/GLES renderer not qualified; "
                            "kmssink scans out VDE buffers but does NOT GPU-rasterize video")
        if not 1 <= a.seconds <= 3600:
            raise GateError("seconds must be 1..3600")
        cmd = pipeline_args(a.file, a.memory, a.audio_sink)
        if a.dry_run:
            print(json.dumps({"mode": a.mode, "memory": a.memory,
                              "render": "Grate EGL GLES2", "decode": "Tegra VDE",
                              "command_argv": cmd, "device_qualified": False}, indent=2))
            return 0
        runtime, display, pinned_graphics = preflight(a.file, a.audio_sink)
        env = gpu_environment(runtime, display, pinned_graphics)
        return run_qualified(cmd, env, a.seconds, a.evidence_dir)
    except (GateError, OSError, subprocess.TimeoutExpired) as exc:
        print("sl101-gpu-video: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
