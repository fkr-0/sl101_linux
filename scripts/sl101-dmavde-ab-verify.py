#!/usr/bin/env python3
"""Fail-closed host-side A/B equivalence gate for CMA vs minus-CMA RC.

Proofs:
  1. Exact three common source patches, the fourth is CMA only.
  2. The actual two kernel source files differ by the CMA patch exactly.
  3. Optional expensive --deep-source tests all source-tree bytes.
  4. Kernel Kconfig differs ONLY in CONFIG_LOCALVERSION.
  5. Both kernel builds have the same DTB/587 module filenames, complete
     587-version-correct modules, identical VDE features, and separate UTS.
  6. Both portable archives and manifests have validated checksums.

No device access or alterations.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "work/sl101-prod-dmavde-rc3-20261110"
B = ROOT / "work/sl101-prod-dmavde-minus-cma-20261110"
A_REL = "7.0.1-postmarketos-grate-dmavde1"
B_REL = "7.0.1-postmarketos-grate-dmavde1-minus-cma"
CMA = "0001-arm-dma-cma-no-kmap-attributes.patch"
PATCH_PATH = ROOT / "patches/linux-postmarketos-grate-7.0.1/dmavde1"
DTB_SHA = "01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0"
RC_ARCHIVE_SHA = "d7781381ee52efb3be6edf885857b2800a4e1e00ce989a63a00955035183d8dc"

sys.path.insert(0, str(ROOT / "deploy/ansible/tools"))
from verify_kernel import PATCHES, sha, verify  # noqa E402


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def config_without_release(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines()
            if not line.startswith("CONFIG_LOCALVERSION=")]


def source_check(deep: bool = False) -> dict:
    require((A / "source/.sl101-four-patches-applied").is_file(),
            "RC source marker missing")
    require((B / "source/.sl101-three-patches-minus-cma-applied").is_file(),
            "minus-CMA source marker missing")
    require(set(p.name for p in (A / "patches").glob("*.patch")) == set(PATCHES),
            "RC must contain exactly four source patches")
    common = {k: v for k, v in PATCHES.items() if k != CMA}
    require(set(p.name for p in (B / "patches").glob("*.patch")) == set(common),
            "Control must contain exactly the three other source patches")
    for name, digest in PATCHES.items():
        require(sha(PATCH_PATH / name) == digest, "upstream patch hash drift: " + name)
        require(sha(A / "patches" / name) == digest, "RC patch hash drift: " + name)
        if name != CMA:
            require(sha(B / "patches" / name) == digest, "control common patch drift: " + name)
    require(sha(A / "backup/production.config") == sha(B / "backup/production.config"),
            "productive stock config differs")

    # Reversing CMA from the already prepared full-CPU source MUST produce
    # the exact control file. This excludes an accidental unrelated edit
    # to CMA code while proving all other three patches remain applied.
    src_rel = "arch/arm/mm/dma-mapping.c"
    with tempfile.TemporaryDirectory(prefix="sl101-cma-reverse-") as tmp:
        dest = Path(tmp) / src_rel
        dest.parent.mkdir(parents=True)
        dest.write_bytes((A / "source" / src_rel).read_bytes())
        reverse = subprocess.run(
            ["patch", "--dry-run", "--batch", "--fuzz=0", "-p1", "-R", "-d", tmp],
            input=(A / "patches" / CMA).read_bytes(), capture_output=True)
        require(reverse.returncode == 0, "CMA reverse dry run mismatch")
        actual = subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-p1", "-R", "-d", tmp],
            input=(A / "patches" / CMA).read_bytes(), capture_output=True)
        require(actual.returncode == 0, "CMA reverse patch failed")
        require(dest.read_bytes() == (B / "source" / src_rel).read_bytes(),
                "CMA-only file mismatch after reversing patch")
    verified_files = "CMA patch reverses to byte-identical control source"
    if deep:
        # This compares EVERY source path and byte, excluding only our own
        # differently named provenance markers. It is intentionally slower.
        proc = subprocess.run([
            "diff", "-qr", "--exclude=.sl101-four-patches-applied",
            "--exclude=.sl101-three-patches-minus-cma-applied",
            str(A / "source"), str(B / "source"),
        ], capture_output=True, text=True, timeout=180)
        require(proc.returncode == 1,
                "deep source diff error or unexpected identical source: " + proc.stderr[-300:])
        lines = proc.stdout.splitlines()
        require(len(lines) == 1 and
                lines[0].startswith("Files ") and
                lines[0].endswith("/arch/arm/mm/dma-mapping.c differ"),
                "unexpected additional source-tree differences: " + repr(lines[:12]))
        verified_files = "entire source trees differ ONLY in arch/arm/mm/dma-mapping.c"

    if (A / "out/.config").is_file() and (B / "out/.config").is_file():
        require(config_without_release(A / "out/.config") ==
                config_without_release(B / "out/.config"),
                "Kconfig includes differences beyond localversion")
    return {"full_kernel_source_diff": verified_files,
            "common_patch_names": sorted(common),
            "isolated_patch": CMA,
            "stock_config_sha256": sha(B / "backup/production.config")}


def release_check(lane: Path, rel: str) -> dict:
    errors = verify(lane, rel, DTB_SHA, require_source_patches=False)
    require(not errors, "kernel+module verification error: " + "; ".join(errors))
    version = (lane / "out/include/config/kernel.release").read_text().strip()
    require(version == rel, "built kernel release mismatch")
    release = lane / "release"
    require(release.is_dir(), "portable release not yet packaged")
    manifest = json.loads((release / "PROVENANCE.json").read_text())
    require(manifest.get("module_count") == 587,
            "provenance module count must be 587")
    modroot = release / f"lib/modules/{rel}"
    modules = {p.relative_to(modroot).as_posix(): p
               for p in modroot.rglob("*.ko.zst")}
    require(len(modules) == 587, "module filenames incomplete")
    check = subprocess.run(["sha256sum", "-c", "SHA256SUMS"],
                           cwd=release, capture_output=True, text=True, timeout=90)
    require(check.returncode == 0, "package SHA256SUMS failed: " + check.stderr[-250:])
    image = release / f"boot/zImage-{rel}"
    require(image.is_file(), "no release image")
    require(sha(release / "boot/tegra20-asus-sl101.dtb") == DTB_SHA,
            "release DTB mismatch")
    return {
        "release": rel,
        "zimage_sha256": sha(image),
        "dtb_sha256": DTB_SHA,
        "vde_sha256": sha(modroot / "kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"),
        "module_count": len(modules),
        "module_paths": sorted(modules),
        "checksum_entries": len(check.stdout.splitlines()),
        "provenance": manifest,
    }


def compare(deep: bool = False, source_only: bool = False) -> dict:
    src = source_check(deep=deep)
    if source_only:
        return {"gate": "SOURCE_ONLY_PASS", "source": src,
                "compiled_results": "NOT_CHECKED"}
    result_a = release_check(A, A_REL)
    result_b = release_check(B, B_REL)
    require(result_a["module_paths"] == result_b["module_paths"],
            "different module inventory - invalid A/B benchmark")
    require(result_a["dtb_sha256"] == result_b["dtb_sha256"], "different DTB")
    require(result_a["provenance"]["patches"] ==
            [{"name": k, "sha256": v} for k, v in PATCHES.items()],
            "RC is not full four-patch image")
    control_patch_names = {x["name"] for x in result_b["provenance"]["patches"]}
    require(control_patch_names == set(PATCHES) - {CMA},
            "minus-CMA release incorrectly includes CMA")
    require(result_b["provenance"]["excluded_patch"]["name"] == CMA,
            "control excluded patch was not CMA")
    require(result_b["provenance"]["comparison_archive_sha256"] == RC_ARCHIVE_SHA,
            "control comparisons unpinned")
    require(result_a["release"] != result_b["release"], "kernel ABI collision")
    require(result_a["zimage_sha256"] != result_b["zimage_sha256"],
            "kernel images unexpectedly equal despite isolated CMA change")
    archive_a = A / "sl101-7.0.1-dmavde1-four-patch-candidate.tar.zst"
    archive_b = B / "sl101-7.0.1-pmos-grate-dmavde1-minus-cma-benchmark.tar.zst"
    require(sha(archive_a) == RC_ARCHIVE_SHA, "RC archive hash mismatch")
    bench_manifest = (B / (archive_b.name + ".sha256")).read_text()
    require(bench_manifest == f"{sha(archive_b)}  {archive_b.name}\n",
            "benchmark archive hash manifest mismatch")

    a_paths, b_paths = result_a.pop("module_paths"), result_b.pop("module_paths")
    for item in (result_a, result_b):
        item.pop("provenance", None)
    return {
        "gate": "HOST_AB_PAIR_PASS",
        "source": src,
        "shared_module_paths": len(a_paths),
        "rc": {"label": "7.0.1-pmos-grate-dmavde1",
               "archive_sha256": RC_ARCHIVE_SHA, **result_a},
        "benchmark": {"label": "7.0.1-pmos-grate-dmavde1-minus-cma",
                      "archive_sha256": sha(archive_b), **result_b},
        "hardware_status": "NOT_TESTED",
        "performance": "NOT_MEASURED",
        "deployment": "NEITHER_DEVICE_MODIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deep-source", action="store_true")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    try:
        result = compare(deep=args.deep_source, source_only=args.source_only)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print("AB_GATE_FAIL:", exc, file=sys.stderr)
        return 70
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
