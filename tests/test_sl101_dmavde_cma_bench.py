"""Offline tests of fail-closed SL101 hardware CMA A-B-A benchmark analysis."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BENCH = load("sl101_cma_bench", "sl101-dmavde-cma-ab-bench.py")
CMP = load("sl101_cma_aba", "sl101-dmavde-cma-ab-compare.py")


def phase(variant: str, boot: str, latency: float) -> dict:
    """Construct a synthetic phase; never borrow unverified hardware data."""
    release = CMP.REL[variant]
    module_hash = ("a" if variant == "cma" else "b") * 64
    values = {"samples": 60, "p50": latency, "p95": latency * 1.1,
              "p99": latency * 1.2}
    cpu_values = {"samples": 60, "p50": 50., "p95": 55., "p99": 60.}
    cma_values = {"samples": 1500, "p50": 500., "p95": 750., "p99": 900.}
    start = {"boot_id": boot, "ac": "1", "battery_percent": 95,
             "cpu_khz": 1000000, "temperature_mC": 29000}
    return {
        "schema": CMP.SCHEMA, "variant": variant, "release": release,
        "boot_id": boot, "repeats": 60,
        "clip_sha256": "9" * 64, "vde_module_sha256": module_hash,
        "started": start, "finished": copy.deepcopy(start),
        "cma_vmstat_delta": {"cma_alloc_fail": 0},
        "trace": {"matched_core_allocations": 1500, "errors": 0,
                  "core_cma_us": cma_values},
        "pipeline_wall_ms": values,
        "pipeline_cpu_user_ms": cpu_values,
        "pipeline_cpu_system_ms": cpu_values,
    }


def sequence():
    return (phase("cma", "boot-a", 900), phase("minus-cma", "boot-b", 910),
            phase("cma", "boot-c", 900))


class ABABenchmarkTests(unittest.TestCase):
    def test_power_profiles_keep_battery_separate_from_ac_comparison(self):
        ac = {"ac": "1", "battery_percent": 61, "charge_status": "Charging",
              "battery_current_uA": 500000}
        battery = {"ac": "0", "battery_percent": 89,
                   "charge_status": "Discharging", "battery_current_uA": -180000}
        BENCH.validate_power_profile(ac, "ac")
        BENCH.validate_power_profile(battery, "battery")
        with self.assertRaisesRegex(RuntimeError, "AC absent"):
            BENCH.validate_power_profile(battery, "ac")
        with self.assertRaisesRegex(RuntimeError, "AC=0"):
            BENCH.validate_power_profile(ac, "battery")

    def test_battery_mode_refuses_low_charge_or_heavy_draw(self):
        state = {"ac": "0", "battery_percent": 79,
                 "charge_status": "Discharging", "battery_current_uA": -180000}
        with self.assertRaisesRegex(RuntimeError, "80%"):
            BENCH.validate_power_profile(state, "battery")
        state["battery_percent"] = 85
        state["battery_current_uA"] = -750000
        with self.assertRaisesRegex(RuntimeError, "discharge current"):
            BENCH.validate_power_profile(state, "battery")
        state["battery_current_uA"] = -180000
        state["battery_percent"] = 74
        with self.assertRaisesRegex(RuntimeError, "75%"):
            BENCH.validate_power_profile(state, "battery", finish=True)

    def test_comparison_gate_rejects_battery_run(self):
        a, b, a2 = sequence()
        b["power_profile"] = "battery"
        b["started"]["ac"] = b["finished"]["ac"] = "0"
        with self.assertRaisesRegex(ValueError, "battery diagnostic"):
            CMP.compare(a, b, a2)
        # A forged/incorrect AC sensor field must not admit battery data.
        b["started"]["ac"] = b["finished"]["ac"] = "1"
        with self.assertRaisesRegex(ValueError, "battery diagnostic"):
            CMP.compare(a, b, a2)

    def test_bench_cli_help_is_valid_on_python314(self):
        cmd = [sys.executable, str(ROOT / "scripts/sl101-dmavde-cma-ab-bench.py"), "--help"]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--power-profile", result.stdout)

    def test_valid_aba_performance_pass(self):
        report = CMP.compare(*sequence())
        self.assertEqual(report["performance_gate"], "PASS")
        self.assertEqual(len(report["sequence"]), 3)
        self.assertEqual(report["production_hardware_qualification"],
                         "NOT_DECIDED_BY_THIS_SCRIPT")

    def test_detects_cma_performance_regression(self):
        a, b, a2 = sequence()
        b["pipeline_wall_ms"]["p50"] = 700
        b["pipeline_wall_ms"]["p95"] = 770
        b["pipeline_wall_ms"]["p99"] = 840
        result = CMP.compare(a, b, a2)
        self.assertEqual(result["performance_gate"], "REGRESSION")

    def test_prevents_same_boot_id_as_independent_reboot(self):
        a, b, a2 = sequence()
        a2["boot_id"] = a["boot_id"]
        a2["started"]["boot_id"] = a["boot_id"]
        a2["finished"]["boot_id"] = a["boot_id"]
        with self.assertRaisesRegex(ValueError, "distinct verified boots"):
            CMP.compare(a, b, a2)

    def test_rejects_temperature_drift(self):
        a, b, a2 = sequence()
        b["finished"]["temperature_mC"] = 36000
        with self.assertRaisesRegex(ValueError, "thermal drift"):
            CMP.compare(a, b, a2)

    def test_rejects_missing_tracing_samples(self):
        a, b, a2 = sequence()
        b["trace"]["matched_core_allocations"] = 59
        with self.assertRaisesRegex(ValueError, "incomplete CMA"):
            CMP.compare(a, b, a2)

    def test_rejects_kernel_cma_failure(self):
        a, b, a2 = sequence()
        b["cma_vmstat_delta"]["cma_alloc_fail"] = 1
        with self.assertRaisesRegex(ValueError, "allocation failures"):
            CMP.compare(a, b, a2)

    def test_rejects_unmatched_clips_and_throttling(self):
        a, b, a2 = sequence()
        b["clip_sha256"] = "1" * 64
        with self.assertRaisesRegex(ValueError, "different benchmark"):
            CMP.compare(a, b, a2)
        a, b, a2 = sequence()
        b["started"]["cpu_khz"] = 500000
        with self.assertRaisesRegex(ValueError, "throttling"):
            CMP.compare(a, b, a2)

    def test_p50_p95_p99_core_from_real_tracepoint_shape(self):
        sample = "\n".join((
            "# entries-in-buffer/entries-written: 2/2   #P:2",
            "qtdemux0:sink-29270 [000] ..... 9223.545519: cma_alloc_start: "
            "name=linux,cma@30000000 request_count=512 available_count=61968 "
            "total_count=65536 align=8",
            "qtdemux0:sink-29270 [000] ..... 9223.547685: cma_alloc_finish: "
            "name=linux,cma@30000000 pfn=0x30f00 page=0000 count=512 "
            "align=8 errorno=0",
        ))
        result = BENCH.parse_trace(sample)
        self.assertEqual(result["matched_core_allocations"], 1)
        self.assertEqual(result["core_cma_us"]["p50"], 2166.0)
        self.assertEqual(result["by_request_pages"]["512"]["p95"], 2166.0)
        self.assertEqual(result["errors"], 0)

    def test_trace_overflow_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "trace-buffer loss"):
            BENCH.parse_trace("# entries-in-buffer/entries-written: 2/3\n")


if __name__ == "__main__":
    unittest.main()
