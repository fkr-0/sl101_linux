#!/usr/bin/env python3
"""Validate and populate the proven ASUS SL101 native-Debian MicroSD layout.

Read-only inspection is the default. ``deploy`` can populate an explicitly
mounted existing ext4 partition, while ``write-media --apply`` is the guarded
destructive path that recreates supported removable media after a card-specific
confirmation token is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any


TABLET_ROOT_DEVICE = "/dev/mmcblk1p1"
ROOT_FS = "ext4"
HOST_PARTITION_NUMBER = 1
KERNEL_RELEASE = "6.18.45"
KERNEL_DEST = "boot/zImage"
DTB_DEST = "boot/tegra20-asus-sl101.dtb"
EXTLINUX_DEST = "boot/extlinux/extlinux.conf"
REPO_ROOT = Path(__file__).resolve().parents[1]
SANITIZED_ROOTFS = REPO_ROOT / "tmp/sl101-rootbind/artifacts/debian-trixie-armhf-rootfs.tar.xz"
SANITIZED_KERNEL = REPO_ROOT / "tmp/sl101-rootbind/kernel-build-tegra/arch/arm/boot/zImage"
SANITIZED_DTB = REPO_ROOT / "tmp/sl101-rootbind/kernel-build-tegra/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb"
BACKLIGHT_SERVICE_SOURCE = REPO_ROOT / "docs/sl101-fix-backlight.service"
BACKLIGHT_SERVICE_DEST = Path("etc/systemd/system/fix-backlight.service")
SANITIZED_HASHES = {
    "rootfs": "5bfc126bdb0c9d4df6048fa123f5af4cc14bda430ade81a865db9b6e3c20a460",
    "kernel": "aaf847d5a15a5c673d921f87c3c08d45dd7ddff8185723dd7da804289265d630",
    "dtb": "7c938df062396a142f800c3807ba0d8f4255cd9ff8bfc8d09e83ee93b1dcb52a",
}
MIN_TARGET_BYTES = 2 * 1024**3
# The SL101 is documented and proven here with microSDHC media.  The previous
# successful card was a nominal 32 GB / 29.7 GiB SDHC card; the failed
# replacement was a 128 GB SDXC card.  Keep destructive media creation inside
# the proven SDHC capacity class instead of treating arbitrary removable media
# as equivalent.
MAX_TARGET_BYTES = 32_000_000_000
ALLOWED_TARGET_TRANSPORTS = {"mmc", "usb"}
REQUIRED_ROOTFS_MEMBERS = (
    "etc/fstab",
    "usr/lib/systemd/systemd",
)


class ContractError(RuntimeError):
    """Raised when source artifacts or target media violate the SL101 contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_tar_name(name: str) -> str:
    return name.lstrip("./")


def _archive_members(path: Path) -> list[tarfile.TarInfo]:
    try:
        with tarfile.open(path, mode="r:*") as archive:
            return archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        raise ContractError(f"invalid rootfs archive {path}: {exc}") from exc


