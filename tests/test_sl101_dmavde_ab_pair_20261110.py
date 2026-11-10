"""Offline contract: two production-source kernels differ only by CMA remap.

The two candidates have independent release strings so module vermagic and
rollback state cannot collide. This suite never deploys, reboots or runs
graphics/KMS on a real tablet.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/sl101-dmavde-ab-verify.py"
SPEC = importlib.util.spec_from_file_location("sl101_dmavde_ab_20261110", TOOL)
assert SPEC and SPEC.loader
AB = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AB
SPEC.loader.exec_module(AB)


class RC3VersusMinusCMA(unittest.TestCase):
    def need_sources(self):
        if not (AB.A / "source/.sl101-four-patches-applied").is_file():
            self.skipTest("full RC source build is not mounted")
        if not (AB.B / "source/.sl101-three-patches-minus-cma-applied").is_file():
            self.skipTest("three-patch benchmark source is not mounted")

    def need_both_archives(self):
        self.need_sources()
        if not (AB.B / "release/PROVENANCE.json").is_file():
            self.skipTest("benchmark build/archive still pending")

    def test_labels_and_actual_kernel_release_are_distinct(self):
        self.assertEqual(AB.A_REL, "7.0.1-postmarketos-grate-dmavde1")
        self.assertEqual(AB.B_REL, "7.0.1-postmarketos-grate-dmavde1-minus-cma")
        self.assertNotEqual(AB.A_REL, AB.B_REL)

    def test_common_patch_inventory_is_exact_three(self):
        self.need_sources()
        report = AB.source_check()
        self.assertEqual(report["isolated_patch"], AB.CMA)
        self.assertEqual(len(report["common_patch_names"]), 3)
        for name in report["common_patch_names"]:
            self.assertNotIn("cma", name)

    def test_cma_patch_reverse_proves_exact_source_file_difference(self):
        self.need_sources()
        report = AB.source_check()
        self.assertIn("byte-identical", report["full_kernel_source_diff"])
        self.assertIn("dma-mapping.c", (AB.A / "patches" / AB.CMA).read_text())

    def test_full_kconfig_is_equal_except_unique_abi_release(self):
        self.need_sources()
        a = AB.A / "out/.config"
        b = AB.B / "out/.config"
        if not b.is_file():
            self.skipTest("benchmark kernel config not generated")
        self.assertEqual(AB.config_without_release(a), AB.config_without_release(b))
        self.assertNotEqual(a.read_text(), b.read_text())

    def test_benchmark_control_can_be_completely_qualified(self):
        self.need_both_archives()
        report = AB.compare()
        self.assertEqual(report["gate"], "HOST_AB_PAIR_PASS")
        self.assertEqual(report["shared_module_paths"], 587)
        self.assertEqual(report["rc"]["module_count"], 587)
        self.assertEqual(report["benchmark"]["module_count"], 587)
        self.assertEqual(report["rc"]["dtb_sha256"], report["benchmark"]["dtb_sha256"])
        self.assertNotEqual(report["rc"]["zimage_sha256"],
                            report["benchmark"]["zimage_sha256"])
        self.assertEqual(report["hardware_status"], "NOT_TESTED")
        self.assertEqual(report["performance"], "NOT_MEASURED")

    def test_excluded_patch_is_only_cma(self):
        self.need_both_archives()
        from json import loads
        a = loads((AB.A / "release/PROVENANCE.json").read_text())
        b = loads((AB.B / "release/PROVENANCE.json").read_text())
        assert len(a["patches"]) == 4
        self.assertEqual(len(b["patches"]), 3)
        self.assertEqual(set(x["name"] for x in a["patches"]) -
                         set(x["name"] for x in b["patches"]), {AB.CMA})
        self.assertEqual(b["excluded_patch"]["name"], AB.CMA)
        self.assertEqual(b["module_count"], 587)

    def test_preparer_refuses_cma_patch_in_control_directory(self):
        preparer = (ROOT / "scripts/sl101-dmavde-minus-cma-prepare.sh").read_text()
        self.assertIn("test ! -e", preparer)
        self.assertIn("0001-arm-dma-cma-no-kmap-attributes.patch", preparer)
        self.assertIn("patch --dry-run --fuzz=0", preparer)
        self.assertIn("sha512sum -c", preparer)

    def test_all_actions_are_host_only(self):
        for name in ("sl101-dmavde-minus-cma-prepare.sh",
                     "sl101-dmavde-minus-cma-build.sh",
                     "sl101-dmavde-minus-cma-package.py",
                     "sl101-dmavde-ab-verify.py"):
            with self.subTest(script=name):
                text = (ROOT / "scripts" / name).read_text()
                for banned in ("ssh user@", "scp user@", "fw_setenv ",
                               "kexec -e", "flash_erase ", "fastboot flash",
                               "dd if=/dev/", "reboot -f"):
                    self.assertNotIn(banned, text)

    def test_abi_qualified_module_verifier_is_required(self):
        p = (ROOT / "scripts/sl101-dmavde-minus-cma-package.py").read_text()
        self.assertIn("verify(LANE, REL, DTB_SHA", p)
        self.assertIn("CONFIG_LOCALVERSION", (ROOT / "scripts/sl101-dmavde-ab-verify.py").read_text())
        self.assertIn("sha256sum", p)
        self.assertIn("refuse overwrite", p.lower())

    def test_cli_source_only_no_hardware(self):
        self.need_sources()
        cp = subprocess.run(
            [sys.executable, str(TOOL), "--source-only"],
            capture_output=True, text=True, timeout=35)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("SOURCE_ONLY_PASS", cp.stdout)
        self.assertIn("NOT_CHECKED", cp.stdout)


if __name__ == "__main__":
    unittest.main()
