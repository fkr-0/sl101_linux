"""Host-only qualification for the optional production-derived Tegra VDE module."""
from pathlib import Path
import hashlib
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/sl101-vde-module-build-20261110.sh"
PATCH = ROOT / "patches/linux-postmarketos-grate-7.0.1/vde-modfix2/0001-media-tegra-vde-async-semaphore.patch"
DMA_PATCH = ROOT / "patches/linux-postmarketos-grate-7.0.1/dmafix1/0002-dma-direct-zero-no-kmap.patch"
LANE = ROOT / "work/sl101-vde-modfix2-20261110"
RELEASE = "7.0.1-postmarketos-grate-dmafix1"
STAGED = LANE / "stage/lib/modules" / RELEASE / "updates/tegra-vde.ko.zst"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VdeModuleProd(unittest.TestCase):
    def test_patch_is_pinned_verbatim(self):
        self.assertEqual(digest(PATCH), "d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de")
        self.assertEqual(digest(DMA_PATCH), "b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b")
        patch = PATCH.read_text()
        for detail in ("down_interruptible(&vde->lock)", "up(&vde->lock)",
                       "sema_init(&vde->lock, 1)", "down(&vde->lock)"):
            self.assertIn(detail, patch)
        self.assertIn("map_lock", patch)

    def test_host_script_has_no_device_side_effect(self):
        r = subprocess.run(["bash", "-n", str(BUILD)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        code = BUILD.read_text()
        for required in ("Module.symvers", "CONFIG_VIDEO_TEGRA_VDE=m",
                         "M=drivers/media/platform/nvidia/tegra-vde",
                         "modules_install", "INSTALL_MOD_PATH",
                         "source archive provenance mismatch",
                         "existing candidate output: refusing overwrite",
                         "ARCH=arm LLVM=1", "CONFIG"):
            # All code predicates except CONFIG are part of actual operational checks.
            if required != "CONFIG":
                self.assertIn(required, code)
        for forbidden in ("ssh ", "reboot ", "kexec ", "dd if=", "fw_setenv"):
            self.assertNotIn(forbidden, code)

    def test_output_matches_kernel_module_abi(self):
        if not STAGED.is_file():
            self.skipTest("optional host build not present")
        self.assertEqual(digest(STAGED), "9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f")
        old = ROOT / "work/sl101-prod-dma-init-20261110/release/lib/modules" / RELEASE / (
            "kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"
        )
        self.assertTrue(old.is_file())
        self.assertNotEqual(digest(STAGED), digest(old))
        r = subprocess.run(["modinfo", "-F", "vermagic", str(STAGED)],
                           capture_output=True, text=True, check=True)
        self.assertTrue(r.stdout.startswith(RELEASE + " SMP mod_unload modversions ARMv7"))

    def test_patch_dry_run_production_archive_source(self):
        source = ROOT / "work/sl101-vde-prod-port-20261110/source"
        if not (source / "drivers/media/platform/nvidia/tegra-vde/vde.h").is_file():
            self.skipTest("standalone extracted source fixture absent")
        r = subprocess.run(["patch", "--dry-run", "--batch", "--forward", "-p1",
                            "-d", str(source)],
                           input=PATCH.read_text(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