def _archive_text(path: Path, member_name: str) -> str:
    wanted = member_name.strip("/")
    try:
        with tarfile.open(path, mode="r:*") as archive:
            for member in archive.getmembers():
                if _normalize_tar_name(member.name) != wanted:
                    continue
                if not member.isfile():
                    raise ContractError(f"rootfs member is not a regular file: {wanted}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ContractError(f"cannot read rootfs member: {wanted}")
                return handle.read().decode("utf-8")
    except (OSError, UnicodeDecodeError, tarfile.TarError) as exc:
        raise ContractError(f"cannot read {wanted} from {path}: {exc}") from exc
    raise ContractError(f"rootfs member missing: {wanted}")


def _archive_bytes(path: Path, member_name: str) -> bytes:
    wanted = member_name.strip("/")
    try:
        with tarfile.open(path, mode="r:*") as archive:
            for member in archive.getmembers():
                if _normalize_tar_name(member.name) != wanted:
                    continue
                if not member.isfile():
                    raise ContractError(f"rootfs member is not a regular file: {wanted}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ContractError(f"cannot read rootfs member: {wanted}")
                return handle.read()
    except (OSError, tarfile.TarError) as exc:
        raise ContractError(f"cannot read {wanted} from {path}: {exc}") from exc
    raise ContractError(f"rootfs member missing: {wanted}")


def validate_rootfs_archive(path: Path, kernel_release: str) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"rootfs archive missing: {path}")

    members = _archive_members(path)
    names = {_normalize_tar_name(member.name) for member in members}
    for required in REQUIRED_ROOTFS_MEMBERS:
        if required not in names:
            raise ContractError(f"rootfs archive missing required member: {required}")

    fstab = _archive_text(path, "etc/fstab")
    fstab_root = "unconfigured-template"
    for raw_line in fstab.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 3 or fields[1] != "/":
            continue
        if fields[0] == "/dev/mmcblk1":
            raise ContractError(
                "rootfs /etc/fstab contains forbidden whole-device /dev/mmcblk1 root"
            )
        if fields[0] != TABLET_ROOT_DEVICE or fields[2] != ROOT_FS:
            raise ContractError(
                f"rootfs /etc/fstab root must be {TABLET_ROOT_DEVICE} as {ROOT_FS}, "
                f"or remain unconfigured for deployment-time PARTUUID binding; observed: {line}"
            )
        fstab_root = fields[0]
        break

    module_prefixes = (
        f"lib/modules/{kernel_release}/",
        f"usr/lib/modules/{kernel_release}/",
    )
    module_layout = next(
        (
            prefix.rstrip("/")
            for prefix in module_prefixes
            if any(name.startswith(prefix) for name in names)
        ),
        None,
    )
    if module_layout is None:
        raise ContractError(
            f"rootfs archive has no modules matching kernel release {kernel_release}"
        )

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "fstab_root": fstab_root,
        "filesystem": ROOT_FS,
        "kernel_release": kernel_release,
        "module_layout": module_layout,
    }


def build_media_write_plan(target: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "destructive-recreate-and-populate",
        "target": target,
        "source_profile": sources.get("profile"),
        "kernel_release": KERNEL_RELEASE,
        "artifacts": {
            "rootfs": sources["rootfs"],
            "kernel": sources["kernel"],
            "dtb": sources["dtb"],
        },
        "partitioning": {
            "table": "dos",
            "partitions": 1,
            "partition_number": 1,
            "start_sector": 2048,
            "filesystem": ROOT_FS,
            "label": "sl101-root",
            "root_binding": "PARTUUID generated after partition creation",
        },
        "actions": [
            "unmount target descendants only",
            "wipe existing target signatures",
            "create one DOS partition table entry",
            "format partition 1 as conservative ext4",
            "extract sanitized Debian rootfs",
            "write known-good zImage + SL101 DTB + extlinux.conf",
            "bind extlinux and /etc/fstab to the same PARTUUID",
            "install the proven framebuffer/backlight unblank service",
            "verify deployed hashes, userspace, modules and sanitized identity state",
            "sync, unmount and run read-only e2fsck",
        ],
    }


