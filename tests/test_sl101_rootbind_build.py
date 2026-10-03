from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sl101-rootbind-build.py"
CONTAINER_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sl101-rootbind-container-build.sh"
SPEC = importlib.util.spec_from_file_location("sl101_rootbind_build", SCRIPT)
assert SPEC and SPEC.loader
sl101_build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sl101_build)


def repo_tempdir() -> tempfile.TemporaryDirectory[str]:
    parent = sl101_build.REPO_ROOT / "tmp"
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


class Sl101RootbindBuildTests(unittest.TestCase):
    def test_plan_is_host_only_and_boot_wrapper_is_blocked(self) -> None:
        plan = sl101_build.build_plan(Path("tmp/sl101-rootbind-test"))
        self.assertEqual("host-only-no-device-io", plan["mode"])
        self.assertEqual("blocked-pending-live-device-evidence", plan["boot_wrapper"]["status"])
        self.assertIsNone(plan["boot_wrapper"]["build_command"])
        self.assertEqual(sl101_build.KERNEL_COMMIT, plan["kernel"]["commit"])
        self.assertEqual([], plan["rootfs"]["firmware_packages"])

        rendered_commands = "\n".join(
            " ".join(argv)
            for section in (plan["kernel"]["commands"], plan["rootfs"]["commands"])
            for argv in section
        ).lower()
        for forbidden in ("adb ", "fastboot", "nvflash", "fusee", "re-crypt", " dd "):
            self.assertNotIn(forbidden, rendered_commands)

    def test_plan_preserves_proven_native_sd_partition_one_contract(self) -> None:
        plan = sl101_build.build_plan(Path("tmp/sl101-rootbind-test"))
        native = plan["native_sd_boot"]
        self.assertEqual("proven-live", native["status"])
        self.assertEqual("2026-09-21", native["evidence_date"])
        self.assertEqual("/dev/mmcblk1p1", native["tablet_root_device"])
        self.assertEqual(1, native["host_partition_number"])
        self.assertEqual("ext4", native["filesystem"])
        self.assertEqual(
            [
                "/boot/zImage",
                "/boot/tegra20-asus-sl101.dtb",
                "/boot/extlinux/extlinux.conf",
            ],
            native["required_boot_files"],
        )
        self.assertNotIn("native_sd_fstab_root", plan["rootfs"])
        self.assertIn("not a RootBind root target", native["rootbind_scope"])
        self.assertIn(
            "legacy root=/dev/mmcblk1 command line",
            plan["boot_wrapper"]["quarantined_defaults"],
        )

    def test_wrapper_spec_resolves_only_live_observed_storage_fields(self) -> None:
        report = {
            "captured_at_utc": "2026-09-23T05:00:00+00:00",
            "mode": "read-only-no-root-escalation",
            "serial": "SL101-LIVE-1",
            "assessment": {"looks_like_sl101": True, "identity_evidence": "exact-model"},
            "safety": {"device_writes_performed": False, "root_escalation_attempted": False},
            "probes": {
                "mounts": {
                    "stdout": "/dev/block/mmcblk0p8 /data ext4 rw,nosuid,nodev 0 0\n"
                },
                "data_space_kib": {
                    "stdout": "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/mmcblk0p8 8388608 1048576 7340032 13% /data\n"
                },
                "partitions": {
                    "stdout": " 179        9     8192 mmcblk0p9\n 179        8  8388608 mmcblk0p8\n"
                },
                "block_by_name": {
                    "stdout": "lrwxrwxrwx root root boot -> /dev/block/mmcblk0p9\n"
                },
            },
        }
        spec = sl101_build.build_wrapper_spec(report)
        self.assertEqual("blocked", spec["status"])
        self.assertEqual("resolved", spec["fields"]["boot_partition"]["status"])
        self.assertEqual("/dev/block/mmcblk0p9", spec["fields"]["boot_partition"]["value"]["path"])
        self.assertEqual(8192 * 1024, spec["fields"]["boot_partition"]["value"]["size_bytes"])
        self.assertEqual("resolved", spec["fields"]["android_data"]["status"])
        self.assertEqual("/dev/block/mmcblk0p8", spec["fields"]["android_data"]["value"]["device"])
        self.assertEqual("ext4", spec["fields"]["android_data"]["value"]["filesystem"])
        self.assertEqual(7340032 * 1024, spec["fields"]["android_data"]["value"]["free_bytes"])
        self.assertEqual("partial", spec["fields"]["rootbind_handoff"]["status"])
        for key in ("boot_image_header", "kernel_ramdisk_geometry", "initramfs_or_mainline_patch", "restore_path"):
            self.assertEqual("blocked", spec["fields"][key]["status"])
        self.assertEqual("blocked-runtime-evidence-required", spec["fields"]["firmware_nvram"]["status"])
        self.assertTrue(spec["policy"]["no_tf101_inference"])

    def test_wrapper_spec_rejects_non_live_or_unidentified_evidence(self) -> None:
        base = {
            "mode": "read-only-no-root-escalation",
            "assessment": {"looks_like_sl101": True},
            "safety": {"device_writes_performed": False, "root_escalation_attempted": False},
            "probes": {},
        }
        bad_mode = dict(base, mode="host-only")
        with self.assertRaisesRegex(sl101_build.ContractError, "read-only"):
            sl101_build.build_wrapper_spec(bad_mode)
        unidentified = {**base, "assessment": {"looks_like_sl101": False}}
        with self.assertRaisesRegex(sl101_build.ContractError, "positively identify"):
            sl101_build.build_wrapper_spec(unidentified)

    def test_stage_plan_requires_live_data_and_hash_matching_rootfs_modules(self) -> None:
        with repo_tempdir() as tmpdir:
            root = Path(tmpdir)
            rootfs = root / "rootfs.tar.xz"
            modules = root / "modules.tar.xz"
            rootfs_tree = root / "rootfs-tree"
            (rootfs_tree / "usr/lib/modules/6.18.45").mkdir(parents=True)
            (rootfs_tree / "usr/lib/modules/6.18.45/test.ko").write_bytes(b"rootfs-module")
            (rootfs_tree / "etc").mkdir(parents=True)
            (rootfs_tree / "etc/machine-id").write_bytes(b"")
            with tarfile.open(rootfs, "w:xz") as archive:
                archive.add(rootfs_tree, arcname=".")
            modules_tree = root / "modules-tree"
            (modules_tree / "lib/modules/6.18.45").mkdir(parents=True)
            (modules_tree / "lib/modules/6.18.45/test.ko").write_bytes(b"module")
            with tarfile.open(modules, "w:xz") as archive:
                archive.add(modules_tree / "lib", arcname="lib")
            provenance = {
                "kernel_release": "6.18.45",
                "debian": {"module_layout": "usr/lib/modules/6.18.45"},
                "artifacts": {
                    "rootfs_archive": {"path": str(rootfs), "sha256": sl101_build.sha256_file(rootfs)},
                    "modules_archive": {"path": str(modules), "sha256": sl101_build.sha256_file(modules)},
                },
            }
            wrapper = {
                "fields": {
                    "android_data": {
                        "status": "resolved",
                        "value": {"device": "/dev/block/live-data", "filesystem": "ext4", "mountpoint": "/data", "options": "rw", "free_bytes": 2 * 1024 * 1024 * 1024},
                    },
                    "restore_path": {"status": "resolved", "value": {"tested": True}},
                }
            }
            plan = sl101_build.build_rootfs_stage_plan(wrapper, provenance)
            self.assertEqual("ready-to-stage", plan["status"])
            self.assertFalse(plan["target"]["reformat_data"])
            self.assertFalse(plan["rollback"]["requires_linux_boot"])
            self.assertEqual("/data/linuxroot", plan["target"]["path"])

            rootfs.write_bytes(b"changed")
            blocked = sl101_build.build_rootfs_stage_plan(wrapper, provenance)
            self.assertEqual("blocked", blocked["status"])
            self.assertIn("rootfs archive", " ".join(blocked["blockers"]))

    def test_stage_plan_blocks_without_tested_restore_or_free_space(self) -> None:
        with repo_tempdir() as tmpdir:
            root = Path(tmpdir)
            rootfs = root / "rootfs.tar.xz"
            modules = root / "modules.tar.xz"
            tree = root / "tree"
            tree.mkdir()
            (tree / "payload").write_bytes(b"x" * 4096)
            (tree / "etc").mkdir()
            (tree / "etc/machine-id").write_bytes(b"")
            for archive_path in (rootfs, modules):
                with tarfile.open(archive_path, "w:xz") as archive:
                    archive.add(tree, arcname=".")
            provenance = {
                "kernel_release": "6.18.45",
                "debian": {"module_layout": "usr/lib/modules/6.18.45"},
                "artifacts": {
                    "rootfs_archive": {"path": str(rootfs), "sha256": sl101_build.sha256_file(rootfs)},
                    "modules_archive": {"path": str(modules), "sha256": sl101_build.sha256_file(modules)},
                },
            }
            wrapper = {
                "fields": {
                    "android_data": {
                        "status": "resolved",
                        "value": {"device": "/dev/block/live-data", "filesystem": "ext4", "mountpoint": "/data", "options": "rw", "free_bytes": 1024},
                    },
                    "restore_path": {"status": "blocked", "value": None},
                }
            }
            plan = sl101_build.build_rootfs_stage_plan(wrapper, provenance)
            self.assertEqual("blocked", plan["status"])
            joined = " ".join(plan["blockers"])
            self.assertIn("restore path", joined)
            self.assertIn("free space", joined)

    def test_rootfs_identity_hygiene_blocks_baked_identity(self) -> None:
        with repo_tempdir() as tmpdir:
            root = Path(tmpdir) / "rootfs"
            (root / "etc/ssh").mkdir(parents=True)
            (root / "usr/bin").mkdir(parents=True)
            (root / "etc/machine-id").write_text("already-initialized\n", encoding="utf-8")
            (root / "etc/ssh/ssh_host_rsa_key").write_bytes(b"private")
            (root / "usr/bin/qemu-arm-static").write_bytes(b"host-helper")
            archive_path = Path(tmpdir) / "rootfs.tar.xz"
            with tarfile.open(archive_path, "w:xz") as archive:
                archive.add(root, arcname=".")
            hygiene = sl101_build.rootfs_identity_hygiene(archive_path)
            self.assertFalse(hygiene["clean"])
            self.assertFalse(hygiene["machine_id_empty"])
            self.assertIn("etc/ssh/ssh_host_rsa_key", hygiene["ssh_host_keys"])
            self.assertTrue(hygiene["qemu_helper_present"])

    def test_preserved_artifact_manifest_hashes_without_semantic_inference(self) -> None:
        with repo_tempdir() as tmpdir:
            root = Path(tmpdir)
            a = root / "boot-p9-looks-semantic.img"
            b = root / "recovery.bin"
            a.write_bytes(b"boot-bytes")
            b.write_bytes(b"recovery-bytes")
            manifest = sl101_build.preserved_artifact_manifest([b, a])
            self.assertEqual("sl101-preserved-evidence-v1", manifest["schema"])
            self.assertEqual([str(a), str(b)], [item["path"] for item in manifest["artifacts"]])
            self.assertEqual(len(b"boot-bytes"), manifest["artifacts"][0]["size"])
            self.assertEqual(sl101_build.sha256_file(a), manifest["artifacts"][0]["sha256"])
            self.assertIn("do not resolve boot labels", manifest["semantic_policy"])

    def test_plan_uses_pinned_debian_snapshot_and_matching_module_stage(self) -> None:
        plan = sl101_build.build_plan(Path("tmp/sl101-rootbind-test"))
        self.assertEqual("trixie", plan["rootfs"]["suite"])
        self.assertEqual("armhf", plan["rootfs"]["arch"])
        self.assertEqual(sl101_build.DEBIAN_SNAPSHOT, plan["rootfs"]["snapshot"])
        self.assertEqual(sl101_build.BUILD_CONTAINER_IMAGE, plan["isolation"]["container_image"])
        self.assertEqual(sl101_build.BUILD_APT_SNAPSHOT, plan["isolation"]["apt_snapshot"])
        module_install = plan["kernel"]["commands"][-1]
        self.assertTrue(any(item.startswith("INSTALL_MOD_PATH=") for item in module_install))
        self.assertEqual("cp", plan["rootfs"]["module_injection_commands"][-1][0])
        self.assertEqual("/bin/sh", plan["rootfs"]["commands"][-1][-3])
        self.assertEqual(3, len(plan["artifact_contract"]["archive_commands"]))

    def test_container_builder_is_pinned_host_only_and_read_only_for_checkout(self) -> None:
        text = CONTAINER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(sl101_build.BUILD_CONTAINER_IMAGE, text)
        self.assertIn(sl101_build.BUILD_APT_SNAPSHOT, text)
        self.assertIn('dst=/repo,readonly', text)
        self.assertNotIn("--privileged", text)
        lowered = text.lower()
        for forbidden in ("adb ", "fastboot", "nvflash", "fusee", "re-crypt"):
            self.assertNotIn(forbidden, lowered)

    def test_kernel_config_gate_reports_missing_or_wrong_symbols(self) -> None:
        with repo_tempdir() as tmpdir:
            config = Path(tmpdir) / ".config"
            config.write_text("CONFIG_ARCH_TEGRA=y\nCONFIG_BRCMFMAC=y\n", encoding="utf-8")
            errors = sl101_build.validate_kernel_config(config)
            self.assertIn("CONFIG_BRCMFMAC: expected m, observed y", errors)
            self.assertIn("CONFIG_TOUCHSCREEN_ATMEL_MXT: expected m, observed n", errors)

    def test_record_manifest_hashes_artifacts_and_keeps_boot_wrapper_blocked(self) -> None:
        with repo_tempdir() as tmpdir:
            root = Path(tmpdir)
            source = root / "linux"
            build = root / "build"
            dts = source / sl101_build.KERNEL_DTS
            dtb = build / sl101_build.KERNEL_DTB
            zimage = build / "arch/arm/boot/zImage"
            config = build / ".config"
            release_file = build / "include/config/kernel.release"
            modules = root / "modules.tar.xz"
            rootfs = root / "rootfs.tar.xz"
            build_packages = root / "build-packages.tsv"
            build_environment = root / "build-environment.json"
            recovery_object = root / "recovery-object.deb"
            rootfs_recovery = root / "rootfs-recovery.json"
            for path in (dts, dtb, zimage, config, release_file, modules, rootfs):
                path.parent.mkdir(parents=True, exist_ok=True)

            dts.write_text(
                'model = "ASUS Eee Pad Slider SL101";\ncompatible = "asus,sl101", "nvidia,tegra20";\n',
                encoding="utf-8",
            )
            config.write_text(
                "\n".join(f"{key}={value}" for key, value in sl101_build.REQUIRED_KERNEL_CONFIG.items()) + "\n",
                encoding="utf-8",
            )
            release_file.write_text("6.18.45-sl101\n", encoding="utf-8")
            dtb.write_bytes(b"dtb")
            zimage.write_bytes(b"kernel")
            module_tree = root / "module-tree"
            module_file = module_tree / "lib/modules/6.18.45-sl101/kernel/test.ko"
            module_file.parent.mkdir(parents=True, exist_ok=True)
            module_file.write_bytes(b"module")
            rootfs_tree = root / "rootfs-tree"
            rootfs_module = rootfs_tree / "lib/modules/6.18.45-sl101/kernel/test.ko"
            rootfs_module.parent.mkdir(parents=True, exist_ok=True)
            rootfs_module.write_bytes(b"module")
            (rootfs_tree / "etc").mkdir(parents=True)
            (rootfs_tree / "etc/machine-id").write_bytes(b"")
            package_manifest = rootfs_tree / "var/lib/dpkg/sl101-package-manifest.tsv"
            package_manifest.parent.mkdir(parents=True, exist_ok=True)
            package_manifest.write_text("base-files\t13.8+deb13u1\n", encoding="utf-8")
            with tarfile.open(modules, "w:xz") as archive:
                archive.add(module_tree / "lib", arcname="lib")
            with tarfile.open(rootfs, "w:xz") as archive:
                archive.add(rootfs_tree, arcname=".")
            build_packages.write_text("gcc-arm-linux-gnueabihf\t14.2.0\n", encoding="utf-8")
            build_environment.write_text(
                "{\n"
                f'  "container_image": "{sl101_build.BUILD_CONTAINER_IMAGE}",\n'
                f'  "apt_snapshot": "{sl101_build.BUILD_APT_SNAPSHOT}",\n'
                '  "package_manifest": {\n'
                f'    "path": "{build_packages.relative_to(sl101_build.REPO_ROOT)}",\n'
                f'    "sha256": "{sl101_build.sha256_file(build_packages)}"\n'
                '  },\n'
                '  "tool_versions": {"cross_gcc": "test gcc"}\n'
                "}\n",
                encoding="utf-8",
            )
            recovery_object.write_bytes(b"signed-snapshot-object")
            rootfs_recovery.write_text(
                json.dumps(
                    {
                        "container_image": sl101_build.BUILD_CONTAINER_IMAGE,
                        "integrity_rule": "test signed-index hash gate",
                        "mode": "snapshot-cache-recovery-no-device-io",
                        "prefetched_objects": [
                            {
                                "path": str(recovery_object.relative_to(sl101_build.REPO_ROOT)),
                                "sha256": sl101_build.sha256_file(recovery_object),
                                "size": recovery_object.stat().st_size,
                            }
                        ],
                        "reason": "fixture",
                        "result": "fixture completed",
                        "rootfs_snapshot": sl101_build.DEBIAN_SNAPSHOT,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(sl101_build, "run_checked", return_value=sl101_build.KERNEL_COMMIT):
                manifest = sl101_build.record_manifest(
                    source, build, modules, rootfs, build_environment, rootfs_recovery
                )
            self.assertEqual(sl101_build.KERNEL_COMMIT, manifest["kernel_source"]["commit"])
            self.assertEqual("6.18.45-sl101", manifest["kernel_release"])
            self.assertEqual(sl101_build.sha256_file(zimage), manifest["artifacts"]["zImage"]["sha256"])
            self.assertEqual(sl101_build.BUILD_CONTAINER_IMAGE, manifest["build_environment"]["container_image"])
            self.assertEqual("snapshot-cache-recovery-no-device-io", manifest["rootfs_recovery"]["mode"])
            self.assertEqual("blocked-pending-live-device-evidence", manifest["boot_wrapper"]["status"])

    def test_usrmerge_rootfs_module_layout_requires_lib_symlink(self) -> None:
        with repo_tempdir() as tmpdir:
            root = Path(tmpdir)
            tree = root / "rootfs"
            module = tree / "usr/lib/modules/6.18.45/kernel/test.ko"
            module.parent.mkdir(parents=True, exist_ok=True)
            module.write_bytes(b"module")
            (tree / "lib").symlink_to("usr/lib")
            archive_path = root / "rootfs.tar.xz"
            with tarfile.open(archive_path, "w:xz") as archive:
                archive.add(tree, arcname=".")
            self.assertEqual(
                "usr/lib/modules/6.18.45",
                sl101_build.rootfs_module_layout(archive_path, "6.18.45"),
            )

            (tree / "lib").unlink()
            (tree / "lib").mkdir()
            bad_archive_path = root / "bad-rootfs.tar.xz"
            with tarfile.open(bad_archive_path, "w:xz") as archive:
                archive.add(tree, arcname=".")
            with self.assertRaisesRegex(sl101_build.ContractError, "does not bind /lib to usr/lib"):
                sl101_build.rootfs_module_layout(bad_archive_path, "6.18.45")

    def test_repo_local_path_rejects_outside_build_destination(self) -> None:
        with self.assertRaises(sl101_build.ContractError):
            sl101_build.repo_local_path(Path("/var/tmp/sl101-rootbind"))


if __name__ == "__main__":
    unittest.main()
