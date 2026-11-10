#!/usr/bin/env python3
"""Package the independent three-patch minus-CMA benchmark control, host only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/sl101-prod-dmavde-minus-cma-20261110"
FULL = ROOT / "work/sl101-prod-dmavde-rc3-20261110"
REL = "7.0.1-postmarketos-grate-dmavde1-minus-cma"
CONTROL_LABEL = "7.0.1-pmos-grate-dmavde1-minus-cma"
RC_LABEL = "7.0.1-pmos-grate-dmavde1"
DTB_SHA = "01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0"
SOURCE_ARCHIVE_SHA512 = "fa6a723db93d0c4c799ca8fb69a37ce13cc98a80ff688bc45dea7bd6d36df05b8f0deaa15a416e271a4ea0c5bb2097e63fc2d0a02903f11e6c404fbec82718a2"
ARCHIVE = LANE / "sl101-7.0.1-pmos-grate-dmavde1-minus-cma-benchmark.tar.zst"
RELEASE = LANE / "release"
sys.path.insert(0, str(ROOT / "deploy/ansible/tools"))
from verify_kernel import PATCHES, sha, verify  # noqa E402

OMITTED = "0001-arm-dma-cma-no-kmap-attributes.patch"
CONTROL_PATCHES = {name: value for name, value in PATCHES.items() if name != OMITTED}


def require(condition: bool, error: str) -> None:
    if not condition:
        raise RuntimeError(error)


def run(argv: list[str], **kwargs) -> None:
    subprocess.run(argv, check=True, **kwargs)


def verify_source() -> None:
    require((LANE / "source/.sl101-three-patches-minus-cma-applied").exists(),
            "Unverified benchmark control source")
    require(not (LANE / "source/.sl101-four-patches-applied").exists(),
            "CMA-full marker present on benchmark control source")
    require(set(p.name for p in (LANE / "patches").glob("*.patch")) == set(CONTROL_PATCHES),
            "Control has unexpected/missing patch: must have exactly 0002, 0003, 0004")
    for name, digest in CONTROL_PATCHES.items():
        expected = ROOT / "patches/linux-postmarketos-grate-7.0.1/dmavde1" / name
        source = LANE / "patches" / name
        require(sha(source) == digest and sha(expected) == digest,
                "Patch missing or drifted: " + name)
        check = subprocess.run(
            ["patch", "--batch", "--fuzz=0", "--dry-run", "-R", "-p1",
             "-d", str(LANE / "source")],
            input=source.read_bytes(), capture_output=True,
        )
        require(check.returncode == 0, "Three-patch reverse dry-run failed: " + name)
    omitted = FULL / "patches" / OMITTED
    check = subprocess.run(
        ["patch", "--batch", "--fuzz=0", "--dry-run", "-p1",
         "-d", str(LANE / "source")],
        input=omitted.read_bytes(), capture_output=True,
    )
    require(check.returncode == 0, "CMA patch not cleanly applicable to control")


def build_release() -> None:
    require(not RELEASE.exists() and not ARCHIVE.exists(),
            "Release/benchmark archive already exists; refuse overwrite")
    verify_source()
    require(sha(LANE / "backup/production.config") == sha(FULL / "backup/production.config"),
            "Productive base kernel config mismatch")
    errors = verify(LANE, REL, DTB_SHA, require_source_patches=False)
    require(not errors, "Compiled benchmark kernel failed verification: " + "; ".join(errors))

    # Validate config differences. The *only* acceptable difference is
    # CONFIG_LOCALVERSION, which ensures distinct module ABI and rollback.
    def normalized(path: Path) -> str:
        return "\n".join(line for line in path.read_text().splitlines()
                         if not line.startswith("CONFIG_LOCALVERSION="))
    require(normalized(LANE / "out/.config") == normalized(FULL / "out/.config"),
            "Kconfig differences beyond LOCALVERSION - invalid A/B benchmark")
    require(sha(LANE / "out/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb") == DTB_SHA,
            "Control DTB mismatch against RC")

    boot = RELEASE / "boot"
    mods = RELEASE / f"lib/modules/{REL}"
    patches = RELEASE / "patches"
    boot.mkdir(parents=True)
    patches.mkdir(parents=True)

    shutil.copytree(LANE / f"modules/lib/modules/{REL}", mods, symlinks=True)
    for name in ("source", "build"):
        p = mods / name
        if p.is_symlink():
            p.unlink()
    require(not any(p.is_symlink() for p in RELEASE.rglob("*")),
            "Refuse symlinks in portable benchmark release")

    zimage = boot / f"zImage-{REL}"
    dtb = boot / "tegra20-asus-sl101.dtb"
    config = boot / f"config-{REL}"
    shutil.copy2(LANE / "out/arch/arm/boot/zImage", zimage)
    shutil.copy2(LANE / "out/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb", dtb)
    shutil.copy2(LANE / "out/.config", config)
    shutil.copy2(LANE / "backup/production.config", boot / "production.config")
    for name in CONTROL_PATCHES:
        shutil.copy2(LANE / "patches" / name, patches / name)

    run(["depmod", "-b", str(RELEASE), "-a", REL])
    vde = mods / "kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"
    provenance = {
        "schema": "sl101-dmavde1-minus-cma-benchmark-v1",
        "label": CONTROL_LABEL,
        "kernel_release": REL,
        "role": "BENCHMARK_CONTROL_NOT_PRODUCTION_DEFAULT",
        "comparison_label": RC_LABEL,
        "comparison_kernel_release": "7.0.1-postmarketos-grate-dmavde1",
        "comparison_archive_sha256": "d7781381ee52efb3be6edf885857b2800a4e1e00ce989a63a00955035183d8dc",
        "source_archive_sha512": SOURCE_ARCHIVE_SHA512,
        "productive_base_config_sha256": sha(boot / "production.config"),
        "dtb_sha256": sha(dtb),
        "zimage_sha256": sha(zimage),
        "vde_module_sha256": sha(vde),
        "module_count": len(list(mods.rglob("*.ko.zst"))),
        "patches": [{"name": n, "sha256": h} for n, h in CONTROL_PATCHES.items()],
        "excluded_patch": {"name": OMITTED, "sha256": PATCHES[OMITTED]},
        "source_diff_allowlist": ["arch/arm/mm/dma-mapping.c"],
        "vde_cached_capture": "compiled; default off",
        "vde_async_lock": "compiled; host verified",
        "boot_status": "not flashed, staged, rebooted or hardware qualified",
        "performance": "benchmark control; no result claimed",
    }
    require(provenance["module_count"] == 587, "incomplete module inventory")
    (RELEASE / "PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n")

    files = sorted(
        (p for p in RELEASE.rglob("*") if p.is_file() and p.name != "SHA256SUMS"),
        key=lambda p: p.as_posix())
    (RELEASE / "SHA256SUMS").write_text("".join(
        f"{sha(p)}  ./{p.relative_to(RELEASE).as_posix()}\n" for p in files))
    with (LANE / "evidence/release-verification.log").open("w") as log:
        run(["sha256sum", "-c", "SHA256SUMS"], cwd=RELEASE, stdout=log)
    run(["tar", "--zstd", "--sort=name", "--mtime=@0", "--owner=0",
         "--group=0", "--numeric-owner", "-cf", str(ARCHIVE),
         "-C", str(LANE), "release"])
    digest = sha(ARCHIVE)
    (LANE / (ARCHIVE.name + ".sha256")).write_text(
        f"{digest}  {ARCHIVE.name}\n")
    (LANE / "evidence/package-result.json").write_text(
        json.dumps({
            "label": CONTROL_LABEL, "kernel_release": REL,
            "archive": str(ARCHIVE), "archive_sha256": digest,
            "zimage_sha256": sha(zimage), "vde_module_sha256": sha(vde),
            "module_count": 587, "source_patches": 3,
        }, indent=2, sort_keys=True) + "\n")
    print((LANE / "evidence/package-result.json").read_text(), end="")


if __name__ == "__main__":
    build_release()
