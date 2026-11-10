#!/usr/bin/env python3
"""Package the four-patch production-baseline candidate, host only."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/sl101-prod-dmavde-rc3-20261110"
REL = "7.0.1-postmarketos-grate-dmavde1"
DTB_SHA = "01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0"
ARCHIVE = LANE / "sl101-7.0.1-dmavde1-four-patch-candidate.tar.zst"
RELEASE = LANE / "release"
sys.path.insert(0, str(ROOT / "deploy/ansible/tools"))
from verify_kernel import PATCHES, sha, verify  # noqa E402


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def checked(argv: list[str], **kw) -> None:
    subprocess.run(argv, check=True, **kw)


def main() -> None:
    issues = verify(LANE, REL, DTB_SHA, require_source_patches=True)
    require(not issues, "Candidate preflight failed: " + "; ".join(issues))
    require(not ARCHIVE.exists() and not RELEASE.exists(), "Candidate already exists; refuse overwrite")
    boot = RELEASE / "boot"
    mods = RELEASE / f"lib/modules/{REL}"
    patches = RELEASE / "patches"
    boot.mkdir(parents=True)
    patches.mkdir(parents=True)
    shutil.copytree(LANE / f"modules/lib/modules/{REL}", mods, symlinks=True)
    for child in ("build", "source"):
        link = mods / child
        if link.is_symlink():
            link.unlink()
    require(not any(p.is_symlink() for p in RELEASE.rglob("*")), "Release must be self-contained")
    shutil.copy2(LANE / "out/arch/arm/boot/zImage", boot / f"zImage-{REL}")
    shutil.copy2(LANE / "out/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb",
                 boot / "tegra20-asus-sl101.dtb")
    shutil.copy2(LANE / "out/.config", boot / f"config-{REL}")
    shutil.copy2(LANE / "backup/production.config", boot / "production.config")
    for filename, expected in PATCHES.items():
        source = LANE / "patches" / filename
        require(sha(source) == expected, f"Source patch changed: {filename}")
        shutil.copy2(source, patches / filename)
    checked(["depmod", "-b", str(RELEASE), "-a", REL])
    vde = mods / "kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"
    image = boot / f"zImage-{REL}"
    metadata = {
        "schema": "sl101-kernel-dmavde-four-patch-rc-v1",
        "release": REL,
        "production_baseline": "linux-postmarketos-grate-7.0.1-r4",
        "source_archive_sha512": "fa6a723db93d0c4c799ca8fb69a37ce13cc98a80ff688bc45dea7bd6d36df05b8f0deaa15a416e271a4ea0c5bb2097e63fc2d0a02903f11e6c404fbec82718a2",
        "production_config_sha256": sha(boot / "production.config"),
        "dtb_sha256": sha(boot / "tegra20-asus-sl101.dtb"),
        "zimage_sha256": sha(image),
        "tegra_vde_module_sha256": sha(vde),
        "module_count": len(list(mods.rglob("*.ko.zst"))),
        "patches": [{"name": name, "sha256": value} for name, value in PATCHES.items()],
        "vde_cached_capture": "compiled; default off",
        "vde_async_lock": "compiled; host verified; hardware unqualified",
        "cma_alias": "experimental; unqualified",
        "boot_status": "nondefault candidate; not flashed, not staged or rebooted",
    }
    require(metadata["module_count"] == 587, "Incomplete modules")
    (RELEASE / "PROVENANCE.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    files = sorted((p for p in RELEASE.rglob("*") if p.is_file()), key=lambda p: p.as_posix())
    (RELEASE / "SHA256SUMS").write_text("".join(
        f"{sha(p)}  ./{p.relative_to(RELEASE).as_posix()}\n" for p in files
    ))
    with (LANE / "evidence/release-verification.log").open("w") as stream:
        checked(["sha256sum", "-c", "SHA256SUMS"], cwd=RELEASE, stdout=stream)
    checked(["tar", "--zstd", "--sort=name", "--mtime=@0", "--owner=0",
             "--group=0", "--numeric-owner", "-cf", str(ARCHIVE), "-C", str(LANE), "release"])
    (LANE / f"{ARCHIVE.name}.sha256").write_text(f"{sha(ARCHIVE)}  {ARCHIVE.name}\n")
    print(json.dumps({"release": REL, "archive": str(ARCHIVE),
                      "archive_sha256": sha(ARCHIVE), "module_count": 587,
                      "zimage_sha256": sha(image),
                      "tegra_vde_module_sha256": sha(vde)}, indent=2))


if __name__ == "__main__":
    main()
