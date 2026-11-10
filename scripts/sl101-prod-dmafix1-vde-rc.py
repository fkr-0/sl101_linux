#!/usr/bin/env python3
"""Build a complete, portable dmafix1 + VDE-owner-lock production candidate.

The VDE patch is an independently compiled MODULE against the exact dmafix1
.config/Module.symvers, not a new built-in kernel change. Keep all 587 modules
and the proven kernel image; replace ONLY tegra-vde.ko.zst, refresh depmod,
include BOTH source patches and hash all artifacts. Host only.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work/sl101-prod-dma-init-20261110"
LANE = ROOT / "work/sl101-dmafix1-vde-rc2-20261110"
REL = "7.0.1-postmarketos-grate-dmafix1"
MOD = Path(f"lib/modules/{REL}/kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst")
VDE_SRC = ROOT / ("work/sl101-vde-modfix2-20261110/stage/lib/modules/"
                  f"{REL}/updates/tegra-vde.ko.zst")
VDE_PATCH = ROOT / ("patches/linux-postmarketos-grate-7.0.1/vde-modfix2/"
                    "0001-media-tegra-vde-async-semaphore.patch")
DMA_PATCH = ROOT / ("patches/linux-postmarketos-grate-7.0.1/dmafix1/"
                    "0002-dma-direct-zero-no-kmap.patch")
OLD_VDE_SHA = "1071962fe35550908ae9f02c28596a9321a0bd3c4de5aca1c6ad8f908dc9a96c"
NEW_VDE_SHA = "9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f"
VDE_PATCH_SHA = "d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de"
DMA_PATCH_SHA = "b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b"
IMAGE_SHA = "315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541"
ARCHIVE = LANE / "sl101-dmafix1-vde-rc2-complete.tar.zst"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(cond, why):
    if not cond:
        raise ValueError(why)


def modinfo(path, field):
    return subprocess.check_output(["modinfo", "-F", field, str(path)], text=True).strip()


def preflight():
    # Base package verifier owns stock hashes and config invariant checks.
    module_path = ROOT / "scripts/sl101-prod-dmafix1-candidate.py"
    spec = importlib.util.spec_from_file_location("sl101_dmafix1_base", module_path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    base = m.verify_inputs()
    require(base["modules"] == 587, "base has wrong module count")
    require(sha(BASE / "release" / MOD) == OLD_VDE_SHA, "base VDE changed")
    require(VDE_SRC.is_file() and sha(VDE_SRC) == NEW_VDE_SHA, "VDE candidate binary mismatch")
    require(sha(DMA_PATCH) == DMA_PATCH_SHA, "DMA patch changed")
    require(sha(VDE_PATCH) == VDE_PATCH_SHA, "VDE patch changed")
    require(modinfo(VDE_SRC, "vermagic").startswith(REL + " "), "VDE vermagic mismatch")
    for field in ("depends", "alias"):
        require(modinfo(VDE_SRC, field) == modinfo(BASE / "release" / MOD, field),
                f"module {field} changed; full dependency rebuild required")
    return m


def generate_sums(folder):
    paths = sorted((p for p in folder.rglob("*") if p.is_file() and p.name != "SHA256SUMS"),
                   key=lambda p: p.as_posix())
    (folder / "SHA256SUMS").write_text("".join(
        f"{sha(p)}  ./{p.relative_to(folder).as_posix()}\n" for p in paths
    ))


def create():
    m = preflight()
    require(not ARCHIVE.exists() and not (LANE / "release").exists(),
            "complete RC already exists; refuse overwrite")
    LANE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compose-", dir=LANE) as tmp:
        temp = Path(tmp)
        dst = temp / "release"
        shutil.copytree(BASE / "release", dst, symlinks=True)
        buildlink = dst / f"lib/modules/{REL}/build"
        require(buildlink.is_symlink(), "unexpected base module build link")
        buildlink.unlink()
        target = dst / MOD
        shutil.copy2(VDE_SRC, target)
        require(sha(target) == NEW_VDE_SHA, "VDE module substitution failed")
        shutil.copy2(VDE_PATCH, dst / "patches/0003-tegra-vde-async-semaphore.patch")
        # Do not rely on stale binary depmod indices after changing the module.
        # Depmod runs against a complete, isolated root, never the host's own modules.
        subprocess.run(["depmod", "-b", str(dst), "-a", REL], check=True)
        # Project's base verifier knows the exact config and forbids symlinks.
        m.inspect_symlinks(dst, allow_build=False)
        require(sha(dst / f"boot/zImage-{REL}") == IMAGE_SHA, "kernel image drift")
        require(len(list((dst / f"lib/modules/{REL}").rglob("*.ko.zst"))) == 587,
                "not a complete 587-module tree")
        manifest = {
            "schema": "sl101-dmafix1-vde-complete-candidate-v1",
            "release": REL,
            "base": "linux-postmarketos-grate-7.0.1-r4",
            "status": "candidate-not-permanent-flash",
            "kernel_sha256": IMAGE_SHA,
            "vde_module_old_sha256": OLD_VDE_SHA,
            "vde_module_new_sha256": NEW_VDE_SHA,
            "module_count": 587,
            "source_patches": [
                {"name": "0002-dma-direct-zero-no-kmap.patch", "sha256": DMA_PATCH_SHA},
                {"name": "0003-tegra-vde-async-semaphore.patch", "sha256": VDE_PATCH_SHA},
            ],
            "excluded": ["0001-arm-dma-cma-no-kmap-attributes.patch"],
            "boot": "APX/RAM-U-Boot SD extlinux default plus one-shot kexec; eMMC untouched",
            "hardware_gate": "DMA 324/324 prior; VDE-owner warning fix awaits reboot/device test",
        }
        (dst / "PROVENANCE.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        generate_sums(dst)
        m.verify_sums(dst)
        require(sha(dst / MOD) == NEW_VDE_SHA, "final candidate VDE hash drift")
        shutil.move(str(dst), str(LANE / "release"))
    # Pack from a complete checksum-verified release. Deterministic metadata.
    subprocess.run(["tar", "--zstd", "--sort=name", "--mtime=@0", "--owner=0",
                    "--group=0", "--numeric-owner", "-cf", str(ARCHIVE),
                    "-C", str(LANE), "release"], check=True)
    (LANE / (ARCHIVE.name + ".sha256")).write_text(f"{sha(ARCHIVE)}  {ARCHIVE.name}\n")
    print(json.dumps({"archive":str(ARCHIVE), "sha256":sha(ARCHIVE),
                      "image_sha256":IMAGE_SHA, "vde_sha256":NEW_VDE_SHA,
                      "module_count":587},sort_keys=True))


def verify():
    m = preflight()
    dst = LANE / "release"
    require(dst.is_dir() and ARCHIVE.is_file(), "complete RC not packaged")
    require(sha(dst / MOD) == NEW_VDE_SHA, "composed VDE hash mismatch")
    require(sha(dst / "patches/0003-tegra-vde-async-semaphore.patch") == VDE_PATCH_SHA,
            "VDE patch absent")
    require(sha(dst / f"boot/zImage-{REL}") == IMAGE_SHA, "kernel drift")
    require(len(list((dst / f"lib/modules/{REL}").rglob("*.ko.zst"))) == 587,
            "module inventory incomplete")
    m.inspect_symlinks(dst, allow_build=False)
    count = m.verify_sums(dst)
    require(count >= 608, "checksum inventory incomplete")
    index = (LANE / (ARCHIVE.name + ".sha256")).read_text()
    require(index == f"{sha(ARCHIVE)}  {ARCHIVE.name}\n", "archive checksum mismatch")
    print(json.dumps({"checks":"PASS", "file_count":count, "archive_sha256":sha(ARCHIVE),
                      "vde_sha256":NEW_VDE_SHA}, sort_keys=True))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--create", action="store_true")
    args = p.parse_args()
    create() if args.create else verify()
