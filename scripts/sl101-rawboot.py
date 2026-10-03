#!/usr/bin/env python3
"""Guarded ASUS SL101 raw LNX boot-slot updater.

The persistent SL101 Linux path uses an Android boot header followed by a
zImage with an appended DTB. This tool verifies that relationship and treats
header+payload as one transaction.

Writes require explicit live-evidence LNX offset and slot size, exact expected
current kernel/DTB hashes, a full-slot backup, and a content-derived
confirmation token. It never partitions or reformats eMMC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ANDROID_MAGIC = b"ANDROID!"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"
ZIMAGE_MAGIC = b"\x18\x28\x6f\x01"
CHUNK = 1024 * 1024
MAX_DTB = 2 * 1024 * 1024


class ContractError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_exact(handle, offset: int, size: int) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        raise ContractError(f"short read at {offset}: {len(data)}/{size}")
    return data


def parse_android_header(page: bytes) -> dict:
    if page[:8] != ANDROID_MAGIC:
        raise ContractError("missing ANDROID! boot header")
    values = struct.unpack_from("<10I", page, 8)
    (
        kernel_size,
        kernel_addr,
        ramdisk_size,
        ramdisk_addr,
        second_size,
        second_addr,
        tags_addr,
        page_size,
        dt_size,
        unused,
    ) = values
    if page_size < 512 or page_size > 65536 or page_size & (page_size - 1):
        raise ContractError(f"implausible page size {page_size}")
    return dict(
        kernel_size=kernel_size,
        kernel_addr=kernel_addr,
        ramdisk_size=ramdisk_size,
        ramdisk_addr=ramdisk_addr,
        second_size=second_size,
        second_addr=second_addr,
        tags_addr=tags_addr,
        page_size=page_size,
        dt_size=dt_size,
        unused=unused,
    )


def zimage_size(handle, offset: int) -> int:
    header = read_exact(handle, offset, 0x30)
    if header[0x24:0x28] != ZIMAGE_MAGIC:
        raise ContractError(f"no ARM zImage magic at {offset}")
    start, end = struct.unpack_from("<II", header, 0x28)
    size = end - start
    if not 1024 * 1024 <= size <= 32 * 1024 * 1024:
        raise ContractError(f"implausible zImage size {size}")
    return size


def dtb_size(handle, offset: int) -> int:
    header = read_exact(handle, offset, 8)
    if header[:4] != FDT_MAGIC:
        raise ContractError(f"no FDT magic at {offset}")
    size = struct.unpack(">I", header[4:8])[0]
    if not 40 <= size <= MAX_DTB:
        raise ContractError(f"implausible DTB size {size}")
    return size


def inspect(device: Path, lnx_offset: int) -> dict:
    with device.open("rb", buffering=0) as handle:
        first = read_exact(handle, lnx_offset, 2048)
        android_header = parse_android_header(first)
        page_size = android_header["page_size"]
        header = read_exact(handle, lnx_offset, page_size)
        kernel_offset = lnx_offset + page_size
        kernel_size = zimage_size(handle, kernel_offset)
        kernel_bytes = read_exact(handle, kernel_offset, kernel_size)
        dtb_offset = kernel_offset + kernel_size
        dtb_len = dtb_size(handle, dtb_offset)
        dtb_bytes = read_exact(handle, dtb_offset, dtb_len)

    payload_size = kernel_size + dtb_len
    if android_header["kernel_size"] != payload_size:
        raise ContractError(
            f"Android header kernel_size {android_header['kernel_size']} "
            f"!= zImage+DTB {payload_size}"
        )
    return dict(
        device=str(device),
        lnx_offset=lnx_offset,
        page_size=page_size,
        header_sha256=sha256_bytes(header),
        header_kernel_size=android_header["kernel_size"],
        kernel_offset=kernel_offset,
        kernel_size=kernel_size,
        kernel_sha256=sha256_bytes(kernel_bytes),
        dtb_offset=dtb_offset,
        dtb_size=dtb_len,
        dtb_sha256=sha256_bytes(dtb_bytes),
        payload_size=payload_size,
        total_used=page_size + payload_size,
        dtb_has_sl101_ec=(
            b"embedded-controller@19" in dtb_bytes
            or b"asus,sl101-ec-dock" in dtb_bytes
        ),
    )


def validate_target(kernel: Path, dtb: Path) -> dict:
    kernel_bytes = kernel.read_bytes()
    dtb_bytes = dtb.read_bytes()
    if len(kernel_bytes) < 0x30 or kernel_bytes[0x24:0x28] != ZIMAGE_MAGIC:
        raise ContractError("target is not ARM zImage")
    zimage_len = struct.unpack_from("<I", kernel_bytes, 0x2C)[0] - struct.unpack_from(
        "<I", kernel_bytes, 0x28
    )[0]
    if zimage_len != len(kernel_bytes):
        raise ContractError(
            f"target zImage declared size {zimage_len} != file size {len(kernel_bytes)}"
        )
    if len(dtb_bytes) < 8 or dtb_bytes[:4] != FDT_MAGIC:
        raise ContractError("target is not DTB")
    dtb_len = struct.unpack(">I", dtb_bytes[4:8])[0]
    if dtb_len != len(dtb_bytes):
        raise ContractError(
            f"target DTB declared size {dtb_len} != file size {len(dtb_bytes)}"
        )
    return dict(
        kernel=str(kernel),
        kernel_size=len(kernel_bytes),
        kernel_sha256=sha256_bytes(kernel_bytes),
        dtb=str(dtb),
        dtb_size=len(dtb_bytes),
        dtb_sha256=sha256_bytes(dtb_bytes),
        payload_size=len(kernel_bytes) + len(dtb_bytes),
        dtb_has_sl101_ec=(
            b"embedded-controller@19" in dtb_bytes
            or b"asus,sl101-ec-dock" in dtb_bytes
        ),
    )


def token(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return "SL101-RAWBOOT-" + hashlib.sha256(raw).hexdigest()[:20]


def make_plan(args) -> dict:
    current = inspect(Path(args.device), args.lnx_offset)
    if current["kernel_sha256"] != args.expected_kernel_sha256:
        raise ContractError(
            f"current kernel hash mismatch: {current['kernel_sha256']}"
        )
    if current["dtb_sha256"] != args.expected_dtb_sha256:
        raise ContractError(f"current DTB hash mismatch: {current['dtb_sha256']}")

    target = validate_target(Path(args.kernel), Path(args.dtb))
    if current["total_used"] > args.slot_size:
        raise ContractError("declared slot smaller than current image")
    if current["page_size"] + target["payload_size"] > args.slot_size:
        raise ContractError("target does not fit declared slot")

    plan = dict(
        contract="sl101-rawboot-v2",
        device=args.device,
        lnx_offset=args.lnx_offset,
        slot_size=args.slot_size,
        current=current,
        target=target,
        new_header_kernel_size=target["payload_size"],
        tail_policy="leave bytes after new payload untouched",
    )
    plan["confirmation_token"] = token(plan)
    return plan


def backup_slot(
    device: Path,
    offset: int,
    size: int,
    destination: Path,
    current: dict,
) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    image = destination / "slot-backup.bin"
    manifest = destination / "slot-backup.json"
    if image.exists() or manifest.exists():
        raise ContractError("backup destination already contains backup files")

    with device.open("rb", buffering=0) as source, image.open("wb") as output:
        source.seek(offset)
        left = size
        while left:
            chunk = source.read(min(CHUNK, left))
            if not chunk:
                raise ContractError("short read while backing up")
            output.write(chunk)
            left -= len(chunk)
        output.flush()
        os.fsync(output.fileno())

    info = dict(
        contract="sl101-rawboot-backup-v2",
        device=str(device),
        lnx_offset=offset,
        slot_size=size,
        slot_sha256=sha256_file(image),
        current=current,
    )
    manifest.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
    return info


def write_target(device: Path, plan: dict, kernel: Path, dtb: Path) -> None:
    page = bytearray()
    with device.open("rb", buffering=0) as handle:
        page.extend(
            read_exact(
                handle,
                plan["lnx_offset"],
                plan["current"]["page_size"],
            )
        )
    struct.pack_into("<I", page, 8, plan["target"]["payload_size"])
    payload = bytes(page) + kernel.read_bytes() + dtb.read_bytes()
    with device.open("r+b", buffering=0) as handle:
        handle.seek(plan["lnx_offset"])
        if handle.write(payload) != len(payload):
            raise ContractError("short write")
        handle.flush()
        os.fsync(handle.fileno())


def verify_target(device: Path, plan: dict) -> dict:
    got = inspect(device, plan["lnx_offset"])
    target = plan["target"]
    if (
        got["kernel_sha256"] != target["kernel_sha256"]
        or got["dtb_sha256"] != target["dtb_sha256"]
    ):
        raise ContractError("target readback hash mismatch")
    if got["header_kernel_size"] != target["payload_size"]:
        raise ContractError("header kernel_size readback mismatch")
    return got


def restore(device: Path, manifest: Path, confirm: str) -> dict:
    info = json.loads(manifest.read_text())
    image = manifest.with_name("slot-backup.bin")
    if not image.is_file() or sha256_file(image) != info["slot_sha256"]:
        raise ContractError("backup missing or hash mismatch")

    contract = dict(
        contract="sl101-rawboot-restore-v2",
        device=str(device),
        lnx_offset=info["lnx_offset"],
        slot_size=info["slot_size"],
        slot_sha256=info["slot_sha256"],
    )
    required_token = token(contract)
    if confirm != required_token:
        raise ContractError(
            f"restore confirmation mismatch; required token: {required_token}"
        )

    backup = image.read_bytes()
    if len(backup) != info["slot_size"]:
        raise ContractError("backup length mismatch")
    with device.open("r+b", buffering=0) as handle:
        handle.seek(info["lnx_offset"])
        if handle.write(backup) != len(backup):
            raise ContractError("short restore write")
        handle.flush()
        os.fsync(handle.fileno())

    with device.open("rb", buffering=0) as handle:
        readback = read_exact(handle, info["lnx_offset"], info["slot_size"])
    if sha256_bytes(readback) != info["slot_sha256"]:
        raise ContractError("restore readback mismatch")
    return dict(restored=True, **contract)


def add_plan_args(parser) -> None:
    parser.add_argument("--device", required=True)
    parser.add_argument("--lnx-offset", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--slot-size", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--dtb", required=True)
    parser.add_argument("--expected-kernel-sha256", required=True)
    parser.add_argument("--expected-dtb-sha256", required=True)


def parser():
    argument_parser = argparse.ArgumentParser()
    subparsers = argument_parser.add_subparsers(dest="cmd", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--device", required=True)
    inspect_parser.add_argument(
        "--lnx-offset",
        required=True,
        type=lambda value: int(value, 0),
    )

    plan_parser = subparsers.add_parser("plan")
    add_plan_args(plan_parser)

    write_parser = subparsers.add_parser("write")
    add_plan_args(write_parser)
    write_parser.add_argument("--backup-dir", required=True)
    write_parser.add_argument("--confirm", required=True)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--device", required=True)
    restore_parser.add_argument("--manifest", required=True)
    restore_parser.add_argument("--confirm", required=True)
    return argument_parser


def main() -> int:
    args = parser().parse_args()
    try:
        if args.cmd == "inspect":
            output = inspect(Path(args.device), args.lnx_offset)
        elif args.cmd == "plan":
            output = make_plan(args)
        elif args.cmd == "write":
            plan = make_plan(args)
            if args.confirm != plan["confirmation_token"]:
                raise ContractError(
                    "write confirmation mismatch; required token: "
                    + plan["confirmation_token"]
                )
            backup = backup_slot(
                Path(args.device),
                args.lnx_offset,
                args.slot_size,
                Path(args.backup_dir),
                plan["current"],
            )
            write_target(
                Path(args.device),
                plan,
                Path(args.kernel),
                Path(args.dtb),
            )
            output = dict(
                written=True,
                plan=plan,
                backup=backup,
                readback=verify_target(Path(args.device), plan),
            )
        elif args.cmd == "restore":
            output = restore(Path(args.device), Path(args.manifest), args.confirm)
        else:
            raise AssertionError(args.cmd)
    except (OSError, ValueError, json.JSONDecodeError, ContractError) as error:
        print("ERROR:", error, file=sys.stderr)
        return 2

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
