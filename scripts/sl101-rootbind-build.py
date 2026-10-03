#!/usr/bin/env python3
"""Describe and verify host-only SL101 RootBind build artifacts.

This helper deliberately stops before Android boot-image construction.  The
ASUS boot-image header/geometry, root hand-off, and target boot partition are
device facts that must come from a physically identified SL101.  Until then we
can safely prepare a pinned upstream kernel, matching modules, and a Debian
armhf rootfs entirely on the host.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

KERNEL_REMOTE = "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git"
KERNEL_REF = "v6.18.45"
KERNEL_COMMIT = "bf3be28f6721e24961992ebb9e61c0cf21a56806"
KERNEL_MAINLINE_OBSERVED = {
    "ref": "v7.2",
    "commit": "8d3ae59288f1e7d58d76558a6ee96d533bc5019f",
    "observed_on": "2026-08-22",
}
KERNEL_DTS = "arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dts"
KERNEL_DTB = "arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb"
KERNEL_CONFIG_SEED = "multi_v7_defconfig"
KERNEL_CROSS_COMPILE = "arm-linux-gnueabihf-"

DEBIAN_SUITE = "trixie"
DEBIAN_ARCH = "armhf"
DEBIAN_SNAPSHOT = "https://snapshot.debian.org/archive/debian/20260821T000000Z/"
BUILD_CONTAINER_IMAGE = "debian@sha256:b6e2a152f22a40ff69d92cb397223c906017e1391a73c952b588e51af8883bf8"
BUILD_APT_SNAPSHOT = "http://snapshot.debian.org/archive/debian/20260821T000000Z/"
BUILD_ENVIRONMENT_PACKAGES = (
    "bc",
    "bison",
    "build-essential",
    "ca-certificates",
    "debootstrap",
    "device-tree-compiler",
    "flex",
    "gcc-arm-linux-gnueabihf",
    "git",
    "kmod",
    "libelf-dev",
    "libssl-dev",
    "perl",
    "python3",
    "qemu-user-static",
    "rsync",
    "xz-utils",
)
ROOTFS_PACKAGES = (
    "ca-certificates",
    "iproute2",
    "iputils-ping",
    "iw",
    "kmod",
    "openssh-server",
    "procps",
    "systemd-sysv",
    "udev",
    "wpasupplicant",
)

# Live native-Debian evidence from 2026-09-21 established that U-Boot sees
# eMMC as mmc0 and the MicroSD slot as mmc1, with Debian rooted on partition 1.
# Keep this distinct from the older RootBind wrapper assumptions below.
NATIVE_SD_EVIDENCE_DATE = "2026-09-21"
NATIVE_SD_ROOT_DEVICE = "/dev/mmcblk1p1"
NATIVE_SD_FILESYSTEM = "ext4"
NATIVE_SD_HOST_PARTITION_NUMBER = 1
NATIVE_SD_REQUIRED_BOOT_FILES = (
    "/boot/zImage",
    "/boot/tegra20-asus-sl101.dtb",
    "/boot/extlinux/extlinux.conf",
)

# These symbols are present in the selected upstream multi_v7_defconfig and
# cover known SL101 DT-described hardware.  They are an acceptance floor, not
# a claim that every peripheral has been validated on either physical tablet.
REQUIRED_KERNEL_CONFIG = {
    "CONFIG_ARCH_TEGRA": "y",
    "CONFIG_BATTERY_SBS": "y",
    "CONFIG_BRCMFMAC": "m",
    "CONFIG_BT_HCIUART": "m",
    "CONFIG_BT_HCIUART_BCM": "y",
    "CONFIG_CHARGER_GPIO": "m",
    "CONFIG_DRM_TEGRA": "y",
    "CONFIG_INPUT_EVDEV": "y",
    "CONFIG_MMC_SDHCI_TEGRA": "y",
    "CONFIG_RTC_DRV_TEGRA": "y",
    "CONFIG_TOUCHSCREEN_ATMEL_MXT": "m",
    "CONFIG_USB": "y",
}

HOST_REQUIRED_TOOLS = (
    "git",
    "make",
    "arm-linux-gnueabihf-gcc",
    "dtc",
    "debootstrap",
    "qemu-arm-static",
    "chroot",
    "install",
    "cp",
    "mkdir",
    "tar",
    "xz",
    "sha256sum",
)


class ContractError(RuntimeError):
    """Raised when provenance or a build artifact violates the contract."""


def repo_local_path(path: Path) -> Path:
    """Resolve a path and reject build/output locations outside this checkout."""
    resolved = path if path.is_absolute() else REPO_ROOT / path
    resolved = resolved.resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ContractError(f"path must stay inside repository: {resolved}") from exc
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_kernel_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# ") and line.endswith(" is not set"):
            values[line[2 : -len(" is not set")]] = "n"
            continue
        if "=" in line and line.startswith("CONFIG_"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def validate_kernel_config(path: Path) -> list[str]:
    values = parse_kernel_config(path)
    errors = []
    for key, expected in REQUIRED_KERNEL_CONFIG.items():
        observed = values.get(key, "n")
        if observed != expected:
            errors.append(f"{key}: expected {expected}, observed {observed}")
    return errors


def run_checked(argv: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise ContractError(f"command failed: {' '.join(argv)}: {detail}")
    return result.stdout.strip()


def verify_kernel_source(source: Path) -> dict[str, Any]:
    source = repo_local_path(source)
    dts = source / KERNEL_DTS
    if not dts.is_file():
        raise ContractError(f"SL101 DTS missing: {dts}")
    head = run_checked(["git", "rev-parse", "HEAD"], cwd=source)
    if head != KERNEL_COMMIT:
        raise ContractError(f"kernel source commit mismatch: expected {KERNEL_COMMIT}, observed {head}")
    text = dts.read_text(encoding="utf-8")
    if 'model = "ASUS Eee Pad Slider SL101"' not in text:
        raise ContractError("SL101 DTS model string missing")
    if 'compatible = "asus,sl101", "nvidia,tegra20"' not in text:
        raise ContractError("SL101 DTS compatible string missing")
    return {
        "remote": KERNEL_REMOTE,
        "ref": KERNEL_REF,
        "commit": head,
        "dts": KERNEL_DTS,
        "dts_sha256": sha256_file(dts),
    }


def _probe_stdout(report: dict[str, Any], key: str) -> str:
    probes = report.get("probes", {})
    value = probes.get(key, {}).get("stdout", "") if isinstance(probes, dict) else ""
    return value.strip() if isinstance(value, str) else ""


def _parse_mount(mounts: str, mountpoint: str) -> dict[str, str] | None:
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == mountpoint:
            return {
                "device": parts[0],
                "mountpoint": parts[1],
                "filesystem": parts[2],
                "options": parts[3],
            }
    return None


def _parse_df_available_bytes(output: str, mountpoint: str) -> int | None:
    """Parse POSIX-ish `df -k` output and return available bytes for one mount."""
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[-1] == mountpoint and parts[-3].isdigit():
            return int(parts[-3]) * 1024
    return None


def archive_unpacked_size(path: Path) -> int:
    try:
        with tarfile.open(path, mode="r:*") as archive:
            return sum(member.size for member in archive.getmembers() if member.isfile())
    except (tarfile.TarError, OSError) as exc:
        raise ContractError(f"invalid tar archive {path}: {exc}") from exc


def rootfs_identity_hygiene(path: Path) -> dict[str, Any]:
    """Verify that archived target identity is intentionally uninitialized."""
    try:
        with tarfile.open(path, mode="r:*") as archive:
            members = {member.name.lstrip("./"): member for member in archive.getmembers()}
    except (tarfile.TarError, OSError) as exc:
        raise ContractError(f"invalid tar archive {path}: {exc}") from exc

    machine_id = members.get("etc/machine-id")
    ssh_host_keys = sorted(
        name for name in members if name.startswith("etc/ssh/ssh_host_")
    )
    qemu_helper = members.get("usr/bin/qemu-arm-static")
    return {
        "machine_id_present": machine_id is not None,
        "machine_id_empty": bool(machine_id and machine_id.isfile() and machine_id.size == 0),
        "ssh_host_keys": ssh_host_keys,
        "qemu_helper_present": qemu_helper is not None,
        "clean": bool(
            machine_id
            and machine_id.isfile()
            and machine_id.size == 0
            and not ssh_host_keys
            and qemu_helper is None
        ),
    }


def preserved_artifact_manifest(paths: list[Path]) -> dict[str, Any]:
    """Hash opaque preserved evidence without assigning semantic device meaning."""
    records = []
    for raw_path in sorted(paths, key=lambda item: str(item)):
        path = repo_local_path(raw_path)
        if not path.is_file():
            raise ContractError(f"preserved evidence artifact missing: {path}")
        records.append(
            {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schema": "sl101-preserved-evidence-v1",
        "mode": "host-hash-only-no-device-io",
        "artifacts": records,
        "semantic_policy": (
            "Artifact names and byte content are preserved provenance only; they do not "
            "resolve boot labels, partition paths, geometry, /data topology, or restore "
            "targets without separate live-tablet evidence."
        ),
    }


def _parse_by_name_target(listing: str, name: str) -> str | None:
    # Typical Android toolbox/toybox output ends in: "boot -> /dev/block/mmcblk0pN".
    for line in listing.splitlines():
        match = re.search(r"(?:^|\s)" + re.escape(name) + r"\s+->\s+(\S+)$", line.strip())
        if match:
            return match.group(1)
    return None


def _partition_size_bytes(partitions: str, device_path: str) -> int | None:
    name = Path(device_path).name
    for line in partitions.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] == name and parts[2].isdigit():
            # /proc/partitions reports 1 KiB blocks.
            return int(parts[2]) * 1024
    return None


def validate_live_preflight(report: dict[str, Any]) -> None:
    if report.get("mode") != "read-only-no-root-escalation":
        raise ContractError("wrapper evidence must be a read-only sl101-preflight report")
    safety = report.get("safety", {})
    if safety.get("device_writes_performed") is not False:
        raise ContractError("preflight does not attest that device writes were avoided")
    if safety.get("root_escalation_attempted") is not False:
        raise ContractError("preflight does not attest that root escalation was avoided")
    assessment = report.get("assessment", {})
    if assessment.get("looks_like_sl101") is not True:
        raise ContractError("preflight does not positively identify an ASUS SL101")


def build_wrapper_spec(report: dict[str, Any], evidence_path: Path | None = None) -> dict[str, Any]:
    """Resolve only fields directly supported by a live read-only tablet report."""
    validate_live_preflight(report)
    mounts = _probe_stdout(report, "mounts")
    partitions = _probe_stdout(report, "partitions")
    by_name = _probe_stdout(report, "block_by_name")
    data_mount = _parse_mount(mounts, "/data")
    data_free_bytes = _parse_df_available_bytes(_probe_stdout(report, "data_space_kib"), "/data")
    boot_path = _parse_by_name_target(by_name, "boot")
    boot_size = _partition_size_bytes(partitions, boot_path) if boot_path else None

    fields: dict[str, Any] = {
        "boot_image_header": {
            "status": "blocked",
            "value": None,
            "probe": "From an already-authorized rooted Android or recovery environment, copy only the first boot-partition header block to the host without writing the tablet, then record its SHA-256/byte count and parse the observed header. Do not infer the format from TF101 material.",
        },
        "kernel_ramdisk_geometry": {
            "status": "blocked",
            "value": None,
            "probe": "Derive kernel address, ramdisk address and page size only from the captured boot image/header from this physical tablet.",
        },
        "boot_partition": {
            "status": "resolved" if boot_path and boot_size else "blocked",
            "value": {"label": "boot", "path": boot_path, "size_bytes": boot_size}
            if boot_path and boot_size
            else None,
            "probe": None if boot_path and boot_size else "Capture /dev/block/by-name plus /proc/partitions on the live tablet; if the boot symlink is absent, obtain the equivalent recovery partition map without writing it.",
        },
        "android_data": {
            "status": "resolved" if data_mount and data_free_bytes is not None else "partial" if data_mount else "blocked",
            "value": ({**data_mount, "free_bytes": data_free_bytes} if data_mount else None),
            "probe": None
            if data_mount and data_free_bytes is not None
            else "Capture the live /proc/mounts entry for /data plus `df -k /data` so both backing device/filesystem and available bytes are observed.",
        },
        "rootbind_handoff": {
            "status": "partial" if data_mount else "blocked",
            "value": {
                "staging_path": "/data/linuxroot",
                "data_device": data_mount["device"],
                "data_filesystem": data_mount["filesystem"],
            }
            if data_mount
            else None,
            "probe": "A boot experiment must still prove the mount/pivot sequence from the observed Android /data topology into /data/linuxroot; no mmcblk number is accepted by default.",
        },
        "initramfs_or_mainline_patch": {
            "status": "blocked",
            "value": None,
            "probe": "After boot-image geometry and /data topology are captured, construct the smallest reversible hand-off candidate and test whether stock mainline can reach /data/linuxroot without a device-specific initramfs/patch.",
        },
        "restore_path": {
            "status": "blocked",
            "value": None,
            "probe": "Before any boot-partition write, capture the original boot image from this tablet, its exact byte size and SHA-256, and prove the recovery environment can restore that exact image to the same observed boot partition.",
        },
        "firmware_nvram": {
            "status": "blocked-runtime-evidence-required",
            "value": [],
            "probe": "After a candidate Linux kernel actually boots, record its exact firmware_class/brcmfmac filename requests; do not select filenames from TF101 guides or DTS inference alone.",
        },
    }
    required = (
        "boot_image_header",
        "kernel_ramdisk_geometry",
        "boot_partition",
        "android_data",
        "rootbind_handoff",
        "initramfs_or_mainline_patch",
        "restore_path",
        "firmware_nvram",
    )
    evidence = {
        "serial": report.get("serial"),
        "captured_at_utc": report.get("captured_at_utc"),
        "identity_evidence": report.get("assessment", {}).get("identity_evidence"),
    }
    if evidence_path is not None:
        path = repo_local_path(evidence_path)
        evidence.update({"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size})
    return {
        "schema": "sl101-rootbind-wrapper-spec-v1",
        "mode": "host-derived-from-live-read-only-evidence",
        "evidence": evidence,
        "fields": fields,
        "status": "ready" if all(fields[key]["status"] == "resolved" for key in required) else "blocked",
        "policy": {
            "no_tf101_inference": True,
            "no_legacy_partition_defaults": True,
            "no_unverified_sbk_bct_keys": True,
            "android_data_reformat_allowed": False,
        },
    }


def audit_manifest_artifacts(manifest: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, artifact in manifest.get("artifacts", {}).items():
        path_value = artifact.get("path")
        expected = artifact.get("sha256")
        path = repo_local_path(Path(path_value)) if isinstance(path_value, str) else None
        exists = bool(path and path.is_file())
        observed = sha256_file(path) if exists and path is not None else None
        result[name] = {
            "path": path_value,
            "expected_sha256": expected,
            "observed_sha256": observed,
            "size": path.stat().st_size if exists and path is not None else None,
            "matches": bool(exists and isinstance(expected, str) and observed == expected),
        }
    return result


def build_rootfs_stage_plan(
    wrapper_spec: dict[str, Any], provenance: dict[str, Any], provenance_path: Path | None = None
) -> dict[str, Any]:
    fields = wrapper_spec.get("fields", {})
    data = fields.get("android_data", {})
    artifact_audit = audit_manifest_artifacts(provenance)
    rootfs_ok = artifact_audit.get("rootfs_archive", {}).get("matches") is True
    modules_ok = artifact_audit.get("modules_archive", {}).get("matches") is True
    release_ok = provenance.get("kernel_release") == "6.18.45"
    module_layout_ok = provenance.get("debian", {}).get("module_layout") == "usr/lib/modules/6.18.45"
    rootfs_hygiene = (
        rootfs_identity_hygiene(Path(provenance["artifacts"]["rootfs_archive"]["path"]))
        if rootfs_ok
        else None
    )
    data_resolved = data.get("status") == "resolved"
    restore_resolved = fields.get("restore_path", {}).get("status") == "resolved"
    blockers: list[str] = []
    if not data_resolved:
        blockers.append("live Android /data backing device/filesystem is unresolved")
    if not restore_resolved:
        blockers.append("tested original-boot restore path is unresolved")
    if not rootfs_ok:
        blockers.append("provenance-qualified rootfs archive is missing or hash-mismatched")
    if not modules_ok:
        blockers.append("provenance-qualified modules archive is missing or hash-mismatched")
    if not release_ok or not module_layout_ok:
        blockers.append("rootfs/module release contract is not exactly 6.18.45")
    if rootfs_hygiene is not None and not rootfs_hygiene["clean"]:
        blockers.append("rootfs archive contains pre-generated target identity or host QEMU helper")

    rootfs_path_value = provenance.get("artifacts", {}).get("rootfs_archive", {}).get("path")
    rootfs_path = Path(rootfs_path_value) if isinstance(rootfs_path_value, str) else None
    unpacked_bytes = archive_unpacked_size(rootfs_path) if rootfs_ok and rootfs_path is not None else None
    # Reserve a fixed 256 MiB margin for first-boot identity generation, logs,
    # package metadata growth and staging bookkeeping.  The threshold is a host
    # contract, not a guess about partition geometry.
    required_free_bytes = unpacked_bytes + 256 * 1024 * 1024 if unpacked_bytes is not None else None
    observed_free_bytes = data.get("value", {}).get("free_bytes") if data_resolved else None
    if (
        required_free_bytes is not None
        and isinstance(observed_free_bytes, int)
        and observed_free_bytes < required_free_bytes
    ):
        blockers.append(
            f"/data free space is insufficient: need at least {required_free_bytes} bytes, observed {observed_free_bytes}"
        )

    plan = {
        "schema": "sl101-rootbind-stage-plan-v1",
        "status": "ready-to-stage" if not blockers else "blocked",
        "blockers": blockers,
        "target": {
            "path": "/data/linuxroot",
            "data_mount": data.get("value") if data_resolved else None,
            "reformat_data": False,
            "overwrite_unrelated_data": False,
            "observed_free_bytes": observed_free_bytes,
            "rootfs_unpacked_bytes": unpacked_bytes,
            "required_free_bytes": required_free_bytes,
        },
        "artifact_audit": artifact_audit,
        "rootfs_identity_hygiene": rootfs_hygiene,
        "kernel_release": provenance.get("kernel_release"),
        "module_layout": provenance.get("debian", {}).get("module_layout"),
        "identity_policy": {
            "machine_id": "archive must remain empty; generate a unique machine-id on first real boot",
            "ssh_host_keys": "archive must contain no SSH host keys; generate on first real boot",
            "authorized_keys": "inject operator-approved public keys only at staging time; never commit private keys or credentials",
        },
        "network_policy": "minimal DHCP/SSH configuration only; no committed Wi-Fi credentials or other secrets",
        "staging_sequence": [
            "verify the live /data mount still matches the wrapper evidence immediately before staging",
            "verify free space without modifying /data",
            "refuse if /data/linuxroot already exists unless an operator explicitly selects a previously created RootBind tree",
            "create /data/linuxroot and a RootBind-owned sentinel inside that new subtree only",
            "extract the provenance-qualified Debian rootfs archive into /data/linuxroot preserving numeric owners/xattrs/acls",
            "verify usr/lib/modules/6.18.45 and merged-/usr /lib -> usr/lib before first boot",
            "leave machine-id empty and SSH host keys absent until first real Linux boot",
            "apply only operator-approved public SSH key material and non-secret network defaults",
        ],
        "rollback": {
            "requires_linux_boot": False,
            "scope": "remove only the sentinel-verified /data/linuxroot subtree from Android/recovery; never reformat /data",
            "boot_restore": "separate gate: original boot image must be captured/hash-verified and recovery restore tested before any boot-partition modification",
        },
    }
    if provenance_path is not None:
        path = repo_local_path(provenance_path)
        plan["provenance"] = {"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size}
    return plan


def doctor() -> dict[str, Any]:
    tools = {tool: shutil.which(tool) for tool in HOST_REQUIRED_TOOLS}
    missing = sorted(tool for tool, path in tools.items() if path is None)
    return {
        "host_arch": platform.machine(),
        "tools": tools,
        "missing_required_tools": missing,
        "ready_for_contract_build": not missing,
        "rootfs_privilege_requirement": "debootstrap/chroot require root privileges or an explicitly configured equivalent user-namespace/container environment",
        "note": "Missing host tools are blockers for artifact construction, not permission to substitute historical SL101/TF101 toolchains.",
    }


def build_plan(work_root: Path) -> dict[str, Any]:
    work_root = repo_local_path(work_root)
    source = work_root / "linux"
    build = work_root / "kernel-build"
    module_stage = work_root / "module-stage"
    rootfs = work_root / "rootfs"
    artifacts = work_root / "artifacts"
    jobs = max(1, os.cpu_count() or 1)
    include = ",".join(ROOTFS_PACKAGES)

    return {
        "mode": "host-only-no-device-io",
        "work_root": str(work_root),
        "isolation": {
            "runtime": "docker",
            "container_image": BUILD_CONTAINER_IMAGE,
            "apt_snapshot": BUILD_APT_SNAPSHOT,
            "packages": list(BUILD_ENVIRONMENT_PACKAGES),
            "tracked_checkout_mount": "read-only",
            "generated_work_mount": "repo-local-read-write",
            "note": "Build dependencies and the target armhf rootfs are both pinned to Debian snapshot 20260821T000000Z. The build-dependency bootstrap uses HTTP only until ca-certificates is installed; signed Debian archive metadata remains the integrity boundary, and exact installed package versions are captured."
        },
        "kernel": {
            "remote": KERNEL_REMOTE,
            "ref": KERNEL_REF,
            "commit": KERNEL_COMMIT,
            "mainline_observed": KERNEL_MAINLINE_OBSERVED,
            "config_seed": KERNEL_CONFIG_SEED,
            "required_config": REQUIRED_KERNEL_CONFIG,
            "dts": KERNEL_DTS,
            "dtb": KERNEL_DTB,
            "commands": [
                ["git", "clone", "--filter=blob:none", "--depth", "1", "--branch", KERNEL_REF, KERNEL_REMOTE, str(source)],
                ["git", "-C", str(source), "checkout", "--detach", KERNEL_COMMIT],
                ["make", "-C", str(source), f"O={build}", "ARCH=arm", f"CROSS_COMPILE={KERNEL_CROSS_COMPILE}", KERNEL_CONFIG_SEED],
                ["make", "-C", str(source), f"O={build}", "ARCH=arm", f"CROSS_COMPILE={KERNEL_CROSS_COMPILE}", f"-j{jobs}", "zImage", "dtbs", "modules"],
                ["make", "-C", str(source), f"O={build}", "ARCH=arm", f"CROSS_COMPILE={KERNEL_CROSS_COMPILE}", f"INSTALL_MOD_PATH={module_stage}", "modules_install"],
            ],
        },
        "rootfs": {
            "suite": DEBIAN_SUITE,
            "arch": DEBIAN_ARCH,
            "snapshot": DEBIAN_SNAPSHOT,
            "variant": "minbase",
            "packages": list(ROOTFS_PACKAGES),
            "firmware_packages": [],
            "firmware_policy": "Do not bake a guessed TF101 firmware filename into the image. The SL101 DTS identifies BCM4329B1/brcmfmac, but exact firmware files must be accepted from the selected kernel's runtime request/evidence.",
            "commands": [
                ["debootstrap", "--arch=armhf", "--foreign", "--variant=minbase", f"--include={include}", DEBIAN_SUITE, str(rootfs), DEBIAN_SNAPSHOT],
                ["install", "-m", "0755", "/usr/bin/qemu-arm-static", str(rootfs / "usr/bin/qemu-arm-static")],
                ["chroot", str(rootfs), "/usr/bin/qemu-arm-static", "/bin/sh", "/debootstrap/debootstrap", "--second-stage"],
            ],
            "module_injection_commands": [
                ["mkdir", "-p", str(rootfs / "lib/modules")],
                ["cp", "-a", str(module_stage / "lib/modules/."), str(rootfs / "lib/modules/")],
            ],
            "package_manifest_capture": {
                "stdout_path": str(rootfs / "var/lib/dpkg/sl101-package-manifest.tsv"),
                "argv": ["chroot", str(rootfs), "/usr/bin/qemu-arm-static", "/usr/bin/dpkg-query", "-W", "-f=${binary:Package}\\t${Version}\\n"],
            },
            "normalization_before_archive": [
                "remove generated SSH host keys so the tablet creates its own identity on first boot",
                "leave /etc/machine-id empty/uninitialized",
                "remove the host-side /usr/bin/qemu-arm-static helper after the foreign second stage",
                "record /var/lib/dpkg/status and an exact dpkg-query package manifest",
                "install only modules from the matching selected kernel release",
            ],
        },
        "artifact_contract": {
            "kernel_image": str(build / "arch/arm/boot/zImage"),
            "dtb": str(build / KERNEL_DTB),
            "kernel_config": str(build / ".config"),
            "kernel_release": str(build / "include/config/kernel.release"),
            "modules_root": str(module_stage / "lib/modules"),
            "modules_archive": str(artifacts / "sl101-modules.tar.xz"),
            "rootfs_archive": str(artifacts / "debian-trixie-armhf-rootfs.tar.xz"),
            "build_environment": str(artifacts / "build-environment.json"),
            "manifest": str(artifacts / "provenance.json"),
            "archive_commands": [
                ["mkdir", "-p", str(artifacts)],
                ["tar", "--sort=name", "--mtime=@0", "--clamp-mtime", "--numeric-owner", "-C", str(module_stage), "-cJf", str(artifacts / "sl101-modules.tar.xz"), "lib/modules"],
                ["tar", "--sort=name", "--mtime=@0", "--clamp-mtime", "--numeric-owner", "--xattrs", "--acls", "-C", str(rootfs), "-cJf", str(artifacts / "debian-trixie-armhf-rootfs.tar.xz"), "."],
            ],
            "reproducibility_scope": "Archive path ordering and stored mtimes are normalized; exact hashes still intentionally attest to the concrete Debian snapshot contents, package scripts, selected kernel commit/config, and resulting filesystem state rather than claiming independent bit-for-bit reproducibility across arbitrary host tool versions.",
        },
        "native_sd_boot": {
            "status": "proven-live",
            "evidence_date": NATIVE_SD_EVIDENCE_DATE,
            "tablet_root_device": NATIVE_SD_ROOT_DEVICE,
            "filesystem": NATIVE_SD_FILESYSTEM,
            "host_partition_number": NATIVE_SD_HOST_PARTITION_NUMBER,
            "required_boot_files": list(NATIVE_SD_REQUIRED_BOOT_FILES),
            "deployment_policy": (
                "Use exactly one ext4 partition on the MicroSD. Reject a filesystem "
                "placed directly on the whole card. Prefer the partition PARTUUID in "
                "generated extlinux/fstab while retaining /dev/mmcblk1p1 as the live "
                "device-numbering evidence."
            ),
            "rootbind_scope": "This native-SD observation is not a RootBind root target and must never populate Android /data or boot-wrapper fields.",
        },
        "boot_wrapper": {
            "status": "blocked-pending-live-device-evidence",
            "build_command": None,
            "unknowns": [
                "ASUS boot image/header format used by each physical tablet",
                "kernel/ramdisk load addresses and page size",
                "exact boot partition label/path/size",
                "whether RootBind needs a device-specific initramfs or downstream root hand-off patch",
                "exact /data filesystem/device and mount hand-off required to reach /data/linuxroot",
                "tested Android/recovery restore path",
            ],
            "quarantined_defaults": [
                "legacy mmcblk0p9/mmcblk0p4 partition guesses",
                "legacy root=/dev/mmcblk1 command line",
                "historical abootimg geometry/load addresses",
                "TF101 blob/NVFlash instructions",
                "historical SBK/BCT/key material",
            ],
        },
        "validation_gates": {
            "input": [
                "Atmel MXT1386 touchscreen enumerates and reports events",
                "power and volume GPIO keys report events",
                "SL101 slider/tablet-mode switch reports SW_TABLET_MODE transitions",
                "built-in keyboard/pointing controls are identified and exercised if exposed",
            ],
            "wifi": [
                "BCM4329B1/brcmfmac device enumerates from the DT-described SDIO function",
                "runtime logs identify the exact requested firmware/NVRAM files",
                "only then add the matching firmware package/files to the rootfs provenance",
                "association, DHCP, DNS, sustained ping, and SSH pass without firmware load errors",
            ],
            "power": [
                "SBS battery reports plausible capacity/status",
                "GPIO mains/charger detection changes with external power",
                "thermal readings are available and plausible",
                "multiple suspend/resume cycles preserve input, Wi-Fi, storage, and display",
            ],
            "storage": [
                "kernel identifies eMMC and MicroSD consistently with DT aliases",
                "RootBind rootfs target comes from live partition/mount evidence, never a historical partition number",
                "Android data is not reformatted or unexpectedly mounted read-write by the Linux experiment",
            ],
        },
    }


def archive_contains(path: Path, required_path: str) -> bool:
    """Check a tar archive for one path without extracting untrusted content."""
    required = required_path.strip("/")
    try:
        with tarfile.open(path, mode="r:*") as archive:
            return any(member.name.lstrip("./") == required for member in archive.getmembers())
    except (tarfile.TarError, OSError) as exc:
        raise ContractError(f"invalid tar archive {path}: {exc}") from exc


def archive_member_sha256(path: Path, required_path: str) -> str:
    """Hash one regular-file member without extracting archive content."""
    required = required_path.strip("/")
    try:
        with tarfile.open(path, mode="r:*") as archive:
            for member in archive.getmembers():
                if member.name.lstrip("./") != required:
                    continue
                if not member.isfile():
                    raise ContractError(f"archive member is not a regular file: {required_path}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ContractError(f"archive member cannot be read: {required_path}")
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                return digest.hexdigest()
    except (tarfile.TarError, OSError) as exc:
        raise ContractError(f"invalid tar archive {path}: {exc}") from exc
    raise ContractError(f"archive member missing: {required_path}")


def rootfs_module_layout(path: Path, release: str) -> str:
    """Return the accepted module path, including a verified merged-/usr layout."""
    legacy_prefix = f"lib/modules/{release}"
    if archive_contains_prefix(path, legacy_prefix):
        return legacy_prefix

    usr_prefix = f"usr/lib/modules/{release}"
    if not archive_contains_prefix(path, usr_prefix):
        raise ContractError(
            f"rootfs archive does not contain matching {legacy_prefix}/ or {usr_prefix}/ tree"
        )
    try:
        with tarfile.open(path, mode="r:*") as archive:
            lib_member = next(
                (member for member in archive.getmembers() if member.name.lstrip("./") == "lib"),
                None,
            )
    except (tarfile.TarError, OSError) as exc:
        raise ContractError(f"invalid tar archive {path}: {exc}") from exc
    if lib_member is None or not lib_member.issym() or lib_member.linkname.lstrip("/") != "usr/lib":
        raise ContractError(
            f"rootfs archive has {usr_prefix}/ but does not bind /lib to usr/lib via a symlink"
        )
    return usr_prefix


def validate_rootfs_recovery(path: Path) -> dict[str, Any]:
    """Validate optional repo-local evidence for snapshot fetch recovery."""
    path = repo_local_path(path)
    if not path.is_file():
        raise ContractError(f"rootfs recovery provenance missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ContractError(f"invalid rootfs recovery provenance {path}: {exc}") from exc
    if value.get("mode") != "snapshot-cache-recovery-no-device-io":
        raise ContractError(f"unexpected rootfs recovery mode: {value.get('mode')!r}")
    if value.get("container_image") != BUILD_CONTAINER_IMAGE:
        raise ContractError("rootfs recovery container does not match the pinned build image")
    if value.get("rootfs_snapshot") != DEBIAN_SNAPSHOT:
        raise ContractError("rootfs recovery snapshot does not match the pinned Debian snapshot")

    objects = value.get("prefetched_objects")
    if not isinstance(objects, list) or not objects:
        raise ContractError("rootfs recovery prefetched_objects must be a non-empty list")
    verified_objects = []
    for item in objects:
        if not isinstance(item, dict):
            raise ContractError("rootfs recovery object entry must be an object")
        object_path_value = item.get("path")
        expected_sha = item.get("sha256")
        expected_size = item.get("size")
        if not isinstance(object_path_value, str) or not isinstance(expected_sha, str) or not isinstance(expected_size, int):
            raise ContractError("rootfs recovery object path/hash/size is incomplete")
        object_path = repo_local_path(Path(object_path_value))
        if not object_path.is_file():
            raise ContractError(f"rootfs recovery object missing: {object_path}")
        observed_sha = sha256_file(object_path)
        observed_size = object_path.stat().st_size
        if observed_sha != expected_sha or observed_size != expected_size:
            raise ContractError(
                f"rootfs recovery object mismatch for {object_path}: expected {expected_sha}/{expected_size}, "
                f"observed {observed_sha}/{observed_size}"
            )
        verified_objects.append({"path": str(object_path), "sha256": observed_sha, "size": observed_size})

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "mode": value["mode"],
        "integrity_rule": value.get("integrity_rule"),
        "reason": value.get("reason"),
        "result": value.get("result"),
        "prefetched_objects": verified_objects,
    }


def archive_contains_prefix(path: Path, required_prefix: str) -> bool:
    """Check a tar archive for a normalized member prefix without extraction."""
    prefix = required_prefix.strip("/") + "/"
    try:
        with tarfile.open(path, mode="r:*") as archive:
            return any(member.name.lstrip("./").startswith(prefix) for member in archive.getmembers())
    except (tarfile.TarError, OSError) as exc:
        raise ContractError(f"invalid tar archive {path}: {exc}") from exc


def read_kernel_release(build: Path) -> str:
    release_file = build / "include/config/kernel.release"
    if not release_file.is_file():
        raise ContractError(f"kernel release file missing: {release_file}")
    release = release_file.read_text(encoding="utf-8").strip()
    if not release or not re.fullmatch(r"[A-Za-z0-9._+~-]+", release):
        raise ContractError(f"invalid kernel release value: {release!r}")
    return release


def record_manifest(
    source: Path,
    build: Path,
    modules_archive: Path,
    rootfs_archive: Path,
    build_environment: Path | None = None,
    rootfs_recovery: Path | None = None,
) -> dict[str, Any]:
    source = repo_local_path(source)
    build = repo_local_path(build)
    modules_archive = repo_local_path(modules_archive)
    rootfs_archive = repo_local_path(rootfs_archive)
    source_info = verify_kernel_source(source)

    config = build / ".config"
    zimage = build / "arch/arm/boot/zImage"
    dtb = build / KERNEL_DTB
    for required in (config, zimage, dtb, modules_archive, rootfs_archive):
        if not required.is_file():
            raise ContractError(f"artifact missing: {required}")

    config_errors = validate_kernel_config(config)
    if config_errors:
        raise ContractError("kernel config gate failed: " + "; ".join(config_errors))
    release = read_kernel_release(build)
    module_prefix = f"lib/modules/{release}"
    if not archive_contains_prefix(modules_archive, module_prefix):
        raise ContractError(f"modules archive does not contain matching {module_prefix}/ tree")
    rootfs_modules = rootfs_module_layout(rootfs_archive, release)
    if not archive_contains(rootfs_archive, "var/lib/dpkg/sl101-package-manifest.tsv"):
        raise ContractError("rootfs archive is missing the captured dpkg package manifest")
    hygiene = rootfs_identity_hygiene(rootfs_archive)
    if not hygiene["clean"]:
        raise ContractError(
            "rootfs identity hygiene failed: machine-id must be an empty regular file, "
            "SSH host keys must be absent, and qemu-arm-static must not be archived"
        )
    rootfs_package_manifest_sha = archive_member_sha256(
        rootfs_archive, "var/lib/dpkg/sl101-package-manifest.tsv"
    )

    environment_info = None
    if build_environment is not None:
        build_environment = repo_local_path(build_environment)
        if not build_environment.is_file():
            raise ContractError(f"build environment provenance missing: {build_environment}")
        try:
            environment = json.loads(build_environment.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ContractError(f"invalid build environment provenance {build_environment}: {exc}") from exc
        if environment.get("container_image") != BUILD_CONTAINER_IMAGE:
            raise ContractError(
                "build environment container mismatch: "
                f"expected {BUILD_CONTAINER_IMAGE}, observed {environment.get('container_image')!r}"
            )
        if environment.get("apt_snapshot") != BUILD_APT_SNAPSHOT:
            raise ContractError(
                "build environment APT snapshot mismatch: "
                f"expected {BUILD_APT_SNAPSHOT}, observed {environment.get('apt_snapshot')!r}"
            )
        package_manifest = environment.get("package_manifest")
        if not isinstance(package_manifest, dict):
            raise ContractError("build environment package_manifest must be an object")
        manifest_path_value = package_manifest.get("path")
        manifest_sha = package_manifest.get("sha256")
        if not isinstance(manifest_path_value, str) or not isinstance(manifest_sha, str):
            raise ContractError("build environment package manifest path/hash missing")
        package_manifest_path = repo_local_path(Path(manifest_path_value))
        if not package_manifest_path.is_file():
            raise ContractError(f"build environment package manifest missing: {package_manifest_path}")
        observed_manifest_sha = sha256_file(package_manifest_path)
        if observed_manifest_sha != manifest_sha:
            raise ContractError(
                "build environment package manifest hash mismatch: "
                f"expected {manifest_sha}, observed {observed_manifest_sha}"
            )
        environment_info = {
            "path": str(build_environment),
            "sha256": sha256_file(build_environment),
            "container_image": environment["container_image"],
            "apt_snapshot": environment["apt_snapshot"],
            "package_manifest": {
                "path": str(package_manifest_path),
                "sha256": observed_manifest_sha,
            },
            "tool_versions": environment.get("tool_versions", {}),
        }

    manifest = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "mode": "host-only-no-device-io",
        "kernel_source": source_info,
        "kernel_release": release,
        "debian": {
            "suite": DEBIAN_SUITE,
            "arch": DEBIAN_ARCH,
            "snapshot": DEBIAN_SNAPSHOT,
            "module_layout": rootfs_modules,
            "package_manifest_sha256": rootfs_package_manifest_sha,
            "identity_hygiene": hygiene,
        },
        "artifacts": {
            "kernel_config": {"path": str(config), "sha256": sha256_file(config)},
            "zImage": {"path": str(zimage), "sha256": sha256_file(zimage)},
            "dtb": {"path": str(dtb), "sha256": sha256_file(dtb)},
            "modules_archive": {"path": str(modules_archive), "sha256": sha256_file(modules_archive)},
            "rootfs_archive": {"path": str(rootfs_archive), "sha256": sha256_file(rootfs_archive)},
        },
        "boot_wrapper": {
            "status": "blocked-pending-live-device-evidence",
            "artifact": None,
        },
    }
    if environment_info is not None:
        manifest["build_environment"] = environment_info
    if rootfs_recovery is not None:
        manifest["rootfs_recovery"] = validate_rootfs_recovery(rootfs_recovery)
    return manifest


def write_json(path: Path, value: dict[str, Any]) -> None:
    path = repo_local_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    path = repo_local_path(path)
    if not path.is_file():
        raise ContractError(f"JSON evidence missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ContractError(f"invalid JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON evidence must contain an object: {path}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan and verify host-only SL101 RootBind kernel/rootfs artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="emit the pinned host-only build contract as JSON")
    plan_parser.add_argument("--work-root", type=Path, default=Path("tmp/sl101-rootbind"))
    plan_parser.add_argument("--out", type=Path, help="optional repo-local JSON output; stdout if omitted")

    subparsers.add_parser("doctor", help="report host tools required by the contract")

    wrapper_parser = subparsers.add_parser(
        "wrapper-spec",
        help="derive the RootBind wrapper field status strictly from one live read-only preflight report",
    )
    wrapper_parser.add_argument("--preflight", type=Path, required=True)
    wrapper_parser.add_argument("--out", type=Path, help="optional repo-local JSON output; stdout if omitted")

    stage_parser = subparsers.add_parser(
        "stage-plan",
        help="derive a reversible /data/linuxroot staging plan from wrapper evidence and artifact provenance",
    )
    stage_parser.add_argument("--wrapper-spec", type=Path, required=True)
    stage_parser.add_argument(
        "--provenance",
        type=Path,
        default=Path("tmp/sl101-rootbind/artifacts/provenance.json"),
    )
    stage_parser.add_argument("--out", type=Path, help="optional repo-local JSON output; stdout if omitted")

    evidence_parser = subparsers.add_parser(
        "evidence-manifest",
        help="record SHA-256/byte-size provenance for opaque preserved SL101 evidence without interpreting it",
    )
    evidence_parser.add_argument("--artifact", type=Path, action="append", required=True)
    evidence_parser.add_argument("--out", type=Path, help="optional repo-local JSON output; stdout if omitted")

    record_parser = subparsers.add_parser("record", help="verify built artifacts and write a provenance manifest")
    record_parser.add_argument("--kernel-source", type=Path, required=True)
    record_parser.add_argument("--kernel-build", type=Path, required=True)
    record_parser.add_argument("--modules-archive", type=Path, required=True)
    record_parser.add_argument("--rootfs-archive", type=Path, required=True)
    record_parser.add_argument("--build-environment", type=Path)
    record_parser.add_argument("--rootfs-recovery", type=Path)
    record_parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "doctor":
            value = doctor()
            print(json.dumps(value, indent=2, sort_keys=True))
            return 0 if value["ready_for_contract_build"] else 2
        if args.command == "plan":
            value = build_plan(args.work_root)
            if args.out:
                write_json(args.out, value)
                print(repo_local_path(args.out))
            else:
                print(json.dumps(value, indent=2, sort_keys=True))
            return 0
        if args.command == "wrapper-spec":
            report = read_json(args.preflight)
            value = build_wrapper_spec(report, args.preflight)
            if args.out:
                write_json(args.out, value)
                print(repo_local_path(args.out))
            else:
                print(json.dumps(value, indent=2, sort_keys=True))
            return 0 if value["status"] == "ready" else 3
        if args.command == "stage-plan":
            wrapper_spec = read_json(args.wrapper_spec)
            provenance = read_json(args.provenance)
            value = build_rootfs_stage_plan(wrapper_spec, provenance, args.provenance)
            if args.out:
                write_json(args.out, value)
                print(repo_local_path(args.out))
            else:
                print(json.dumps(value, indent=2, sort_keys=True))
            return 0 if value["status"] == "ready-to-stage" else 3
        if args.command == "evidence-manifest":
            value = preserved_artifact_manifest(args.artifact)
            if args.out:
                write_json(args.out, value)
                print(repo_local_path(args.out))
            else:
                print(json.dumps(value, indent=2, sort_keys=True))
            return 0
        if args.command == "record":
            value = record_manifest(
                args.kernel_source,
                args.kernel_build,
                args.modules_archive,
                args.rootfs_archive,
                args.build_environment,
                args.rootfs_recovery,
            )
            write_json(args.out, value)
            print(repo_local_path(args.out))
            return 0
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
