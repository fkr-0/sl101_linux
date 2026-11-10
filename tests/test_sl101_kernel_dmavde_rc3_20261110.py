"""Host-only qualification of complete four-patch production-baseline kernel."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/sl101-prod-dmavde-rc3-20261110"
TOOLS = ROOT / "deploy/ansible/tools"
sys.path.insert(0, str(TOOLS))
from verify_kernel import PATCHES, sha, verify, source_patches_errors  # noqa E402

REL = "7.0.1-postmarketos-grate-dmavde1"
DTB_SHA = "01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0"
ARCHIVE_SHA = "d7781381ee52efb3be6edf885857b2800a4e1e00ce989a63a00955035183d8dc"
IMAGE_SHA = "79911fc494207ff0607373ceed2ff848e8b6b9252e97599a0e75913965e941aa"
VDE_SHA = "625bc023d0df8903f6387b9ff1c7963ed4ebb79eb3a13c8c1884b6ef4fd7b892"


class KernelDMAAndVDECandidateTests(unittest.TestCase):
    def require_lane(self):
        if not (LANE / "release/PROVENANCE.json").is_file():
            self.skipTest("host kernel build not mounted; repository logic still tested")

    def test_four_patches_present_and_pinned(self):
        self.assertEqual(len(PATCHES), 4)
        self.assertTrue(any("cma" in n for n in PATCHES))
        self.assertTrue(any("dma-direct" in n for n in PATCHES))
        self.assertTrue(any("cached-capture" in n for n in PATCHES))
        self.assertTrue(any("semaphore" in n for n in PATCHES))
        if not (LANE / "patches").exists():
            self.skipTest("host-only four-patch work lane not mounted")
        for path, digest in PATCHES.items():
            with self.subTest(path=path):
                tracked = ROOT / "patches/linux-postmarketos-grate-7.0.1/dmavde1" / path
                self.assertEqual(sha(tracked), digest)
                self.assertEqual(sha(LANE / "patches" / path), digest)

    def test_candidate_modules_and_compiled_vde_fixes(self):
        self.require_lane()
        issues = verify(LANE, REL, DTB_SHA, require_source_patches=True)
        self.assertEqual(issues, [], issues)
        vde = LANE / f"release/lib/modules/{REL}/kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"
        self.assertEqual(sha(vde), VDE_SHA)
        image = LANE / f"release/boot/zImage-{REL}"
        self.assertEqual(sha(image), IMAGE_SHA)

    def test_release_provenance_and_archived_sha256(self):
        self.require_lane()
        provenance = json.loads((LANE / "release/PROVENANCE.json").read_text())
        self.assertEqual(provenance["release"], REL)
        self.assertEqual(provenance["module_count"], 587)
        self.assertEqual(provenance["dtb_sha256"], DTB_SHA)
        self.assertEqual(provenance["tegra_vde_module_sha256"], VDE_SHA)
        self.assertEqual(
            {item["name"]: item["sha256"] for item in provenance["patches"]}, PATCHES
        )
        archive = LANE / "sl101-7.0.1-dmavde1-four-patch-candidate.tar.zst"
        self.assertTrue(archive.is_file())
        self.assertEqual(sha(archive), ARCHIVE_SHA)
        self.assertEqual(sha(LANE / "release/boot/tegra20-asus-sl101.dtb"), DTB_SHA)

    def test_host_only_ansible_gate_no_boot_mutations(self):
        for basename in ("kernel-preflight.yml", "hardware-preflight.yml"):
            with self.subTest(name=basename):
                data = (ROOT / "deploy/ansible/playbooks" / basename).read_text()
                for banned in ("kexec -e", "reboot:", "fw_setenv", "flash_erase", "dd if="):
                    self.assertNotIn(banned, data)
        book = (ROOT / "deploy/ansible/playbooks/kernel-preflight.yml").read_text()
        self.assertIn("hosts: localhost", book)
        self.assertIn("changed_when: false", book)
        self.assertIn("sha256sum", book)

    def test_previous_missing_vde_patch_stays_blocked(self):
        old = ROOT / "work/sl101-prod-dma-init-20261110"
        if not (old / "modules").is_dir():
            self.skipTest("previous host-only candidate not mounted")
        issues = verify(old, "7.0.1-postmarketos-grate-dmafix1")
        self.assertTrue(any("cached_capture" in issue for issue in issues))
        self.assertTrue(any("async-semaphore" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
