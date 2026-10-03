import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sl101_kernel7_oneshot",
    ROOT / "scripts/sl101-kernel7-oneshot.py",
)
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


class Kernel7OneShotTests(unittest.TestCase):
    def make_source(self, root: Path) -> tuple[Path, Path]:
        source = root / "source"
        module_root = source / "lib/modules" / m.DEFAULT_RELEASE
        (source / "boot").mkdir(parents=True)
        module_root.mkdir(parents=True)

        (source / "boot/vmlinuz").write_bytes(b"kernel-7")
        (source / "boot/tegra20-asus-sl101.dtb").write_bytes(b"dtb-7")
        (source / "boot/config").write_text(
            "CONFIG_DRM_TEGRA_STAGING=y\nCONFIG_ZRAM=y\n",
            encoding="utf-8",
        )
        (module_root / "modules.builtin").write_text(
            "kernel/drivers/gpu/host1x-grate/host1x-drv.ko\n",
            encoding="utf-8",
        )
        (module_root / "modules.dep").write_text(
            "kernel/drivers/net/example.ko:\n",
            encoding="utf-8",
        )
        (module_root / "modules.alias").write_text(
            "alias example example\n",
            encoding="utf-8",
        )
        mod = module_root / "kernel/drivers/net/example.ko"
        mod.parent.mkdir(parents=True)
        mod.write_bytes(b"module")

        provenance = {
            "schema": "android-infra.sl101-kernel7-consolidation.v1",
            "coherence": {
                "coherent": True,
                "errors": 0,
                "config_difference_count": 0,
            },
            "artifacts": {
                "release": m.DEFAULT_RELEASE,
                "vmlinuz_sha256": m.sha256_file(source / "boot/vmlinuz"),
                "dtb_sha256": m.sha256_file(
                    source / "boot/tegra20-asus-sl101.dtb"
                ),
                "config_sha256": m.sha256_file(source / "boot/config"),
                "modules_builtin_sha256": m.sha256_file(
                    module_root / "modules.builtin"
                ),
                "modules_dep_sha256": m.sha256_file(module_root / "modules.dep"),
                "modules_alias_sha256": m.sha256_file(module_root / "modules.alias"),
                "module_count": 1,
            },
        }
        provenance_path = root / "provenance.json"
        provenance_path.write_text(
            json.dumps(provenance, sort_keys=True),
            encoding="utf-8",
        )
        return source, provenance_path

    def test_build_and_verify_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, provenance = self.make_source(root)
            out = root / "bundle"

            manifest = m.build_bundle(source, provenance, out)
            result = m.verify_bundle(out)

            self.assertEqual(m.DEFAULT_RELEASE, manifest["release"])
            self.assertTrue(result["verified"])
            self.assertEqual(1, result["module_count"])
            self.assertFalse(result["service_enabled"])
            self.assertFalse(
                (out / "etc/runlevels/default/sl101-kernel7-oneshot").exists()
            )

            helper = out / "usr/local/sbin/sl101-kernel7-oneshot"
            self.assertTrue(helper.stat().st_mode & stat.S_IXUSR)
            text = helper.read_text(encoding="utf-8")
            self.assertLess(
                text.index('mv "$MARKER" "$PENDING"'),
                text.index('sleep "$GRACE_SECONDS"'),
            )
            self.assertLess(
                text.index('mv "$PENDING" "$ATTEMPT"'),
                text.index("kexec -l"),
            )
            self.assertIn("GRACE_SECONDS=${SL101_KERNEL7_GRACE_SECONDS:-10}", text)
            self.assertIn("exec kexec -e", text)

    def test_verify_rejects_tampered_kernel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, provenance = self.make_source(root)
            out = root / "bundle"
            m.build_bundle(source, provenance, out)
            (out / "opt/nura-kernel7/vmlinuz").write_bytes(b"tampered")

            with self.assertRaisesRegex(m.ContractError, "bundle artifact mismatch"):
                m.verify_bundle(out)

    def test_validate_source_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, provenance = self.make_source(root)
            data = json.loads(provenance.read_text(encoding="utf-8"))
            data["artifacts"]["dtb_sha256"] = "0" * 64
            provenance.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(m.ContractError, "dtb hash mismatch"):
                m.build_bundle(source, provenance, root / "bundle")

    def test_no_marker_is_no_action(self):
        ready, reason = m.evaluate_preflight(
            marker_exists=False,
            current_release=m.DEFAULT_RECOVERY_RELEASE,
            root_device=m.DEFAULT_ROOT_DEVICE,
            kernel_hash_ok=True,
            dtb_hash_ok=True,
            config_hash_ok=True,
            module_tree_ok=True,
        )
        self.assertFalse(ready)
        self.assertEqual("no-marker", reason)

    def test_wrong_recovery_kernel_fails_closed(self):
        ready, reason = m.evaluate_preflight(
            marker_exists=True,
            current_release=m.DEFAULT_RELEASE,
            root_device=m.DEFAULT_ROOT_DEVICE,
            kernel_hash_ok=True,
            dtb_hash_ok=True,
            config_hash_ok=True,
            module_tree_ok=True,
        )
        self.assertFalse(ready)
        self.assertEqual("recovery-kernel-mismatch", reason)

    def test_wrong_root_device_fails_closed(self):
        ready, reason = m.evaluate_preflight(
            marker_exists=True,
            current_release=m.DEFAULT_RECOVERY_RELEASE,
            root_device="/dev/mmcblk0p1",
            kernel_hash_ok=True,
            dtb_hash_ok=True,
            config_hash_ok=True,
            module_tree_ok=True,
        )
        self.assertFalse(ready)
        self.assertEqual("root-device-mismatch", reason)

    def test_each_hash_boundary_fails_closed(self):
        cases = (
            ("kernel_hash_ok", "kernel-hash-mismatch"),
            ("dtb_hash_ok", "dtb-hash-mismatch"),
            ("config_hash_ok", "config-hash-mismatch"),
            ("module_tree_ok", "module-tree-mismatch"),
        )
        for field, expected in cases:
            with self.subTest(field=field):
                kwargs = {
                    "marker_exists": True,
                    "current_release": m.DEFAULT_RECOVERY_RELEASE,
                    "root_device": m.DEFAULT_ROOT_DEVICE,
                    "kernel_hash_ok": True,
                    "dtb_hash_ok": True,
                    "config_hash_ok": True,
                    "module_tree_ok": True,
                }
                kwargs[field] = False
                ready, reason = m.evaluate_preflight(**kwargs)
                self.assertFalse(ready)
                self.assertEqual(expected, reason)

    def test_good_preflight_is_ready(self):
        ready, reason = m.evaluate_preflight(
            marker_exists=True,
            current_release=m.DEFAULT_RECOVERY_RELEASE,
            root_device=m.DEFAULT_ROOT_DEVICE,
            kernel_hash_ok=True,
            dtb_hash_ok=True,
            config_hash_ok=True,
            module_tree_ok=True,
        )
        self.assertTrue(ready)
        self.assertEqual("ready-for-one-shot-kexec", reason)


if __name__ == "__main__":
    unittest.main()