def _run_checked(argv: list[str], *, stdin: str | None = None) -> str:
    proc = subprocess.run(
        argv,
        input=stdin,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise ContractError(f"command failed ({' '.join(argv)}): {detail}")
    return proc.stdout.strip()


def _partition_path(device: str, number: int = HOST_PARTITION_NUMBER) -> str:
    return f"{device}p{number}" if device[-1:].isdigit() else f"{device}{number}"


def _unmount_target_descendants(device: str) -> None:
    payload = read_lsblk(device)
    nodes = _walk_block_nodes(payload.get("blockdevices") or [])
    disk = next((node for node in nodes if node.get("path") == device), None)
    if disk is None:
        raise ContractError(f"target disappeared before unmount: {device}")
    mounts: list[str] = []
    for node in _walk_block_nodes(disk.get("children") or []):
        mounts.extend(
            str(item)
            for item in (node.get("mountpoints") or [])
            if item not in (None, "")
        )
    for mount in sorted(set(mounts), key=len, reverse=True):
        if mount == "/" or mount == "/boot" or mount.startswith("/boot/"):
            raise ContractError(f"refusing to unmount protected path: {mount}")
        _run_checked(["umount", "--", mount])


def _wait_for_partition(path: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if Path(path).exists():
            return
        time.sleep(0.1)
    raise ContractError(f"partition node did not appear: {path}")


def _partition_and_format(
    device: str,
    expected_confirmation_token: str,
    *,
    allow_unsupported_capacity: bool = False,
) -> str:
    _unmount_target_descendants(device)
    # Re-check after unmount, immediately before the first destructive command.
    target = validate_erasable_target(
        read_lsblk(device),
        device,
        allow_unsupported_capacity=allow_unsupported_capacity,
    )
    if target["confirmation_token"] != expected_confirmation_token:
        raise ContractError(
            "target identity changed after confirmation; refusing destructive write"
        )

    disk_id = secrets.randbits(32) or 1
    table = (
        "label: dos\n"
        f"label-id: 0x{disk_id:08x}\n"
        "unit: sectors\n\n"
        "start=2048, type=83, bootable\n"
    )
    _run_checked(["wipefs", "--all", "--force", device])
    _run_checked(
        ["sfdisk", "--wipe", "always", "--wipe-partitions", "always", device],
        stdin=table,
    )
    _run_checked(["partprobe", device])
    _run_checked(["udevadm", "settle"])

    partition = _partition_path(device)
    _wait_for_partition(partition)
    _run_checked(
        [
            "mkfs.ext4",
            "-F",
            "-L",
            "sl101-root",
            "-O",
            "^64bit,^metadata_csum_seed,^orphan_file",
            partition,
        ]
    )
    _run_checked(["udevadm", "settle"])
    return partition


def _post_deploy_verify(
    mountpoint: Path,
    *,
    root_spec: str,
    sources: dict[str, Any],
) -> dict[str, Any]:
    required = [
        mountpoint / "usr/lib/systemd/systemd",
        mountpoint / KERNEL_DEST,
        mountpoint / DTB_DEST,
        mountpoint / EXTLINUX_DEST,
        mountpoint / "etc/fstab",
        mountpoint / BACKLIGHT_SERVICE_DEST,
    ]
    for path in required:
        if not path.exists():
            raise ContractError(f"deployed required path missing: {path}")

    module_roots = [
        mountpoint / f"lib/modules/{KERNEL_RELEASE}",
        mountpoint / f"usr/lib/modules/{KERNEL_RELEASE}",
    ]
    if not any(path.is_dir() for path in module_roots):
        raise ContractError(f"deployed rootfs lacks modules for {KERNEL_RELEASE}")

    kernel_hash = sha256_file(mountpoint / KERNEL_DEST)
    dtb_hash = sha256_file(mountpoint / DTB_DEST)
    if kernel_hash != sources["kernel"]["sha256"]:
        raise ContractError("deployed kernel hash does not match sanitized source")
    if dtb_hash != sources["dtb"]["sha256"]:
        raise ContractError("deployed DTB hash does not match sanitized source")

    extlinux = (mountpoint / EXTLINUX_DEST).read_text(encoding="utf-8")
    fstab = (mountpoint / "etc/fstab").read_text(encoding="utf-8")
    if f"root={root_spec}" not in extlinux or not fstab.startswith(f"{root_spec} "):
        raise ContractError("deployed root bindings disagree with generated PARTUUID")

    machine_id = mountpoint / "etc/machine-id"
    if machine_id.exists() and machine_id.read_bytes().strip():
        raise ContractError("deployed rootfs unexpectedly contains a machine identity")
    ssh_host_keys = list((mountpoint / "etc/ssh").glob("ssh_host_*")) if (mountpoint / "etc/ssh").is_dir() else []
    if ssh_host_keys:
        raise ContractError("deployed rootfs unexpectedly contains SSH host keys")

    backlight_link = (
        mountpoint
        / "etc/systemd/system/multi-user.target.wants/fix-backlight.service"
    )
    if not backlight_link.is_symlink():
        raise ContractError("deployed rootfs does not enable fix-backlight.service")

    return {
        "kernel_sha256": kernel_hash,
        "dtb_sha256": dtb_hash,
        "root_spec": root_spec,
        "modules": next(str(path.relative_to(mountpoint)) for path in module_roots if path.is_dir()),
        "identity_sanitized": True,
        "display_unblank_service": "enabled",
    }


def write_sanitized_media(
    device: str,
    sources: dict[str, Any],
    *,
    expected_confirmation_token: str,
    allow_unsupported_capacity: bool = False,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise ContractError("write-media --apply must run as root")
    target = validate_erasable_target(
        read_lsblk(device),
        device,
        allow_unsupported_capacity=allow_unsupported_capacity,
    )
    if target["confirmation_token"] != expected_confirmation_token:
        raise ContractError("target identity does not match --confirm-erase token")
    partition = _partition_and_format(
        device,
        expected_confirmation_token,
        allow_unsupported_capacity=allow_unsupported_capacity,
    )

    mount_dir = Path(tempfile.mkdtemp(prefix="sl101-sd-"))
    mounted = False
    try:
        _run_checked(["mount", "--", partition, str(mount_dir)])
        mounted = True
        payload = read_lsblk(device)
        layout = validate_target_layout(payload, device, require_unmounted=False)
        if layout["partition"] != partition:
            raise ContractError(
                f"partition identity changed after format: expected {partition}, observed {layout['partition']}"
            )
        resolved_mounts = {str(Path(value).resolve()) for value in layout["mountpoints"]}
        if str(mount_dir.resolve()) not in resolved_mounts:
            raise ContractError(
                f"new partition did not mount at expected path {mount_dir}; observed {sorted(resolved_mounts)}"
            )

        plan = build_deployment_plan(layout, sources, mount_dir)
        apply_deployment(
            plan,
            SANITIZED_ROOTFS,
            SANITIZED_KERNEL,
            SANITIZED_DTB,
            mount_dir,
        )
        verification = _post_deploy_verify(
            mount_dir,
            root_spec=plan["root_spec"],
            sources=sources,
        )
        os.sync()
    finally:
        if mounted:
            _run_checked(["umount", "--", str(mount_dir)])
        try:
            mount_dir.rmdir()
        except OSError:
            pass

    fsck = subprocess.run(
        ["e2fsck", "-fn", partition],
        check=False,
        text=True,
        capture_output=True,
    )
    if fsck.returncode != 0:
        detail = (fsck.stderr or fsck.stdout).strip()
        raise ContractError(f"post-write e2fsck failed for {partition}: {detail}")

    final_layout = validate_target_layout(read_lsblk(device), device)
    return {
        "status": "written-and-verified",
        "target": target,
        "layout": final_layout,
        "verification": verification,
        "e2fsck": "clean",
    }


def _walk_block_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for node in nodes:
        flattened.append(node)
        flattened.extend(_walk_block_nodes(node.get("children") or []))
    return flattened


def validate_target_layout(
    lsblk_payload: dict[str, Any],
    device: str,
    *,
    require_unmounted: bool = True,
) -> dict[str, Any]:
    nodes = _walk_block_nodes(lsblk_payload.get("blockdevices") or [])
    disk = next((node for node in nodes if node.get("path") == device), None)
    if disk is None:
        raise ContractError(f"target device not present in lsblk data: {device}")
    if disk.get("type") != "disk":
        raise ContractError(f"target must be a whole disk, not {disk.get('type')!r}: {device}")
    if disk.get("ro") in (1, "1", True):
        raise ContractError(f"target disk is read-only: {device}")
    if disk.get("fstype"):
        raise ContractError(
            f"refusing whole-disk filesystem {disk.get('fstype')!r} on {device}; "
            "SL101 requires an ext4 partition 1"
        )

    partitions = [
        child
        for child in (disk.get("children") or [])
        if child.get("type") == "part"
    ]
    if len(partitions) != 1:
        raise ContractError(
            f"{device} must contain exactly one partition; observed {len(partitions)}"
        )
    partition = partitions[0]
    try:
        partn = int(partition.get("partn"))
    except (TypeError, ValueError) as exc:
        raise ContractError(f"cannot determine partition number for {partition.get('path')}") from exc
    if partn != HOST_PARTITION_NUMBER:
        raise ContractError(
            f"SL101 MicroSD root must be partition 1, observed partition {partn}"
        )
    if partition.get("fstype") != ROOT_FS:
        raise ContractError(
            f"partition 1 must be {ROOT_FS}, observed {partition.get('fstype')!r}"
        )
    partuuid = partition.get("partuuid")
    if not partuuid:
        raise ContractError("partition 1 has no PARTUUID; cannot render stable boot arguments")

    mountpoints = [
        item
        for item in (partition.get("mountpoints") or [])
        if item not in (None, "")
    ]
    if require_unmounted and mountpoints:
        raise ContractError(
            f"target partition must be unmounted for preflight: "
            f"{partition.get('path')} -> {mountpoints}"
        )

    return {
        "device": device,
        "partition": partition.get("path"),
        "partition_number": partn,
        "partuuid": str(partuuid),
        "filesystem": ROOT_FS,
        "mountpoints": mountpoints,
    }


def read_lsblk(device: str) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "lsblk",
            "--json",
            "--paths",
            "--bytes",
            "-o",
            "NAME,PATH,TYPE,FSTYPE,LABEL,UUID,PARTN,PARTUUID,MOUNTPOINTS,SIZE,RM,RO,TRAN,HOTPLUG",
            device,
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise ContractError(f"lsblk failed for {device}: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid lsblk JSON for {device}: {exc}") from exc


def _truthy_block_value(value: Any) -> bool:
    return value in (1, "1", True, "true", "yes")


def validate_erasable_target(
    lsblk_payload: dict[str, Any],
    device: str,
    *,
    allow_unsupported_capacity: bool = False,
) -> dict[str, Any]:
    """Validate a whole removable/hotplug disk before any destructive action."""
    nodes = _walk_block_nodes(lsblk_payload.get("blockdevices") or [])
    disk = next((node for node in nodes if node.get("path") == device), None)
    if disk is None:
        raise ContractError(f"target device not present in lsblk data: {device}")
    if disk.get("type") != "disk":
        raise ContractError(f"erase target must be a whole disk: {device}")
    if _truthy_block_value(disk.get("ro")):
        raise ContractError(f"erase target is read-only: {device}")

    transport = str(disk.get("tran") or "")
    if transport not in ALLOWED_TARGET_TRANSPORTS:
        raise ContractError(
            f"refusing transport {transport!r} for {device}; expected removable mmc/usb media"
        )
    if not (_truthy_block_value(disk.get("rm")) or _truthy_block_value(disk.get("hotplug"))):
        raise ContractError(f"refusing non-removable/non-hotplug disk: {device}")

    try:
        size = int(disk.get("size"))
    except (TypeError, ValueError) as exc:
        raise ContractError(f"cannot determine byte size for erase target: {device}") from exc
    if size < MIN_TARGET_BYTES:
        raise ContractError(
            f"refusing target size {size} bytes for {device}; minimum supported host "
            f"media size is {MIN_TARGET_BYTES} bytes"
        )
    capacity_qualified = size <= MAX_TARGET_BYTES
    if not capacity_qualified and not allow_unsupported_capacity:
        raise ContractError(
            f"refusing target size {size} bytes for {device}; the SL101 boot path is "
            f"qualified only for microSDHC media up to 32 GB. Re-run with "
            f"--allow-unsupported-capacity only if you intentionally want to prepare "
            f"larger SDXC media despite the unqualified tablet boot path."
        )

    mountpoints: list[str] = []
    for node in [disk, *_walk_block_nodes(disk.get("children") or [])]:
        mountpoints.extend(
            str(item)
            for item in (node.get("mountpoints") or [])
            if item not in (None, "")
        )
    protected = [
        mount
        for mount in mountpoints
        if mount == "/" or mount == "/boot" or mount.startswith("/boot/")
    ]
    if protected:
        raise ContractError(
            f"refusing target containing protected host mounts: {sorted(set(protected))}"
        )

    child_identity = [
        {
            "path": node.get("path"),
            "size": node.get("size"),
            "fstype": node.get("fstype"),
            "label": node.get("label"),
            "uuid": node.get("uuid"),
            "partuuid": node.get("partuuid"),
            "partn": node.get("partn"),
        }
        for node in _walk_block_nodes(disk.get("children") or [])
    ]
    token_material = json.dumps(
        {
            "device": device,
            "size": size,
            "transport": transport,
            "children": child_identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    confirmation_token = "ERASE-" + hashlib.sha256(token_material).hexdigest()[:16]

    return {
        "device": device,
        "size_bytes": size,
        "transport": transport,
        "removable": _truthy_block_value(disk.get("rm")),
        "hotplug": _truthy_block_value(disk.get("hotplug")),
        "existing_mountpoints": sorted(set(mountpoints)),
        "confirmation_token": confirmation_token,
        "sl101_capacity_qualified": capacity_qualified,
    }


def build_prepare_media_plan(
    target: dict[str, Any],
    mountpoint: Path,
    *,
    allow_unsupported_capacity: bool,
) -> dict[str, Any]:
    return {
        "mode": "destructive-format-and-mount",
        "target": target,
        "mountpoint": str(mountpoint),
        "allow_unsupported_capacity": allow_unsupported_capacity,
        "partitioning": {
            "table": "dos",
            "partitions": 1,
            "partition_number": 1,
            "start_sector": 2048,
            "filesystem": ROOT_FS,
            "label": "sl101-root",
        },
        "actions": [
            "unmount target descendants only",
            "wipe existing target signatures",
            "create one DOS partition table entry",
            "format partition 1 as conservative ext4",
            f"mount partition 1 at {mountpoint}",
        ],
    }


def prepare_media(
    device: str,
    mountpoint: Path,
    *,
    expected_confirmation_token: str,
    allow_unsupported_capacity: bool = False,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise ContractError("prepare-media --apply must run as root")

    resolved = mountpoint.resolve()
    if str(resolved) == "/" or str(resolved) == "/boot" or str(resolved).startswith("/boot/"):
        raise ContractError(f"refusing protected mountpoint: {resolved}")
    if resolved.exists():
        if not resolved.is_dir():
            raise ContractError(f"mountpoint exists but is not a directory: {resolved}")
        if resolved.is_mount():
            raise ContractError(f"mountpoint is already active: {resolved}")
        if any(resolved.iterdir()):
            raise ContractError(f"mountpoint must be empty before preparation: {resolved}")
    else:
        resolved.mkdir(parents=True)

    target = validate_erasable_target(
        read_lsblk(device),
        device,
        allow_unsupported_capacity=allow_unsupported_capacity,
    )
    if target["confirmation_token"] != expected_confirmation_token:
        raise ContractError("target identity does not match --confirm-erase token")

    partition = _partition_and_format(
        device,
        expected_confirmation_token,
        allow_unsupported_capacity=allow_unsupported_capacity,
    )
    mounted = False
    try:
        _run_checked(["mount", "--", partition, str(resolved)])
        mounted = True
        layout = validate_target_layout(
            read_lsblk(device),
            device,
            require_unmounted=False,
        )
        observed_mounts = {str(Path(value).resolve()) for value in layout["mountpoints"]}
        if str(resolved) not in observed_mounts:
            raise ContractError(
                f"prepared partition did not mount at expected path {resolved}; "
                f"observed {sorted(observed_mounts)}"
            )
    except Exception:
        if mounted:
            _run_checked(["umount", "--", str(resolved)])
        raise

    return {
        "status": "formatted-and-mounted",
        "target": target,
        "layout": layout,
        "mountpoint": str(resolved),
    }


def validate_sanitized_baseline() -> dict[str, Any]:
    """Validate the exact provenance-qualified, identity-sanitized SL101 baseline."""
    sources = validate_sources(
        SANITIZED_ROOTFS,
        SANITIZED_KERNEL,
        SANITIZED_DTB,
        KERNEL_RELEASE,
    )
    observed = {
        "rootfs": sources["rootfs"]["sha256"],
        "kernel": sources["kernel"]["sha256"],
        "dtb": sources["dtb"]["sha256"],
    }
    for name, expected in SANITIZED_HASHES.items():
        if observed[name] != expected:
            raise ContractError(
                f"sanitized {name} hash drift: expected {expected}, observed {observed[name]}"
            )

    members = {
        _normalize_tar_name(member.name)
        for member in _archive_members(SANITIZED_ROOTFS)
    }
    sensitive = sorted(
        name
        for name in members
        if name.startswith("etc/ssh/ssh_host_")
        or name == "root/.ssh"
        or name.startswith("root/.ssh/")
        or (name.startswith("home/") and "/.ssh/" in name)
    )
    if sensitive:
        raise ContractError(
            "sanitized rootfs unexpectedly contains host/user SSH identity material: "
            + ", ".join(sensitive[:10])
        )
    if _archive_bytes(SANITIZED_ROOTFS, "etc/machine-id").strip():
        raise ContractError("sanitized rootfs has a pre-populated /etc/machine-id")

    sources["profile"] = "sanitized-known-good-20260921"
    sources["identity_sanitized"] = True
    return sources


def render_extlinux(root_spec: str) -> str:
    return (
        "default Debian\n"
        "timeout 30\n\n"
        "label Debian\n"
        "  kernel /boot/zImage\n"
        "  fdt /boot/tegra20-asus-sl101.dtb\n"
        f"  append root={root_spec} rootfstype=ext4 rootwait rw "
        "console=tty0 video=tegrafb loglevel=7\n"
    )


def render_fstab(root_spec: str) -> str:
    return f"{root_spec} / ext4 errors=remount-ro 0 1\n"


def validate_sources(
    rootfs: Path,
    kernel: Path,
    dtb: Path,
    kernel_release: str,
) -> dict[str, Any]:
    rootfs_info = validate_rootfs_archive(rootfs, kernel_release)
    for label, path in (("kernel", kernel), ("dtb", dtb)):
        if not path.is_file() or path.stat().st_size == 0:
            raise ContractError(f"{label} artifact missing or empty: {path}")
    return {
        "rootfs": rootfs_info,
        "kernel": {
            "path": str(kernel),
            "size": kernel.stat().st_size,
            "sha256": sha256_file(kernel),
        },
        "dtb": {
            "path": str(dtb),
            "size": dtb.stat().st_size,
            "sha256": sha256_file(dtb),
        },
    }


def build_deployment_plan(
    layout: dict[str, Any],
    sources: dict[str, Any],
    mountpoint: Path,
) -> dict[str, Any]:
    root_spec = f"PARTUUID={layout['partuuid']}"
    return {
        "mode": "populate-existing-partition-only",
        "target": layout,
        "mountpoint": str(mountpoint),
        "tablet_root_device_evidence": TABLET_ROOT_DEVICE,
        "root_spec": root_spec,
        "rootfs": sources["rootfs"],
        "kernel": sources["kernel"],
        "dtb": sources["dtb"],
        "writes": [
            "extract rootfs archive to partition 1",
            f"write /{KERNEL_DEST}",
            f"write /{DTB_DEST}",
            f"write /{EXTLINUX_DEST}",
            "rewrite /etc/fstab to the same partition PARTUUID used by extlinux",
            "install and enable fix-backlight.service",
        ],
        "extlinux": render_extlinux(root_spec),
        "fstab": render_fstab(root_spec),
    }


def _ensure_deploy_mount(layout: dict[str, Any], mountpoint: Path) -> Path:
    resolved = mountpoint.resolve()
    if not resolved.is_dir() or not resolved.is_mount():
        raise ContractError(f"deploy mountpoint is not an active mount: {resolved}")
    observed_mounts = {str(Path(value).resolve()) for value in layout["mountpoints"]}
    if str(resolved) not in observed_mounts:
        raise ContractError(
            f"{layout['partition']} is not mounted at requested target {resolved}; "
            f"observed {sorted(observed_mounts)}"
        )
    entries = {entry.name for entry in resolved.iterdir()}
    unexpected = entries - {"lost+found"}
    if unexpected:
        raise ContractError(
            "deploy target is not empty; refusing to overwrite existing files: "
            f"{sorted(unexpected)[:10]}"
        )
    return resolved


def apply_deployment(
    plan: dict[str, Any],
    rootfs: Path,
    kernel: Path,
    dtb: Path,
    mountpoint: Path,
) -> None:
    resolved = _ensure_deploy_mount(plan["target"], mountpoint)
    proc = subprocess.run(
        [
            "tar",
            "--numeric-owner",
            "--xattrs",
            "--acls",
            "-xf",
            str(rootfs),
            "-C",
            str(resolved),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise ContractError(f"rootfs extraction failed: {proc.stderr.strip()}")

    boot = resolved / "boot"
    extlinux_dir = boot / "extlinux"
    extlinux_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kernel, boot / "zImage")
    shutil.copy2(dtb, boot / "tegra20-asus-sl101.dtb")
    (extlinux_dir / "extlinux.conf").write_text(plan["extlinux"], encoding="utf-8")
    (resolved / "etc/fstab").write_text(plan["fstab"], encoding="utf-8")
    _install_runtime_fixes(resolved)
    os.sync()


def _install_runtime_fixes(root: Path) -> None:
    """Install fixes proven necessary on the live SL101 baseline."""
    if not BACKLIGHT_SERVICE_SOURCE.is_file():
        raise ContractError(
            f"SL101 backlight service source is missing: {BACKLIGHT_SERVICE_SOURCE}"
        )
    service = root / BACKLIGHT_SERVICE_DEST
    service.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BACKLIGHT_SERVICE_SOURCE, service)

    wants = root / "etc/systemd/system/multi-user.target.wants"
    wants.mkdir(parents=True, exist_ok=True)
    link = wants / service.name
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to("../fix-backlight.service")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight", help="read-only validation of target media layout"
    )
    preflight.add_argument("--device", required=True)

    verify = subparsers.add_parser(
        "verify-source", help="verify rootfs/kernel/DTB source artifacts"
    )
    verify.add_argument("--rootfs", type=Path, required=True)
    verify.add_argument("--kernel", type=Path, required=True)
    verify.add_argument("--dtb", type=Path, required=True)
    verify.add_argument("--kernel-release", required=True)

    deploy = subparsers.add_parser(
        "deploy", help="populate an already formatted/mounted partition 1"
    )
    deploy.add_argument("--device", required=True)
    deploy.add_argument("--mountpoint", type=Path, required=True)
    deploy.add_argument("--rootfs", type=Path, required=True)
    deploy.add_argument("--kernel", type=Path, required=True)
    deploy.add_argument("--dtb", type=Path, required=True)
    deploy.add_argument("--kernel-release", required=True)
    deploy.add_argument(
        "--apply",
        action="store_true",
        help="perform writes; without this flag only print the validated deployment plan",
    )

    write_media = subparsers.add_parser(
        "write-media",
        help="recreate a removable SD card and install the exact sanitized known-good SL101 baseline",
    )
    write_media.add_argument("--device", required=True)
    write_media.add_argument(
        "--apply",
        action="store_true",
        help="erase/repartition/format/write the target; without this flag print a read-only plan",
    )
    write_media.add_argument(
        "--confirm-erase",
        help="must equal the ERASE-... confirmation token printed by the read-only plan",
    )
    write_media.add_argument(
        "--allow-unsupported-capacity",
        action="store_true",
        help="allow >32 GB SDXC media despite the SL101 boot path being unqualified for it",
    )

    prepare_media_parser = subparsers.add_parser(
        "prepare-media",
        help="erase/repartition/format removable media as ext4 partition 1 and leave it mounted",
    )
    prepare_media_parser.add_argument("--device", required=True)
    prepare_media_parser.add_argument("--mountpoint", type=Path, required=True)
    prepare_media_parser.add_argument(
        "--apply",
        action="store_true",
        help="erase/repartition/format/mount the target; without this flag print a read-only plan",
    )
    prepare_media_parser.add_argument(
        "--confirm-erase",
        help="must equal the ERASE-... confirmation token printed by the read-only plan",
    )
    prepare_media_parser.add_argument(
        "--allow-unsupported-capacity",
        action="store_true",
        help="allow >32 GB SDXC media for host preparation despite unqualified SL101 boot support",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "preflight":
            layout = validate_target_layout(read_lsblk(args.device), args.device)
            print(json.dumps(layout, indent=2, sort_keys=True))
            return 0

        if args.command == "verify-source":
            value = validate_sources(
                args.rootfs,
                args.kernel,
                args.dtb,
                args.kernel_release,
            )
            print(json.dumps(value, indent=2, sort_keys=True))
            return 0

        if args.command == "deploy":
            payload = read_lsblk(args.device)
            layout = validate_target_layout(
                payload,
                args.device,
                require_unmounted=not args.apply,
            )
            sources = validate_sources(
                args.rootfs,
                args.kernel,
                args.dtb,
                args.kernel_release,
            )
            plan = build_deployment_plan(layout, sources, args.mountpoint)
            print(json.dumps(plan, indent=2, sort_keys=True))
            if args.apply:
                apply_deployment(
                    plan,
                    args.rootfs,
                    args.kernel,
                    args.dtb,
                    args.mountpoint,
                )
            return 0

        if args.command == "write-media":
            target = validate_erasable_target(
                read_lsblk(args.device),
                args.device,
                allow_unsupported_capacity=args.allow_unsupported_capacity,
            )
            sources = validate_sanitized_baseline()
            plan = build_media_write_plan(target, sources)
            plan["allow_unsupported_capacity"] = args.allow_unsupported_capacity
            if not args.apply:
                print(json.dumps(plan, indent=2, sort_keys=True))
                return 0
            if args.confirm_erase != target["confirmation_token"]:
                raise ContractError(
                    "destructive write requires --confirm-erase to match the current target confirmation token"
                )
            result = write_sanitized_media(
                args.device,
                sources,
                expected_confirmation_token=args.confirm_erase,
                allow_unsupported_capacity=args.allow_unsupported_capacity,
            )
            print(json.dumps({"plan": plan, "result": result}, indent=2, sort_keys=True))
            return 0

        if args.command == "prepare-media":
            target = validate_erasable_target(
                read_lsblk(args.device),
                args.device,
                allow_unsupported_capacity=args.allow_unsupported_capacity,
            )
            plan = build_prepare_media_plan(
                target,
                args.mountpoint,
                allow_unsupported_capacity=args.allow_unsupported_capacity,
            )
            if not args.apply:
                print(json.dumps(plan, indent=2, sort_keys=True))
                return 0
            if args.confirm_erase != target["confirmation_token"]:
                raise ContractError(
                    "destructive preparation requires --confirm-erase to match the current target confirmation token"
                )
            result = prepare_media(
                args.device,
                args.mountpoint,
                expected_confirmation_token=args.confirm_erase,
                allow_unsupported_capacity=args.allow_unsupported_capacity,
            )
            print(json.dumps({"plan": plan, "result": result}, indent=2, sort_keys=True))
            return 0

    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
