#!/usr/bin/env python3
"""SL101 physical CMA A/B benchmark on the VDE no-kernel-mapping allocation path.

Runs in a PRIVATE tracefs instance on the target tablet, without KMS or
global function tracing. Native CMA tracepoints measure CMA core allocation times, while the matched
full VDE pipelines measure end-to-end latency (which includes the optional
lowmem remap). Trace state is restored even if decoding or parsing fails.
CMA tracepoints alone do not time the subsequent remap separately.

The experiment's two kernel builds differ only by the CMA remap patch and
CONFIG_LOCALVERSION; see scripts/sl101-dmavde-ab-verify.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import socket
import statistics
import subprocess
import sys
import time

KERNELS = {
    "cma": {
        "release": "7.0.1-postmarketos-grate-dmavde1",
        "vde_sha": "625bc023d0df8903f6387b9ff1c7963ed4ebb79eb3a13c8c1884b6ef4fd7b892",
    },
    "minus-cma": {
        "release": "7.0.1-postmarketos-grate-dmavde1-minus-cma",
        "vde_sha": "be44097b3fe220fa8083abb7cf7dbbcea396ce28d41e8c15199617b15aecc24b",
    },
}
SD_CID = "035344534c31323880ac79a543010300"
EMMC_CID = "7001004d4d43333247448d402a656e00"
BASE = Path("/root/hwrun/qa-dmavde1")
CLIP = BASE / "vde-qual/short.mp4"
TRACE = Path("/sys/kernel/tracing")
INSTANCE = TRACE / "instances/sl101_cma_ab_bench"
CMA_EVENTS = ("cma_alloc_start", "cma_alloc_finish", "cma_release")
RE = re.compile(
    r"^\s*(?P<comm>.+?)-(?P<pid>\d+)\s+\[(?P<cpu>\d+)\]\s+\S+\s+"
    r"(?P<timestamp>\d+\.\d+): (?P<kind>"
    r"cma_alloc_start|cma_alloc_finish|cma_release): (?P<details>.*)$"
)
SIZE_RE = re.compile(r"\brequest_count=(\d+)\b")
ERR_RE = re.compile(r"\berrorno=(-?\d+)\b")
OVERFLOW = re.compile(r"entries-in-buffer/entries-written:\s*(\d+)/(\d+)")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path: Path) -> str:
    return path.read_text().strip()


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lower, upper = int(pos), min(len(ordered) - 1, int(pos) + 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower), 3)


def descriptive(values: list[float]) -> dict:
    return {
        "samples": len(values),
        "min": round(min(values), 3) if values else None,
        "p50": pct(values, .5),
        "p95": pct(values, .95),
        "p99": pct(values, .99),
        "max": round(max(values), 3) if values else None,
        "mean": round(statistics.fmean(values), 3) if values else None,
    }


def parse_trace(data: str) -> dict:
    head = OVERFLOW.search(data)
    if not head:
        raise ValueError("no tracing buffer count header")
    in_buffer, written = map(int, head.groups())
    if in_buffer != written:
        raise ValueError(f"trace-buffer loss {written - in_buffer} entries")
    active = {}
    allocations = []
    counters = {}
    bad = []
    for line in data.splitlines():
        m = RE.match(line)
        if m is None:
            continue
        kind, tid, t = m["kind"], int(m["pid"]), float(m["timestamp"])
        counters[kind] = counters.get(kind, 0) + 1
        if kind == "cma_alloc_start":
            if tid in active:
                bad.append(f"nested CMA start on tid {tid}")
            size = SIZE_RE.search(m["details"])
            active[tid] = {"core_start": t,
                           "pages": int(size.group(1)) if size else None}
        elif kind == "cma_alloc_finish":
            if tid not in active:
                bad.append(f"orphan CMA finish tid {tid}")
                continue
            slot = active.pop(tid)
            if t < slot["core_start"]:
                bad.append(f"negative CMA duration on tid {tid}")
                continue
            err = ERR_RE.search(m["details"])
            slot["errorno"] = int(err.group(1)) if err else None
            slot["core_us"] = round((t - slot["core_start"]) * 1e6, 3)
            allocations.append(slot)
    if active:
        bad.append(f"{len(active)} unmatched CMA starts")
    if bad:
        raise ValueError("unmatched CMA trace: " + "; ".join(bad[:8]))
    if not allocations:
        raise ValueError("CMA trace has no core allocations")
    by_pages = {}
    for row in allocations:
        by_pages.setdefault(str(row["pages"]), []).append(row["core_us"])
    return {
        "trace_entries": written,
        "events": counters,
        "matched_core_allocations": len(allocations),
        "core_cma_us": descriptive([r["core_us"] for r in allocations]),
        "by_request_pages": {k: descriptive(v) for k, v in sorted(by_pages.items())},
        "errors": sum(r.get("errorno") not in (None, 0) for r in allocations),
        "limitation": ("CMA tracepoints stop before the patched direct-map remap; "
                       "only pipeline_wall_ms includes remap time"),
    }


def cma_vmstat() -> dict:
    wanted = {"cma_alloc_success", "cma_alloc_fail", "cma_release_success",
              "nr_free_cma"}
    out = {}
    for line in Path("/proc/vmstat").read_text().splitlines():
        name, val = line.split()
        if name in wanted:
            out[name] = int(val)
    return out


def health() -> dict:
    cpu = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    ac = Path("/sys/class/power_supply/ac-adapter-detect/online")
    bat = Path("/sys/class/power_supply/sbs-5-000b/capacity")
    return {
        "boot_id": read(Path("/proc/sys/kernel/random/boot_id")),
        "cpu_khz": int(read(cpu)) if cpu.is_file() else None,
        "temperature_mC": int(read(thermal)) if thermal.is_file() else None,
        "ac": read(ac) if ac.is_file() else None,
        "battery_percent": int(read(bat)) if bat.is_file() else None,
        "vmstat": cma_vmstat(),
    }


def put(path: Path, value: str) -> None:
    path.write_text(str(value) + "\n")


def configure_trace() -> None:
    if INSTANCE.exists():
        raise RuntimeError("private trace instance already exists; refusing to reuse")
    INSTANCE.mkdir()
    put(INSTANCE / "tracing_on", 0)
    put(INSTANCE / "buffer_size_kb", 4096)
    put(INSTANCE / "trace_clock", "mono")
    for name in CMA_EVENTS:
        put(INSTANCE / f"events/cma/{name}/enable", 1)


def cleanup_trace() -> list[str]:
    errors = []
    if INSTANCE.exists():
        try:
            put(INSTANCE / "tracing_on", 0)
            for name in CMA_EVENTS:
                put(INSTANCE / f"events/cma/{name}/enable", 0)
            INSTANCE.rmdir()
        except OSError as exc:
            errors.append("instance-cleanup: " + str(exc))
    return errors


def run_pipeline(path: Path, timeout: int = 30) -> tuple[float, float, float]:
    command = [
        "gst-launch-1.0", "-q",
        "filesrc", "location=" + str(path), "!",
        "qtdemux", "!", "h264parse", "!", "v4l2slh264dec",
        "!", "fakesink", "sync=false",
    ]
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    tick = time.perf_counter_ns()
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    wall_ms = (time.perf_counter_ns() - tick) / 1e6
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    if result.returncode:
        raise RuntimeError(f"VDE pipeline rc={result.returncode}: "
                           + result.stderr.decode(errors="replace")[-1500:])
    return (round(wall_ms, 3),
            round((after.ru_utime - before.ru_utime) * 1000, 3),
            round((after.ru_stime - before.ru_stime) * 1000, 3))


def run(args: argparse.Namespace) -> dict:
    config = KERNELS[args.variant]
    if os.geteuid():
        raise RuntimeError("requires root for private tracefs instance")
    if socket.gethostname() != "sl101-nura":
        raise RuntimeError("wrong physical tablet hostname")
    uname = os.uname().release
    if uname != config["release"]:
        raise RuntimeError("wrong ABI/release, got " + uname)
    if read(Path("/sys/block/mmcblk1/device/cid")) != SD_CID:
        raise RuntimeError("wrong SD physical CID")
    if read(Path("/sys/block/mmcblk0/device/cid")) != EMMC_CID:
        raise RuntimeError("wrong eMMC physical CID")
    if read(Path("/sys/module/tegra_vde/parameters/cached_capture")) != "N":
        raise RuntimeError("VDE cached_capture not at baseline N")
    if read(Path("/sys/class/power_supply/ac-adapter-detect/online")) != "1":
        raise RuntimeError("AC absent; benchmark invalid")
    module = Path(f"/lib/modules/{uname}/kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst")
    if sha(module) != config["vde_sha"]:
        raise RuntimeError("wrong VDE module binary for running kernel")
    if not CLIP.is_file():
        raise RuntimeError("pinned 96-frame H264 clip missing")
    if args.repeats < 5 or args.repeats > 400:
        raise ValueError("5..400 repeats")
    dest = Path(args.output)
    if dest.exists():
        raise FileExistsError("benchmark output exists; refusing overwrite")
    if not dest.parent.is_dir():
        raise FileNotFoundError("output parent must be created in advance")
    sway_proc = subprocess.run(["pgrep", "-xo", "sl101-sway"], capture_output=True, text=True)
    if sway_proc.returncode:
        raise RuntimeError("Sway supervisor not running; refuse")
    sway_pid = sway_proc.stdout.strip()
    vm_before = health()
    # Prewarm dynamic libraries/firmware in the same mode, not included in measurements.
    for _ in range(3):
        run_pipeline(CLIP)
    timings = []
    error = None
    configured = False
    trace_text = ""
    try:
        configure_trace()
        configured = True
        put(INSTANCE / "tracing_on", 1)
        for i in range(args.repeats):
            timing = run_pipeline(CLIP)
            timings.append(timing)
            if (i + 1) % 15 == 0:
                print(f"BENCH_PROGRESS variant={args.variant} {i+1}/{args.repeats}", flush=True)
        put(INSTANCE / "tracing_on", 0)
        trace_text = (INSTANCE / "trace").read_text()
    except Exception as exc:
        error = str(exc)
    finally:
        cleanup_errors = cleanup_trace()
    if cleanup_errors:
        raise RuntimeError("kernel trace cleanup incomplete: " + "; ".join(cleanup_errors))
    if error:
        raise RuntimeError(error)
    trace = parse_trace(trace_text)
    vm_after = health()
    if vm_after["boot_id"] != vm_before["boot_id"]:
        raise RuntimeError("boot ID changed during benchmark")
    after_sway = subprocess.run(["pgrep", "-xo", "sl101-sway"], capture_output=True, text=True)
    if after_sway.stdout.strip() != sway_pid:
        raise RuntimeError("Sway changed PID during benchmark")
    deltas = {k: v - vm_before["vmstat"].get(k, 0) for k, v in vm_after["vmstat"].items()}
    if deltas.get("cma_alloc_fail", 0) or trace["errors"]:
        raise RuntimeError("kernel CMA allocation failed")
    if trace["matched_core_allocations"] < args.repeats * 10:
        raise RuntimeError("too few CMA core samples; instrumentation incomplete")
    result = {
        "schema": "sl101-cma-ab-hardware-v1",
        "variant": args.variant,
        "release": uname,
        "boot_id": vm_before["boot_id"],
        "vde_module_sha256": config["vde_sha"],
        "clip_sha256": sha(CLIP),
        "repeats": args.repeats,
        "prewarm_runs": 3,
        "sway_pid": sway_pid,
        "started": vm_before,
        "finished": vm_after,
        "cma_vmstat_delta": deltas,
        "pipeline_wall_ms": descriptive([a[0] for a in timings]),
        "pipeline_cpu_user_ms": descriptive([a[1] for a in timings]),
        "pipeline_cpu_system_ms": descriptive([a[2] for a in timings]),
        "trace": trace,
        "trace_sha256": hashlib.sha256(trace_text.encode()).hexdigest(),
        "measurement_caveats": [
            "private tracepoints have small overhead, same tracepoints/clip used in both kernels",
            "core_cma_us excludes the CMA patch remap; pipeline_wall_ms includes it",
            "end-to-end pipeline timings include userspace startup, decoding and CMA allocation",
            "A/B must be balanced against temperature, CPU frequency, and load drift",
        ],
    }
    dest.mkdir(mode=0o700)
    (dest / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (dest / "trace.txt").write_text(trace_text)
    (dest / "pipelines.json").write_text(json.dumps(
        [{"wall_ms": a, "user_ms": b, "system_ms": c} for a, b, c in timings],
        indent=2) + "\n")
    print(json.dumps({
        "result": str(dest / "result.json"),
        "variant": args.variant,
        "repeats": args.repeats,
        "core_cma_us": trace["core_cma_us"],
        "pipeline_ms": result["pipeline_wall_ms"],
        "vmstat_delta": deltas,
    }, indent=2, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(KERNELS), required=True)
    parser.add_argument("--repeats", type=int, default=60)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print("CMA_HARDWARE_BENCH_FAIL:", exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
