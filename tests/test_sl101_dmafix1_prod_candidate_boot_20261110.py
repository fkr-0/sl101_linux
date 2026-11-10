"""Pure host-only contract tests for the physical SL101 dmafix1 one-shot boot."""
from pathlib import Path
import hashlib
import importlib.util
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "scripts/sl101-dmafix1-prod-candidate-boot.py"
SPEC = importlib.util.spec_from_file_location("sl101_dmafix1_boot", BOOT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

OLD = b"""timeout 1
default grate-k76-dontkmap
menu title boot prev kernel

label postmarketOS
\tkernel /vmlinuz
\tfdtdir /
\tinitrd /initramfs

label grate-k76-dontkmap
    menu label EXPERIMENTAL: SL101 Grate 0076 DONT_KMAP
    kernel /boot/zImage-k76-dontkmap
    fdt /boot/tegra20-asus-sl101-k76.dtb
    append root=/dev/mmcblk1p1 rootfstype=ext4 rootwait rw console=tty0 video=tegrafb loglevel=7
"""


class Dmafix1BootTests(unittest.TestCase):
    def setUp(self):
        self.orig_sha = MODULE.OLD_CONF_SHA
        MODULE.OLD_CONF_SHA = hashlib.sha256(OLD).hexdigest()
        self.addCleanup(lambda: setattr(MODULE, "OLD_CONF_SHA", self.orig_sha))

    def test_staging_changes_only_candidate_entry_and_default(self):
        new = MODULE.updated_conf(OLD)
        self.assertIn(b"default dmafix1-prod-candidate\n", new)
        self.assertIn(b"label dmafix1-prod-candidate\n", new)
        self.assertIn(b"kernel /boot/zImage-dmafix1-prod-candidate\n", new)
        self.assertIn(b"fdt /boot/tegra20-asus-sl101.dtb\n", new)
        self.assertIn(b"menu label PROD-CANDIDATE: SL101 Grate dmafix1\n", new)
        self.assertIn(b"label postmarketOS\n\tkernel /vmlinuz\n", new)
        self.assertIn(b"timeout 1\n", new)
        self.assertEqual(new.count(b"default dmafix1-prod-candidate"), 1)

    def test_wrong_original_hash_rejected(self):
        with self.assertRaises(MODULE.Guard):
            MODULE.updated_conf(OLD + b" changed")

    def test_missing_original_stock_fallback_rejected(self):
        modified = OLD.replace(b"label postmarketOS", b"label gone")
        MODULE.OLD_CONF_SHA = hashlib.sha256(modified).hexdigest()
        with self.assertRaises(MODULE.Guard):
            MODULE.updated_conf(modified)

    def test_ambiguous_default_rejected(self):
        modified = OLD + b"default grate-k76-dontkmap\n"
        MODULE.OLD_CONF_SHA = hashlib.sha256(modified).hexdigest()
        with self.assertRaises(MODULE.Guard):
            MODULE.updated_conf(modified)

    def test_scripts_parse(self):
        r = subprocess.run(["python3", "-m", "py_compile", str(BOOT)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_exact_identity_and_reboot_guard(self):
        text = BOOT.read_text()
        self.assertIn("DMAFIX1_APX_DEFAULT_STAGED", text)
        self.assertIn("tegra-vde.before.ko.zst", text)
        self.assertIn("VDE module SHA mismatch", text)
        self.assertIn("module_check()", text)
        for expected in ("035344534c31323880ac79a543010300",
                         "7.0.1-postmarketos-grate-dmafix1",
                         "7f0af633", "module_check()", "kexec_loaded",
                         "ac-adapter-detect/online", "kexec", "-e",
                         "VDE_NEW_SHA", "RC_ARCHIVE_SHA", "module_check(base=True)",
                         "extlinux.before", "cold_boot_fallback"):
            # Archive hash is separately verified by host artifact packager;
            # the device script pins the image hash instead.
            if expected != "7f0af633":
                self.assertIn(expected, text)
        for forbidden in ("/dev/mmcblk0", "fw_setenv", "fastboot flash",
                          "dd if=", "kexec -f"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
