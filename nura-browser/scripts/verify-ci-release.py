#!/usr/bin/env python3
"""Fail-closed verifier for the CI-built ARMHF NuraBrowser tar.

The GitHub Actions run provenance MUST be verified separately by the
controller before this verifier is invoked. No local build is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tarfile
import tempfile

SHA = re.compile(r"[a-f0-9]{40}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
RUN = re.compile(r"[1-9][0-9]*\Z")
FILES = {
    "release/CI-PROVENANCE.json",
    "release/nurabrowser-artifacts.json",
    "release/bin/nurabrowser-core",
    "release/bin/,browse",
}
DIRS = {"release", "release/bin"}
EVIDENCE = {
    "nurabrowser-ci.tar",
    "SHA256SUMS.txt",
    "BIN-SHA256SUMS.txt",
    "BUILDER-PACKAGES.tsv",
    "BUILDER-IMAGE-ID.txt",
    "ELF-HEADER.txt",
    "ELF-ATTRIBUTES.txt",
    "ELF-NEEDED.txt",
    "NO-NEON-QEMU.txt",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def checked_armhf(elf: bytes) -> None:
    if len(elf) < 52 or elf[:7] != b"\x7fELF\x01\x01\x01":
        fail("not a valid ELF32 little-endian binary")
    if struct.unpack_from("<H", elf, 18)[0] != 40:  # EM_ARM
        fail("wrong ELF machine, expected ARM")
    flags = struct.unpack_from("<I", elf, 36)[0]
    if (flags & 0xFF000000) != 0x05000000 or not (flags & 0x400):
        fail("not ARM EABI5 hard-float ABI")
    with tempfile.TemporaryDirectory(prefix="nurabrowser-elf-") as tmp:
        path = Path(tmp) / "core"
        path.write_bytes(elf)
        def readelf(*args: str) -> str:
            result = subprocess.run(
                ["readelf", *args, str(path)], capture_output=True,
                text=True, check=True, timeout=12
            )
            return result.stdout
        attrs = readelf("-A")
        if "Tag_CPU_arch: v7" not in attrs or "Tag_FP_arch: VFPv3-D16" not in attrs:
            fail("ARMv7 / VFPv3-D16 attributes absent")
        if "Tag_Advanced_SIMD_arch" in attrs:
            fail("NEON ELF attribute present")
        interp = readelf("-l")
        if "/lib/ld-linux-armhf.so.3" not in interp:
            fail("expected glibc ARMHF interpreter absent")
        needed = readelf("-d")
        if "libWPEWebKit-2.0.so.1" not in needed:
            fail("WPE 2.54 dependency absent")


def verify(artifact_dir: Path, sha: str, run_id: str, tar_sha: str) -> dict:
    if not SHA.fullmatch(sha) or not RUN.fullmatch(run_id):
        fail("invalid exact CI source SHA or run ID")
    if not SHA256.fullmatch(tar_sha):
        fail("invalid approved tar SHA256")
    if not artifact_dir.is_dir() or artifact_dir.is_symlink():
        fail("artifact directory missing or symlinked")
    present = {p.name for p in artifact_dir.iterdir()}
    prepared = EVIDENCE | {"CI-GITHUB-RUN.json", "CI-VERIFIED.json"}
    if present not in (EVIDENCE, prepared) or any(
        not p.is_file() or p.is_symlink() for p in artifact_dir.iterdir()
    ):
        fail(f"artifact evidence file set mismatch: {present ^ EVIDENCE}")

    archive = artifact_dir / "nurabrowser-ci.tar"
    blob = archive.read_bytes()
    if digest(blob) != tar_sha:
        fail("tar digest differs from Git-reviewed approved SHA256")
    if (artifact_dir / "SHA256SUMS.txt").read_text() != (
        f"{tar_sha}  nurabrowser-ci.tar\n"
    ):
        fail("CI SHA256SUMS differs from archive")

    qemu = (artifact_dir / "NO-NEON-QEMU.txt").read_text()
    if "TEGRA2_NO_NEON_QEMU_PROBE=PASS\n" not in qemu or "NEON=0" not in qemu:
        fail("no audited no-NEON runtime probe")
    with tarfile.open(archive, "r:") as tar:
        members = tar.getmembers()
        names = [m.name.rstrip("/") for m in members]
        if len(names) != len(set(names)):
            fail("duplicate archive paths")
        if set(names) != FILES | DIRS:
            fail("unexpected/absent archive entries")
        extracted: dict[str, bytes] = {}
        for member in members:
            name = member.name.rstrip("/")
            if member.uid != 0 or member.gid != 0:
                fail("unexpected archive ownership")
            if name in DIRS:
                if not member.isdir():
                    fail("directory has wrong tar type")
            elif not member.isfile() or member.size > 2 * 1024 * 1024:
                fail("non-regular or oversized release member")
            else:
                f = tar.extractfile(member)
                if f is None:
                    fail("archive file unreadable")
                extracted[name] = f.read()
                if len(extracted[name]) != member.size:
                    fail("short archive member")

    receipt = json.loads(extracted["release/CI-PROVENANCE.json"])
    expected = {
        "schema": "sl101.nurabrowser.github-ci.v1",
        "source_repo": "fkr-0/sl101_linux",
        "source_sha": sha,
        "run_id": run_id,
        "wpe_debian_version": "2.54.0-2",
        "target": "armv7-linux-gnueabihf-vfpv3-d16-no-neon",
        "status": "static-armhf-audited-not-runtime-qualified",
    }
    for k, v in expected.items():
        if receipt.get(k) != v:
            fail(f"CI provenance {k} mismatch")
    if type(receipt.get("run_attempt")) is not int or receipt["run_attempt"] < 1:
        fail("invalid CI run attempt")
    core = extracted["release/bin/nurabrowser-core"]
    launcher = extracted["release/bin/,browse"]
    if digest(core) != receipt.get("browser_sha256"):
        fail("core SHA256 differs from CI provenance")
    if digest(launcher) != receipt.get("launcher_sha256"):
        fail("launcher SHA256 differs from CI provenance")
    checked_armhf(core)
    if not launcher.startswith(b"#!/bin/sh\n") or b"NURABROWSER_PRIVATE_ROOT" not in launcher:
        fail("unexpected browser launcher")
    manifest = json.loads(extracted["release/nurabrowser-artifacts.json"])
    if manifest.get("status") != expected["status"] or manifest.get("wpe_debian_version") != "2.54.0-2":
        fail("manifest release status mismatch")
    paths = {e["install_path"]: e for e in manifest.get("artifacts", [])}
    if set(paths) != {
        "/usr/libexec/nura-browser/nurabrowser-core", "/usr/bin/,browse"
    }:
        fail("manifest contains unexpected artifact paths")
    for path, data in (
        ("/usr/libexec/nura-browser/nurabrowser-core", core),
        ("/usr/bin/,browse", launcher)
    ):
        if paths[path].get("sha256") != digest(data) or paths[path].get("size") != len(data):
            fail("embedded manifest SHA256 or size mismatch")
    checksums = (artifact_dir / "BIN-SHA256SUMS.txt").read_text()
    expected_checksums = (
        f"{digest(core)}  release/bin/nurabrowser-core\n"
        f"{digest(launcher)}  release/bin/,browse\n"
    )
    if checksums != expected_checksums:
        fail("binary checksums differ")
    if "libWPEWebKit-2.0.so.1" not in (artifact_dir / "ELF-NEEDED.txt").read_text():
        fail("CI ELF dependency audit missing")
    return {
        "schema": "sl101.nurabrowser.ci-verified.v1",
        "sha": sha,
        "run_id": run_id,
        "tar_sha256": tar_sha,
        "core_sha256": digest(core),
        "launcher_sha256": digest(launcher),
        "status": "CI-STATIC-READY-RUNTIME-UNQUALIFIED",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-dir", type=Path, required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--tar-sha256", required=True)
    args = p.parse_args()
    try:
        result = verify(args.artifact_dir, args.sha, args.run_id, args.tar_sha256)
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
