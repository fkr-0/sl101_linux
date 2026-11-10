#!/usr/bin/env python3
"""Verify and package the *already built* SL101 production-derived dmafix1 candidate.

Host-only: no SSH, boot installation, flash, or Git mutation. The output is a
self-contained, checksum-checked RELEASE CANDIDATE, not a production promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/sl101-prod-dma-init-20261110"
RELEASE = "7.0.1-postmarketos-grate-dmafix1"
MODULE_SUBDIR = f"lib/modules/{RELEASE}"
OUT_DIR = LANE / "canonical-candidate"
OUT_ARCHIVE = OUT_DIR / "sl101-7.0.1-dmafix1-canonical-candidate.tar.zst"
EXPECTED = {
    "base_kernel": "794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1",
    "base_config": "6b09863a5f4356ce615f7d5d4cdecbba4cd2cc208c34125954af9534648f9248",
    "base_dtb": "01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0",
    "candidate_kernel": "315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541",
    "patch_applied": "b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b",
    "candidate_dtb": "01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_file(path: Path, expected: str | None = None) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing, linked, or nonregular file: {path}")
    if expected is not None and digest(path) != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")


def safe_relative(name: str) -> Path:
    p = PurePosixPath(name)
    if p.is_absolute() or not p.parts or ".." in p.parts or "." == str(p):
        raise ValueError(f"unsafe checksum path: {name!r}")
    return Path(*p.parts)


def verify_sums(folder: Path) -> int:
    index = folder / "SHA256SUMS"
    require_file(index)
    paths = set()
    count = 0
    for line in index.read_text().splitlines():
        digest_text, separator, name = line.partition("  ")
        if separator != "  " or len(digest_text) != 64:
            raise ValueError("malformed SHA256SUMS entry")
        rel = safe_relative(name.removeprefix("./"))
        if rel in paths:
            raise ValueError(f"duplicate SHA256SUMS entry: {rel}")
        paths.add(rel)
        require_file(folder / rel, digest_text)
        count += 1
    actual = {p.relative_to(folder) for p in folder.rglob("*") if p.is_file() and not p.is_symlink()}
    actual.discard(Path("SHA256SUMS"))
    if paths != actual:
        raise ValueError(f"incomplete checksums: missing={actual-paths}, spurious={paths-actual}")
    return count


def inspect_symlinks(folder: Path, *, allow_build: bool) -> None:
    linked = [p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_symlink()]
    permitted = {f"{MODULE_SUBDIR}/build"} if allow_build else set()
    if set(linked) != permitted:
        raise ValueError(f"unexpected symlink(s): {linked}")


def verify_release(folder: Path, *, raw: bool) -> dict:
    require_file(folder / f"boot/zImage-{RELEASE}", EXPECTED["candidate_kernel"])
    require_file(folder / "boot/tegra20-asus-sl101.dtb", EXPECTED["candidate_dtb"])
    require_file(folder / f"boot/config-{RELEASE}")
    require_file(folder / "patches/0002-dma-direct-zero-no-kmap.patch", EXPECTED["patch_applied"])
    config = (folder / f"boot/config-{RELEASE}").read_text()
    for required in (
        'CONFIG_LOCALVERSION="-postmarketos-grate-dmafix1"',
        "CONFIG_DRM_TEGRA=y",
        "CONFIG_TEGRA_IOMMU_GART=y",
        "CONFIG_BRCMFMAC=m",
        "CONFIG_ASUS_DOCKRAM=m",
    ):
        if required not in config:
            raise ValueError(f"candidate config lacks invariant: {required}")
    inspect_symlinks(folder, allow_build=raw)
    modules = sorted((folder / MODULE_SUBDIR).rglob("*.ko.zst"))
    if len(modules) != 587:
        raise ValueError(f"expected 587 modules, got {len(modules)}")
    require_file(folder / MODULE_SUBDIR / "modules.dep")
    if len((folder / MODULE_SUBDIR / "modules.dep").read_text().splitlines()) != 587:
        raise ValueError("modules.dep contains wrong number of modules")
    n = verify_sums(folder)
    return {"release": RELEASE, "modules": len(modules), "checksummed_files": n}


def verify_inputs() -> dict:
    base = LANE / "backup-prod-7.0.1/device-export/boot"
    for fn, key in (("vmlinuz", "base_kernel"), ("config", "base_config"),
                    ("tegra20-asus-sl101.dtb", "base_dtb")):
        require_file(base / fn, EXPECTED[key])
    patch = ROOT / "patches/linux-postmarketos-grate-7.0.1/dmafix1/0002-dma-direct-zero-no-kmap.patch"
    require_file(patch, EXPECTED["patch_applied"])
    # Patch 0001 is explicitly excluded: it does not fix the DMA-direct
    # no-kernel-mapping branch tested by the 216+108 hardware matrix.
    build_script = (LANE / "prepare-source.sh").read_text()
    if "0002-dma-direct-zero-no-kmap.patch" not in build_script:
        raise ValueError("build recipe no longer uses the selected patch")
    return verify_release(LANE / "release", raw=True)


def write_sums(folder: Path) -> None:
    entries = sorted(p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()
                     and p.name != "SHA256SUMS")
    (folder / "SHA256SUMS").write_text(
        "".join(f"{digest(p)}  ./{p.relative_to(folder).as_posix()}\n" for p in entries)
    )


def package() -> Path:
    info = verify_inputs()
    if OUT_ARCHIVE.exists():
        raise FileExistsError(f"candidate already exists; refusing overwrite: {OUT_ARCHIVE}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dmafix1-package-", dir=OUT_DIR) as tmp:
        temp_root = Path(tmp)
        dest = temp_root / "release"
        shutil.copytree(LANE / "release", dest, symlinks=True)
        (dest / MODULE_SUBDIR / "build").unlink()
        provenance = {
            "status": "candidate-not-production",
            "base": "linux-postmarketos-grate-7.0.1-r4",
            "base_source_commit": "bfffc6d6656e87f3de3aa4c09d852849081ef088",
            "release": RELEASE,
            "patches_applied": [{"path": "patches/linux-postmarketos-grate-7.0.1/dmafix1/0002-dma-direct-zero-no-kmap.patch",
                                  "sha256": EXPECTED["patch_applied"]}],
            "patches_excluded": ["0001-arm-dma-cma-no-kmap-attributes.patch"],
            "baseline_sha256": {k: EXPECTED[k] for k in ("base_kernel", "base_config", "base_dtb")},
            "kernel_sha256": EXPECTED["candidate_kernel"],
            "dtb_sha256": EXPECTED["candidate_dtb"],
            "modules": info["modules"],
            "hardware_evidence": "docs/sl101-0076-dontkmap-ab-20261109.md: 216/216 plus 108/108 first-use clean on one experimental boot",
            "release_gate": "repeat boot/graphics/video/Cog qualification pending",
        }
        (dest / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        write_sums(dest)
        verify_release(dest, raw=False)
        cmd = ["tar", "--zstd", "--sort=name", "--mtime=@0", "--owner=0",
               "--group=0", "--numeric-owner", "-C", str(temp_root), "-cf",
               str(OUT_ARCHIVE), "release"]
        subprocess.run(cmd, check=True)
    (OUT_ARCHIVE.with_suffix(OUT_ARCHIVE.suffix + ".sha256")).write_text(
        f"{digest(OUT_ARCHIVE)}  {OUT_ARCHIVE.name}\n"
    )
    return OUT_ARCHIVE


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", action="store_true", help="create a guarded, self-contained candidate archive")
    args = ap.parse_args()
    info = verify_inputs()
    print(json.dumps({"checks": "PASS", **info, "candidate_sha256": EXPECTED["candidate_kernel"]}, sort_keys=True))
    if args.package:
        path = package()
        print(json.dumps({"archive": str(path), "sha256": digest(path), "status": "candidate-only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
