from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from android_infra.runner import CommandResult


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sl101-preflight.py"
SPEC = importlib.util.spec_from_file_location("sl101_preflight", SCRIPT)
assert SPEC and SPEC.loader
sl101_preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sl101_preflight
SPEC.loader.exec_module(sl101_preflight)


class Sl101PreflightTests(unittest.TestCase):
    def test_probe_allowlist_is_observational(self) -> None:
        allowed = {"getprop", "uname", "id", "cat", "mount", "df", "ls"}
        forbidden = {
            "dd",
            "flash",
            "reboot",
            "push",
            "pull",
            "install",
            "uninstall",
            "setprop",
            "rm",
            "mv",
            "cp",
            "chmod",
            "chown",
            "mkdir",
            "su",
        }
        for probe in sl101_preflight.PROBES:
            self.assertIn(probe.argv[0], allowed, probe.key)
            self.assertTrue(forbidden.isdisjoint(probe.argv), probe.key)
            if probe.argv[0] == "mount":
                self.assertEqual(("mount",), probe.argv)

    def test_default_output_path_stays_repo_local_and_sanitizes_serial(self) -> None:
        path = sl101_preflight.default_output_path(
            "SL101:usb/1",
            datetime(2026, 8, 22, 1, 30, tzinfo=UTC),
        )
        self.assertEqual(
            sl101_preflight.REPO_ROOT
            / "state"
            / "sl101-preflight"
            / "SL101_usb_1"
            / "20260822T013000Z.json",
            path,
        )

    @patch.object(sl101_preflight, "adb_devices")
    def test_require_connected_rejects_unauthorized_transport(self, adb_devices_mock) -> None:
        adb_devices_mock.return_value = [{"serial": "tablet", "state": "unauthorized"}]
        with self.assertRaisesRegex(RuntimeError, "tablet=unauthorized"):
            sl101_preflight.require_connected("tablet")

    @patch.object(sl101_preflight, "run")
    def test_run_probe_uses_only_adb_shell_and_selected_serial(self, run_mock) -> None:
        run_mock.return_value = CommandResult(
            argv=("adb",),
            returncode=0,
            stdout="ASUS\n",
            stderr="",
        )
        result = sl101_preflight.run_probe("SERIAL-1", sl101_preflight.PROBES[0])
        self.assertEqual("ASUS", result["stdout"])
        argv = run_mock.call_args.args[0]
        self.assertEqual(("adb", "-s", "SERIAL-1", "shell", "getprop", "ro.product.manufacturer"), tuple(argv))

    def test_assessment_requires_exact_sl101_properties_and_vfpv3(self) -> None:
        probes = {
            "manufacturer": {"stdout": "ASUS", "stderr": ""},
            "model": {"stdout": "Eee Pad Slider SL101", "stderr": ""},
            "cpuinfo": {"stdout": "Features : swp half thumb fastmult vfp edsp neon vfpv3", "stderr": ""},
            "partitions": {"stdout": "major minor  #blocks  name\n179 0 123 mmcblk0", "stderr": ""},
            "block_by_name": {"stdout": "LNX -> /dev/block/mmcblk0p4", "stderr": ""},
            "su_indicators": {"stdout": "", "stderr": "ls: /system/xbin/su: No such file or directory"},
        }
        assessment = sl101_preflight.build_assessment(probes)
        self.assertTrue(assessment["looks_like_sl101"])
        self.assertTrue(assessment["armhf_vfpv3_observed"])
        self.assertTrue(assessment["partition_table_observed"])
        self.assertTrue(assessment["by_name_links_observed"])
        self.assertFalse(assessment["su_path_indicator_observed"])
        self.assertEqual([], assessment["warnings"])

    def test_generic_transformer_label_is_accepted_only_with_sl101_corroboration(self) -> None:
        probes = {
            "manufacturer": {"stdout": "ASUS"},
            "model": {"stdout": "Eee Pad Transformer"},
            "device": {"stdout": "SL101"},
            "product": {"stdout": "sl101_ww_epad"},
            "build_fingerprint": {"stdout": "asus/WW_epad/SL101:4.0.3/test"},
            "cpuinfo": {"stdout": "Features : vfpv3"},
            "partitions": {"stdout": "179 0 123 mmcblk0"},
            "block_by_name": {"stdout": "LNX -> /dev/block/mmcblk0p4"},
            "su_indicators": {"stdout": ""},
        }
        assessment = sl101_preflight.build_assessment(probes)
        self.assertTrue(assessment["looks_like_sl101"])
        self.assertTrue(assessment["generic_transformer_label_is_cosmetic"])
        self.assertEqual("corroborated-generic-transformer-label", assessment["identity_evidence"])
        self.assertEqual([], assessment["warnings"])

        probes["device"] = {"stdout": "tf101"}
        probes["product"] = {"stdout": "tf101"}
        probes["build_fingerprint"] = {"stdout": "asus/tf101"}
        assessment = sl101_preflight.build_assessment(probes)
        self.assertFalse(assessment["looks_like_sl101"])
        self.assertFalse(assessment["generic_transformer_label_is_cosmetic"])
        self.assertTrue(assessment["warnings"])


if __name__ == "__main__":
    unittest.main()
