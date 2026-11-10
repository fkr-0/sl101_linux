"""Ensure the distributed RC includes the CURRENT DMA and VDE patchset."""
import hashlib
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RC = ROOT / "work/sl101-dmafix1-vde-rc2-20261110"
BASE = ROOT / "work/sl101-prod-dma-init-20261110/release"
RELEASE = "7.0.1-postmarketos-grate-dmafix1"
MOD = (f"lib/modules/{RELEASE}/kernel/drivers/media/platform/nvidia/"
       "tegra-vde/tegra-vde.ko.zst")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CurrentPatchsetRC(unittest.TestCase):
    def test_both_source_patches_in_complete_release(self):
        root = RC / "release"
        expected = {
            "patches/0002-dma-direct-zero-no-kmap.patch": "b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b",
            "patches/0003-tegra-vde-async-semaphore.patch": "d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de",
            MOD: "9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f",
            f"boot/zImage-{RELEASE}": "315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541",
        }
        for rel, hashval in expected.items():
            with self.subTest(rel=rel):
                self.assertEqual(digest(root / rel), hashval)

    def test_587_modules_unique_and_correct_vde(self):
        original = BASE / MOD
        patched = RC / "release" / MOD
        self.assertNotEqual(digest(original), digest(patched))
        self.assertEqual(len(list((RC / "release/lib/modules" / RELEASE).rglob("*.ko.zst"))), 587)
        self.assertEqual(
            subprocess.check_output(["modinfo", "-F", "depends", str(original)]),
            subprocess.check_output(["modinfo", "-F", "depends", str(patched)]),
        )

    def test_depmod_index_byte_identical(self):
        base = BASE / "lib/modules" / RELEASE
        rc = RC / "release/lib/modules" / RELEASE
        for p in base.glob("modules.*"):
            with self.subTest(p=p.name):
                self.assertEqual(p.read_bytes(), (rc / p.name).read_bytes())

    def test_manifest_and_tar_self_contained(self):
        check = subprocess.run(["python3", str(ROOT / "scripts/sl101-prod-dmafix1-vde-rc.py")],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        root = RC / "release"
        self.assertFalse(any(p.is_symlink() for p in root.rglob("*")))
        self.assertEqual(
            digest(RC / "sl101-dmafix1-vde-rc2-complete.tar.zst"),
            "02c4c66cabef1560765e72a358a225e86ac00f5d75dbe905f288e6faab666912",
        )
        self.assertIn('0003-tegra-vde-async-semaphore', (root / 'SHA256SUMS').read_text())

    def test_base_rc_does_not_qualify_as_full_rc(self):
        archive = ROOT / "work/sl101-prod-dma-init-20261110/release"
        self.assertFalse((archive / "patches/0003-tegra-vde-async-semaphore.patch").exists())


if __name__ == "__main__":
    unittest.main()
