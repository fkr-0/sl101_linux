"""Guard the SL101 dual-device boot topology and minimal production patchset.

Offline-only: no SSH, no flash, no reboot, no kexec. These are
source/artifact contract checks, not physical boot qualification.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / "docs/sl101-two-device-boot-and-kernel-contract-20261110.md"
HIST = ROOT / "docs/sl101-dmafix1-prod-candidate-boot-20261110.md"
RC2 = ROOT / "work/sl101-dmafix1-vde-rc2-20261110"
RC3 = ROOT / "work/sl101-prod-dmavde-rc3-20261110"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SL101DualBootContractTests(unittest.TestCase):
    def test_operator_bootloader_ownership_and_actual_sd_root_are_separate(self):
        data = CANON.read_text()
        self.assertIn("Original ASUS/Android bootloader", data)
        self.assertIn("Native U-Boot in internal eMMC", data)
        self.assertIn("RootBind-style", data)
        self.assertIn("microSD /dev/mmcblk1p1", data)
        self.assertIn("not the same as the", data)
        self.assertIn("eMMC", data)
        self.assertIn("actual selected kernel file still to be demonstrated", data)

    def test_pinned_physical_identities_stay_distinct(self):
        text = CANON.read_text()
        for identity in (
            "192.168.23.100",
            "sltwrpbootdebian",
            "03534453553332478030be3f6400b900",
            "7001004d4d43333247447e682c336e00",
            "192.168.23.106",
            "sl101-nura",
            "035344534c31323880ac79a543010300",
            "7001004d4d43333247448d402a656e00",
        ):
            with self.subTest(identity=identity):
                self.assertIn(identity, text)

    def test_only_two_mandatory_fixes_and_matching_module(self):
        text = CANON.read_text()
        self.assertIn("ONE shared", text)
        self.assertIn("two-functional-fix RC2", text)
        self.assertIn("0002-dma-direct-zero-no-kmap.patch", text)
        self.assertIn("0001-media-tegra-vde-async-semaphore.patch", text)
        self.assertIn("loadable kernel module", text)
        self.assertIn("Module.symvers", text)
        dma = ROOT / ("patches/linux-postmarketos-grate-7.0.1/dmafix1/"
                      "0002-dma-direct-zero-no-kmap.patch")
        mutex = ROOT / ("patches/linux-postmarketos-grate-7.0.1/vde-modfix2/"
                        "0001-media-tegra-vde-async-semaphore.patch")
        self.assertEqual(sha256(dma),
                         "b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b")
        self.assertEqual(sha256(mutex),
                         "d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de")

    def test_rc2_artifact_hash_if_host_artifact_present(self):
        file = RC2 / "sl101-dmafix1-vde-rc2-complete.tar.zst"
        if not file.exists():
            self.skipTest("large host-only archive not mounted")
        self.assertEqual(sha256(file),
                         "02c4c66cabef1560765e72a358a225e86ac00f5d75dbe905f288e6faab666912")

    def test_rc3_experimental_patch_cannot_be_called_qualified(self):
        report = ROOT / "docs/sl101-kernel-dmavde-rc3-20261110.md"
        text = report.read_text()
        self.assertIn("experimental", text)
        self.assertIn("NOT device-tested", text)
        self.assertIn("0001-arm-dma-cma-no-kmap-attributes.patch", text)
        self.assertIn("0004-vde-async-semaphore.patch", text)
        self.assertIn("Do not promote", text)
        self.assertIn("development candidate", CANON.read_text())

    def test_exact_vendor_lnx_boundary_and_separate_uboot_install(self):
        text = CANON.read_text()
        for s in (
            "8,912,896", "8,388,608", "14-MiB",
            "LNX+BAK+GP1", "DTB", "Sway/WayVNC",
            "Editing /boot/extlinux alone is insufficient proof.",
        ):
            self.assertIn(s, text)

    def test_outdated_cold_boot_assumption_is_explicitly_superseded(self):
        current = CANON.read_text()
        historical = HIST.read_text()
        self.assertIn("unproven", current)
        self.assertIn("Boot-chain correction", historical)
        self.assertIn("was not proven", historical)
        self.assertIn("physical reboot", historical)
        self.assertNotIn("A physical cold boot returns to the", historical)


if __name__ == "__main__":
    unittest.main()
