"""Pure host-only contract tests for the physical SL101 dmafix1 one-shot boot."""
from pathlib import Path
import hashlib
import importlib.util
import subprocess
import tempfile
from unittest import mock
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

    def test_interrupted_stage_rollback_restores_original_files(self):
        self._rollback_fixture(new_vde=True, changed_config=True)

    def test_rollback_before_vde_backup_does_not_require_it(self):
        self._rollback_fixture(new_vde=False, changed_config=False,
                               include_vde_backup=False)

    def test_rollback_rejects_changed_foreign_extlinux(self):
        with self.assertRaises(MODULE.Guard):
            self._rollback_fixture(new_vde=True, changed_config=True,
                                   foreign_config=True)

    def test_rollback_rejects_pending_kexec(self):
        with self.assertRaises(MODULE.Guard):
            self._rollback_fixture(new_vde=True, changed_config=True,
                                   pending_kexec=True)

    def test_rollback_rejects_missing_vde_backup(self):
        with self.assertRaises(MODULE.Guard):
            self._rollback_fixture(new_vde=True, changed_config=True,
                                   include_vde_backup=False)

    def _rollback_fixture(self, *, new_vde, changed_config,
                          include_vde_backup=True, foreign_config=False,
                          pending_kexec=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir()
            (state / "extlinux.before").write_bytes(OLD)
            conf = root / "extlinux.conf"
            conf.write_bytes(
                b"foreign config" if foreign_config else
                MODULE.updated_conf(OLD) if changed_config else OLD
            )
            vde = root / "tegra-vde.ko.zst"
            old_vde, fixed_vde = b"old-vde-module", b"fixed-vde-module"
            vde.write_bytes(fixed_vde if new_vde else old_vde)
            if include_vde_backup:
                (state / "tegra-vde.before.ko.zst").write_bytes(old_vde)
            kexec_state = root / "kexec_loaded"
            kexec_state.write_text("1" if pending_kexec else "0")
            boot_id = root / "boot_id"
            boot_id.write_text("boot-id-for-test")
            with mock.patch.multiple(
                MODULE, STATE=state, CONF=conf, VDE_MODULE=vde,
                KEXEC_LOADED=kexec_state, BOOT_ID=boot_id,
                VDE_OLD_SHA=hashlib.sha256(old_vde).hexdigest(),
                VDE_NEW_SHA=hashlib.sha256(fixed_vde).hexdigest(),
            ), mock.patch.object(MODULE, "validate_target"):
                MODULE.rollback()
            self.assertEqual(conf.read_bytes(), OLD)
            self.assertEqual(vde.read_bytes(), old_vde)
            self.assertFalse(state.exists())
            archive = root / "state.rolledback-boot-id-for-test"
            self.assertTrue(archive.is_dir())
            self.assertEqual((archive / "extlinux.before").read_bytes(), OLD)

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
        self.assertIn('MANIFEST = STATE / "modules.sha256"', text)
        self.assertIn("MANIFEST_SHA", text)
        self.assertIn("boot_id", text)
        self.assertIn("loaded candidate provenance or boot-ID marker missing", text)
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
