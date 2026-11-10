#!/usr/bin/env python3
"""Fail-closed host preflight for a complete production-baseline SL101 kernel RC.

No network, no boot changes. Inspect the *built* module binaries as well as the
image, module ABI, production DTB and (optionally) four exact source patches.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile

MODULE_COUNT = 587
PATCHES = {
    "0001-arm-dma-cma-no-kmap-attributes.patch": "fbc0cf2e77a29dec2e82423e01a1ecdf54041c4d6e8fc1f7b37d2845e6853116",
    "0002-dma-direct-zero-no-kmap.patch": "b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b",
    "0003-vde-cached-capture-v2.patch": "83230997771fae22bc4983915197b0fcb8a95c550a3951334400784bfe72a176",
    "0004-vde-async-semaphore.patch": "d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def command(argv: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=input_bytes, capture_output=True, check=True)


def probe_module(path: Path, field: str) -> str:
    return command(["modinfo", "-F", field, str(path)]).stdout.decode()


def source_patches_errors(root: Path) -> list[str]:
    """Confirm the original patch bytes and strict reverse applicability."""
    issues: list[str] = []
    source = root / "source"
    marker = source / ".sl101-four-patches-applied"
    if not marker.is_file():
        return ["source four-patch marker absent"]
    for name, expected in PATCHES.items():
        patch_path = root / "patches" / name
        if not patch_path.is_file() or sha(patch_path) != expected:
            issues.append(f"missing/changed source patch: {name}")
            continue
        try:
            command(["patch", "--batch", "--dry-run", "--fuzz=0", "-R",
                     "-p1", "-d", str(source)], input_bytes=patch_path.read_bytes())
        except (OSError, subprocess.CalledProcessError):
            issues.append(f"source does not contain exact applied patch: {name}")
    return issues


def verify(root: Path, release: str,
           expected_dtb_sha: str | None = None,
           require_source_patches: bool = False) -> list[str]:
    issues: list[str] = []
    image = root / "out/arch/arm/boot/zImage"
    dtb = root / "out/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb"
    version = root / "out/include/config/kernel.release"
    modpath = root / "modules/lib/modules" / release

    if not version.is_file() or version.read_text().strip() != release:
        issues.append("wrong/missing release marker")
    if not image.is_file() or image.stat().st_size < 1024 * 1024:
        issues.append("missing/truncated zImage")
    if not dtb.is_file() or (expected_dtb_sha and sha(dtb) != expected_dtb_sha):
        issues.append("missing or mismatched production DTB")

    modules = sorted(modpath.glob("kernel/**/*.ko.zst")) if modpath.is_dir() else []
    if len(modules) != MODULE_COUNT:
        issues.append(f"missing/incomplete matching module tree: {len(modules)} modules (expected {MODULE_COUNT})")
    if not (modpath / "modules.dep").is_file():
        issues.append("missing depmod index")
    for path in modules:
        if path.is_symlink():
            issues.append(f"symlinked module forbidden: {path.name}")
            continue
        try:
            vermagic = probe_module(path, "vermagic")
            if not vermagic.startswith(release + " "):
                issues.append(f"module vermagic mismatch: {path.name}")
        except (OSError, subprocess.CalledProcessError):
            issues.append(f"unreadable or malformed module: {path.name}")
        if len(issues) > 30:
            break

    vde = modpath / "kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"
    if not vde.is_file():
        issues.append("tegra-vde module absent")
    else:
        try:
            params = probe_module(vde, "parm")
            if "cached_capture" not in params:
                issues.append("VDE cached_capture parameter ABSENT (VDE v2 patch missing)")
            # The async decode ownership fix produces these imports, unlike
            # the stock VDE mutex-locking module. It is a binary, not just
            # source-file, assertion.
            decompressed = command(["zstdcat", str(vde)]).stdout
            with tempfile.TemporaryDirectory(prefix="sl101-vde-check-") as tempdir:
                uncompressed = Path(tempdir) / "tegra-vde.ko"
                uncompressed.write_bytes(decompressed)
                syms = command(["nm", "-u", str(uncompressed)]).stdout.decode()
            imports = set(re.findall(r"\bU\s+(\w+)", syms))
            if not {"down", "down_interruptible", "up"} <= imports or "mutex_lock_interruptible" in imports:
                issues.append("VDE async-semaphore symbols absent (owner-lock patch not compiled)")
        except (OSError, subprocess.CalledProcessError) as exc:
            issues.append(f"VDE module binary inspection failed: {exc}")

    if require_source_patches:
        issues.extend(source_patches_errors(root))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--expected-dtb-sha", default="")
    parser.add_argument("--require-source-patches", action="store_true")
    args = parser.parse_args()
    issues = verify(args.root, args.release, args.expected_dtb_sha or None,
                    require_source_patches=args.require_source_patches)
    for message in issues:
        print("BLOCKER:", message, file=sys.stderr)
    if issues:
        return 2
    print(f"KERNEL_STAGE_PREFLIGHT_OK release={args.release} modules={MODULE_COUNT} VDE=cached+async")
    return 0


if __name__ == "__main__":
    sys.exit(main())
