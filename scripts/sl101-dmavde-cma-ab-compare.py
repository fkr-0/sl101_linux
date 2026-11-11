#!/usr/bin/env python3
"""Compare SL101 CMA vs minus-CMA real hardware using an A-B-A sequence.

The actual target kernel source trees differ only by CMA plus
CONFIG_LOCALVERSION, verified separately by sl101-dmavde-ab-verify.py.

An A-B-A result is required to check thermal/time drift before a promotion
decision. All phase inputs must be complete, unique boot IDs, same video
clip, same VDE module feature baseline and >=30 decoding repetitions.
This gate judges performance only, NOT boot safety or GPU pixel accuracy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

REL = {
    "cma": "7.0.1-postmarketos-grate-dmavde1",
    "minus-cma": "7.0.1-postmarketos-grate-dmavde1-minus-cma",
}
SCHEMA = "sl101-cma-ab-hardware-v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_phase(data: dict, variant: str) -> None:
    require(data.get("schema") == SCHEMA, "invalid benchmark schema")
    require(data.get("variant") == variant, "variant mismatch")
    require(data.get("release") == REL[variant], "kernel ABI mismatch")
    # Earlier AC-only result files had no power_profile field. Explicit
    # standalone battery diagnostics must never qualify for matched A-B-A.
    require(data.get("power_profile", "ac") == "ac",
            "battery diagnostic is not eligible for AC-only A-B-A comparison")
    require(data.get("repeats", 0) >= 30, "insufficient pipeline samples")
    require(data["trace"]["matched_core_allocations"] >= data["repeats"] * 10,
            "incomplete CMA trace samples")
    require(data["trace"]["errors"] == 0, "trace reported CMA allocation errors")
    require(data["cma_vmstat_delta"].get("cma_alloc_fail", -1) == 0,
            "kernel CMA allocation failures")
    for phase in ("started", "finished"):
        h = data[phase]
        require(h.get("ac") == "1", "AC power missing in " + phase)
        require(h.get("battery_percent", 0) >= 60,
                "battery below 60% during benchmark")
        require(h.get("boot_id") == data["boot_id"], "boot ID changed midphase")
        require(h.get("cpu_khz", 0) >= 800000,
                "CPU clock below 800MHz: throttling likely")
        require(h.get("temperature_mC") is not None,
                "temperature observation unavailable")
    for stat in (data["pipeline_wall_ms"], data["trace"]["core_cma_us"]):
        require(stat["samples"] >= data["repeats"],
                "statistical samples incomplete")
        for q in ("p50", "p95", "p99"):
            require(stat[q] is not None and stat[q] > 0,
                    "invalid latency stat: " + q)


def compare(a1: dict, b: dict, a2: dict) -> dict:
    for phase, variant in [(a1, "cma"), (b, "minus-cma"), (a2, "cma")]:
        validate_phase(phase, variant)
    require(len({a1["boot_id"], b["boot_id"], a2["boot_id"]}) == 3,
            "A-B-A sequence requires three distinct verified boots")
    require(len({a1["clip_sha256"], b["clip_sha256"], a2["clip_sha256"]}) == 1,
            "different benchmark H.264 clips")
    require(a1["vde_module_sha256"] == a2["vde_module_sha256"],
            "A1/A2 compiled module binary mismatch")
    require(b["vde_module_sha256"] != a1["vde_module_sha256"],
            "benchmark modules have wrong ABI/provenance")

    phases = [a1, b, a2]
    temps = [p[x]["temperature_mC"] for p in phases for x in ("started", "finished")]
    require(max(temps) - min(temps) <= 6000,
            "thermal drift > 6C: inconclusive comparison")
    a1wall = a1["pipeline_wall_ms"]
    bwall = b["pipeline_wall_ms"]
    a2wall = a2["pipeline_wall_ms"]
    drift = abs(a1wall["p50"] - a2wall["p50"]) / statistics.mean(
        [a1wall["p50"], a2wall["p50"]])
    require(drift <= .08, "A1/A2 pipeline drift >8%: inconclusive comparison")

    deltas = {}
    for metric, key in (
        ("pipeline_wall_ms", "pipeline_wall_ms"),
        ("cpu_user_ms", "pipeline_cpu_user_ms"),
        ("cpu_system_ms", "pipeline_cpu_system_ms"),
        ("underlying_cma_alloc_us", "trace/core_cma_us"),
    ):
        def stat(data: dict) -> dict:
            if key == "trace/core_cma_us":
                return data["trace"]["core_cma_us"]
            return data[key]
        da, db, dc = (stat(p) for p in phases)
        deltas[metric] = {
            quant: {
                "a1": da[quant],
                "no_cma": db[quant],
                "a2": dc[quant],
                "cma_mean": round(statistics.mean((da[quant], dc[quant])), 3),
                "cma_over_no_cma_ratio": round(
                    statistics.mean((da[quant], dc[quant])) / db[quant], 4),
            }
            for quant in ("p50", "p95", "p99")
        }

    # Fail closed on unexplained high variability. The CMA trace measures
    # core page allocation ONLY; it cannot isolate the remap's instruction
    # cost. End-to-end time is therefore the promotion-critical signal.
    core_ratio = deltas["underlying_cma_alloc_us"]["p50"]["cma_over_no_cma_ratio"]
    require(.70 <= core_ratio <= 1.30,
            "core CMA allocator shift >30%: potential fragmentation confounder")
    wall = deltas["pipeline_wall_ms"]
    regressed = (
        wall["p50"]["cma_over_no_cma_ratio"] > 1.05 or
        wall["p95"]["cma_over_no_cma_ratio"] > 1.10 or
        wall["p99"]["cma_over_no_cma_ratio"] > 1.20
    )
    return {
        "schema": "sl101-cma-aba-comparison-v1",
        "performance_gate": "PASS" if not regressed else "REGRESSION",
        "production_hardware_qualification": "NOT_DECIDED_BY_THIS_SCRIPT",
        "clip_sha256": a1["clip_sha256"],
        "sequence": [
            {"phase": tag, "boot_id": p["boot_id"], "kernel": p["release"],
             "samples": p["repeats"]}
            for tag, p in zip(("A1-CMA", "B-MINUS-CMA", "A2-CMA"), phases)
        ],
        "thermal_spread_mC": max(temps) - min(temps),
        "a1_a2_pipeline_drift_fraction": round(drift, 5),
        "thresholds": {
            "pipeline_p50_cma_over_no_cma_max": 1.05,
            "pipeline_p95_cma_over_no_cma_max": 1.10,
            "pipeline_p99_cma_over_no_cma_max": 1.20,
            "thermal_spread_max_mC": 6000,
            "a1_a2_p50_drift_max": .08,
        },
        "metrics": deltas,
        "caveats": [
            "This performance comparison must be accompanied by the separate GPU/VDE pixel and boot recovery qualification",
            "CMA alloc tracepoints do not include remap overhead; only full VDE pipeline latency does",
            "The threshold is an operational acceptance policy, not a proof of no overhead",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("a1", type=Path)
    p.add_argument("b", type=Path)
    p.add_argument("a2", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    try:
        data = [json.loads(path.read_text()) for path in (args.a1, args.b, args.a2)]
        result = compare(*data)
        if args.output:
            if args.output.exists():
                raise FileExistsError("refuse to overwrite comparison")
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["performance_gate"] == "PASS" else 2
    except (ValueError, OSError, KeyError, TypeError, ZeroDivisionError) as exc:
        print("CMA_A_B_A_COMPARISON_INCONCLUSIVE:", exc, file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
