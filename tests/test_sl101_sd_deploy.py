from __future__ import annotations

import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sl101-sd-deploy.py"
SPEC = importlib.util.spec_from_file_location("sl101_sd_deploy", SCRIPT)
assert SPEC and SPEC.loader
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class Sl101SdDeployTests(unittest.TestCase):
    def make_rootfs(
        self,
        root: Path,
        *,
        fstab_root: str | None = deploy.TABLET_ROOT_DEVICE,
        module_release: str = "6.18.45",
    ) -> Path:
        tree = root / "rootfs"
        (tree / "etc").mkdir(parents=True)
        (tree / "usr/lib/systemd").mkdir(parents=True)
        (tree / f"usr/lib/modules/{module_release}/kernel").mkdir(parents=True)
        fstab_text = (
            "# UNCONFIGURED FSTAB FOR BASE SYSTEM\n"
            if fstab_root is None
            else f"{fstab_root} / ext4 errors=remount-ro 0 1\n"
        )
        (tree / "etc/fstab").write_text(fstab_text, encoding="utf-8")
        (tree / "usr/lib/systemd/systemd").write_bytes(b"systemd")
        (tree / f"usr/lib/modules/{module_release}/kernel/test.ko").write_bytes(
            b"module"
        )
        archive = root / "rootfs.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(tree, arcname=".")
        return archive

    @staticmethod
    def partitioned_lsblk() -> dict:
        return {
            "blockdevices": [
                {
                    "path": "/dev/mmcblk0",
                    "type": "disk",
                    "fstype": None,
                    "ro": False,
                    "children": [
                        {
                            "path": "/dev/mmcblk0p1",
                            "type": "part",
                            "partn": 1,
                            "fstype": "ext4",
                            "partuuid": "11111111-01",
                            "mountpoints": [None],
                        }
                    ],
                }
            ]
        }

    def test_rootfs_requires_partition_one_root_and_matching_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = self.make_rootfs(root)
            info = deploy.validate_rootfs_archive(archive, "6.18.45")
            self.assertEqual("/dev/mmcblk1p1", info["fstab_root"])
            self.assertEqual("usr/lib/modules/6.18.45", info["module_layout"])

        with tempfile.TemporaryDirectory() as tmpdir:
            bad = self.make_rootfs(Path(tmpdir), fstab_root="/dev/mmcblk1")
            with self.assertRaisesRegex(deploy.ContractError, "whole-device"):
                deploy.validate_rootfs_archive(bad, "6.18.45")

    def test_rootfs_accepts_unconfigured_provenance_template_fstab(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = self.make_rootfs(Path(tmpdir), fstab_root=None)
            info = deploy.validate_rootfs_archive(archive, "6.18.45")
            self.assertEqual("unconfigured-template", info["fstab_root"])

    def test_rootfs_rejects_missing_matching_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = self.make_rootfs(Path(tmpdir), module_release="6.18.44")
            with self.assertRaisesRegex(deploy.ContractError, "no modules matching"):
                deploy.validate_rootfs_archive(archive, "6.18.45")

    def test_target_preflight_rejects_whole_disk_ext4(self) -> None:
        payload = {
            "blockdevices": [
                {
                    "path": "/dev/mmcblk0",
                    "type": "disk",
                    "fstype": "ext4",
                    "ro": False,
                    "children": [],
                }
            ]
        }
        with self.assertRaisesRegex(deploy.ContractError, "whole-disk filesystem"):
            deploy.validate_target_layout(payload, "/dev/mmcblk0")

    def test_target_preflight_requires_exactly_partition_one_ext4(self) -> None:
        info = deploy.validate_target_layout(
            self.partitioned_lsblk(),
            "/dev/mmcblk0",
        )
        self.assertEqual("/dev/mmcblk0p1", info["partition"])
        self.assertEqual(1, info["partition_number"])
        self.assertEqual("11111111-01", info["partuuid"])

        payload = self.partitioned_lsblk()
        payload["blockdevices"][0]["children"][0]["partn"] = 2
        with self.assertRaisesRegex(deploy.ContractError, "partition 1"):
            deploy.validate_target_layout(payload, "/dev/mmcblk0")

    def test_target_preflight_rejects_mounted_partition_by_default(self) -> None:
        payload = self.partitioned_lsblk()
        payload["blockdevices"][0]["children"][0]["mountpoints"] = ["/mnt/sl101"]
        with self.assertRaisesRegex(deploy.ContractError, "must be unmounted"):
            deploy.validate_target_layout(payload, "/dev/mmcblk0")

    def test_extlinux_and_fstab_share_stable_partuuid(self) -> None:
        root_spec = "PARTUUID=11111111-01"
        extlinux = deploy.render_extlinux(root_spec)
        fstab = deploy.render_fstab(root_spec)
        self.assertIn("root=PARTUUID=11111111-01", extlinux)
        self.assertIn("PARTUUID=11111111-01 / ext4", fstab)
        self.assertNotIn("root=/dev/mmcblk1 ", extlinux)
        self.assertNotIn("/dev/mmcblk1 /", fstab)

    def test_source_validation_requires_kernel_and_dtb(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rootfs = self.make_rootfs(root)
            kernel = root / "zImage"
            dtb = root / "tegra20-asus-sl101.dtb"
            kernel.write_bytes(b"kernel")
            dtb.write_bytes(b"dtb")
            value = deploy.validate_sources(rootfs, kernel, dtb, "6.18.45")
            self.assertEqual(
                deploy.sha256_file(kernel),
                value["kernel"]["sha256"],
            )
            dtb.unlink()
            with self.assertRaisesRegex(deploy.ContractError, "dtb artifact missing"):
                deploy.validate_sources(rootfs, kernel, dtb, "6.18.45")

    @staticmethod
    def erasable_mmc_lsblk() -> dict:
        return {
            "blockdevices": [
                {
                    "path": "/dev/mmcblk0",
                    "type": "disk",
                    "size": 31_914_983_424,
                    "tran": "mmc",
                    "rm": False,
                    "hotplug": True,
                    "ro": False,
                    "mountpoints": [],
                    "children": [
                        {
                            "path": "/dev/mmcblk0p1",
                            "type": "part",
                            "size": 31_913_934_848,
                            "fstype": "ext4",
                            "label": "debian",
                            "uuid": "4f6966f3-b8b0-9556-b1f3-707cd50c63a3",
                            "partuuid": None,
                            "partn": 1,
                            "mountpoints": ["/run/media/user/debian"],
                        }
                    ],
                }
            ]
        }

    def test_erasable_target_accepts_hotplug_mmc_even_when_rm_is_false(self) -> None:
        info = deploy.validate_erasable_target(self.erasable_mmc_lsblk(), "/dev/mmcblk0")
        self.assertEqual("mmc", info["transport"])
        self.assertTrue(info["hotplug"])
        self.assertFalse(info["removable"])
        self.assertEqual(["/run/media/user/debian"], info["existing_mountpoints"])
        self.assertRegex(info["confirmation_token"], r"^ERASE-[0-9a-f]{16}$")

    def test_erase_confirmation_token_changes_with_media_identity(self) -> None:
        first = deploy.validate_erasable_target(self.erasable_mmc_lsblk(), "/dev/mmcblk0")
        payload = self.erasable_mmc_lsblk()
        payload["blockdevices"][0]["children"][0]["uuid"] = "different-card"
        second = deploy.validate_erasable_target(payload, "/dev/mmcblk0")
        self.assertNotEqual(first["confirmation_token"], second["confirmation_token"])

    def test_erasable_target_rejects_system_or_implausibly_large_disks(self) -> None:
        payload = self.erasable_mmc_lsblk()
        payload["blockdevices"][0]["children"][0]["mountpoints"] = ["/boot"]
        with self.assertRaisesRegex(deploy.ContractError, "protected host mounts"):
            deploy.validate_erasable_target(payload, "/dev/mmcblk0")

        payload = self.erasable_mmc_lsblk()
        payload["blockdevices"][0]["size"] = 128_000_000_000
        with self.assertRaisesRegex(deploy.ContractError, "microSDHC.*32 GB"):
            deploy.validate_erasable_target(payload, "/dev/mmcblk0")
        accepted = deploy.validate_erasable_target(
            payload,
            "/dev/mmcblk0",
            allow_unsupported_capacity=True,
        )
        self.assertFalse(accepted["sl101_capacity_qualified"])

        payload = self.erasable_mmc_lsblk()
        payload["blockdevices"][0]["tran"] = "nvme"
        with self.assertRaisesRegex(deploy.ContractError, "refusing transport"):
            deploy.validate_erasable_target(payload, "/dev/mmcblk0")

    def test_runtime_fix_installs_and_enables_backlight_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            deploy._install_runtime_fixes(root)
            service = root / deploy.BACKLIGHT_SERVICE_DEST
            link = (
                root
                / "etc/systemd/system/multi-user.target.wants/fix-backlight.service"
            )
            self.assertTrue(service.is_file())
            self.assertTrue(link.is_symlink())
            self.assertEqual("../fix-backlight.service", str(link.readlink()))
            self.assertIn("fb0/blank", service.read_text(encoding="utf-8"))

    def test_partition_path_handles_mmc_and_sd_names(self) -> None:
        self.assertEqual("/dev/mmcblk0p1", deploy._partition_path("/dev/mmcblk0"))
        self.assertEqual("/dev/sdb1", deploy._partition_path("/dev/sdb"))

    def test_media_write_plan_is_explicitly_destructive_and_sanitized(self) -> None:
        target = deploy.validate_erasable_target(self.erasable_mmc_lsblk(), "/dev/mmcblk0")
        sources = {
            "profile": "sanitized-known-good-20260921",
            "rootfs": {"sha256": "root"},
            "kernel": {"sha256": "kernel"},
            "dtb": {"sha256": "dtb"},
        }
        plan = deploy.build_media_write_plan(target, sources)
        self.assertEqual("destructive-recreate-and-populate", plan["mode"])
        self.assertEqual("dos", plan["partitioning"]["table"])
        self.assertEqual(1, plan["partitioning"]["partitions"])
        self.assertIn("PARTUUID", plan["partitioning"]["root_binding"])
        self.assertEqual("sanitized-known-good-20260921", plan["source_profile"])

    def test_prepare_media_plan_formats_ext4_and_mounts(self) -> None:
        target = deploy.validate_erasable_target(self.erasable_mmc_lsblk(), "/dev/mmcblk0")
        plan = deploy.build_prepare_media_plan(
            target,
            Path("/mnt/sl101"),
            allow_unsupported_capacity=False,
        )
        self.assertEqual("destructive-format-and-mount", plan["mode"])
        self.assertEqual("ext4", plan["partitioning"]["filesystem"])
        self.assertEqual(1, plan["partitioning"]["partition_number"])
        self.assertEqual("/mnt/sl101", plan["mountpoint"])
        self.assertIn("mount partition 1 at /mnt/sl101", plan["actions"])


if __name__ == "__main__":
    unittest.main()
