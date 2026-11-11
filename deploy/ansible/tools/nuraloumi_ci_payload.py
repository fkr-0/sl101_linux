#!/usr/bin/env python3
"""Host-only import of an EXACT, successful NuraLoumi GitHub CI artifact.

No device access, no local build output, no APK key enrollment or installation.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
REQUIRED = {"nuraloumi-panel", "nuraloumi-files", "nuraloumi-run",
            "nuraloumi-viewer", "nuraloumi-sway-workspace-switcher"}
TARGET = "armv7-unknown-linux-musleabihf"
SCHEMA = "sl101-nuraloumi-ci-payload-v1"
MAX_FILES = 256
MAX_BYTES = 256 * 1024 * 1024


def demand(condition, why):
    if not condition:
        raise ValueError(why)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_fields(text):
    header, marker, tail = text.partition("\nfiles:\n")
    demand(bool(marker), "missing manifest files section")
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition("=")
        demand(bool(sep) and key not in fields, "invalid/duplicate manifest field")
        fields[key] = value
    digests = {}
    for line in tail.splitlines():
        found = re.fullmatch(r"  ([0-9a-f]{64})  ([a-zA-Z0-9_./-]+)", line)
        demand(found is not None, "invalid per-file manifest checksum")
        digest, path = found.groups()
        p = PurePosixPath(path)
        demand(not p.is_absolute() and ".." not in p.parts and path not in digests,
               "duplicate/unsafe manifest path")
        digests[path] = digest
    demand(bool(digests), "empty file digest list")
    return fields, digests


def verify_elf(path):
    with Path(path).open("rb") as stream:
        head = stream.read(52)
    demand(len(head) >= 52 and head[:6] == b"\x7fELF\x01\x01",
           f"not a little-endian ELF32 binary: {path}")
    demand(struct.unpack_from("<H", head, 18)[0] == 40,
           f"not ARM EABI: {path}")
    demand(struct.unpack_from("<I", head, 36)[0] & 0x400 != 0,
           f"missing ARM hard-float ABI: {path}")


def verify_payload(root, sha, run_id, expected_tar_sha=None, expected_manifest_sha=None):
    """Controller-side validation immediately before Ansible can copy bytes."""
    root = Path(root)
    demand(SHA_RE.fullmatch(sha) is not None and run_id > 0, "invalid identity")
    proof_path = root / "CI-PROVENANCE.json"
    demand(proof_path.is_file() and not proof_path.is_symlink(), "missing proof")
    proof = json.loads(proof_path.read_text())
    for key, wanted in (("schema", SCHEMA), ("git_sha", sha),
                        ("run_id", run_id), ("target", TARGET),
                        ("ci_conclusion", "success")):
        demand(proof.get(key) == wanted, f"payload {key} mismatch")
    mf = root / "release/MANIFEST.txt"
    demand(mf.is_file() and not mf.is_symlink(), "missing manifest")
    fields, digests = manifest_fields(mf.read_text())
    for key, wanted in (("schema", "nuraloumi-package-manifest-v1"),
                        ("git_commit", sha), ("git_dirty", "false"),
                        ("target", TARGET)):
        demand(fields.get(key) == wanted, f"manifest {key} mismatch")
    names = fields.get("binaries", "").split(",")
    demand(len(names) >= 24 and len(names) == len(set(names)) and
           all(NAME_RE.fullmatch(n) for n in names) and REQUIRED.issubset(names),
           "invalid or incomplete binary set")
    demand(names == proof.get("binaries"), "provenance binary list mismatch")
    lines = []
    for name in names:
        path = root / "release/bin" / name
        demand(path.is_file() and not path.is_symlink(), f"missing binary {name}")
        verify_elf(path)
        digest = sha256(path)
        demand(digests.get("bin/" + name) == digest,
               f"manifest checksum mismatch: {name}")
        lines.append(f"{digest}  bin/{name}")
    expected = "\n".join(lines) + "\n"
    checksum = root / "release/SHA256SUMS.bin"
    demand(checksum.is_file() and not checksum.is_symlink() and
           checksum.read_text() == expected,
           "remote binary checksum contract mismatch")
    demand(sha256(mf) == proof.get("manifest_sha256"), "manifest proof mismatch")
    demand(bool(DIGEST_RE.fullmatch(proof.get("ci_tar_sha256", ""))),
           "missing source tar SHA256")
    bundled = root / "nuraloumi-ci.tar"
    if bundled.exists():
        demand(bundled.is_file() and not bundled.is_symlink() and
               sha256(bundled) == proof["ci_tar_sha256"],
               "preserved CI tar differs from verified original")
    if expected_tar_sha is not None:
        demand(proof["ci_tar_sha256"] == expected_tar_sha,
               "CI tar digest differs from repository-approved immutable digest")
    if expected_manifest_sha is not None:
        demand(sha256(mf) == expected_manifest_sha,
               "CI manifest digest differs from repository-approved immutable digest")
    demand((root / "ELF-AUDIT.txt").is_file(), "missing ELF audit evidence")
    return names


def import_verified_download(download, candidate, sha, run_id):
    """Only caller is the successful upstream exact-run GitHub verifier."""
    download, candidate = Path(download), Path(candidate)
    tar_path = download / "nuraloumi-ci.tar"
    mf_path = download / "nuraloumi-ci/MANIFEST.txt"
    demand(tar_path.is_file() and mf_path.is_file(), "incomplete CI tar download")
    source_fields, source_digests = manifest_fields(mf_path.read_text())
    demand(source_fields.get("git_commit") == sha and
           source_fields.get("target") == TARGET and
           source_fields.get("git_dirty") == "false",
           "downloaded artifact does not match required SHA/ABI")
    binary_names = source_fields.get("binaries", "").split(",")
    demand(REQUIRED.issubset(binary_names) and len(binary_names) >= 24,
           "incomplete upstream binary list")
    (candidate / "release/bin").mkdir(parents=True, exist_ok=False)
    total = 0
    visited = set()
    checked = set()
    with tarfile.open(tar_path, "r:") as archive:
        members = archive.getmembers()
        demand(len(members) <= MAX_FILES, "too many entries in CI tar")
        for member in members:
            path = PurePosixPath(member.name)
            demand(not path.is_absolute() and ".." not in path.parts,
                   "unsafe tar member path")
            rel = str(path)
            if rel == ".":
                continue
            demand(rel not in visited, "duplicate tar member")
            visited.add(rel)
            demand(member.isdir() or member.isfile(), "tar symlink/hardlink/device prohibited")
            if member.isdir():
                continue
            total += member.size
            demand(total <= MAX_BYTES, "CI tar exceeds maximum uncompressed size")
            # The manifest describes every OTHER file; it cannot include
            # its own checksum without a circular hash dependency.
            expected = sha256(mf_path) if rel == "MANIFEST.txt" else source_digests.get(rel)
            demand(expected is not None, f"unexpected tar file {rel}")
            handle = archive.extractfile(member)
            demand(handle is not None, "cannot read tar member")
            selected = rel.startswith("bin/") and rel.removeprefix("bin/") in binary_names
            output = candidate / "release" / rel if selected else None
            digest = hashlib.sha256()
            if output is not None:
                with output.open("xb") as stream:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                        stream.write(chunk)
                output.chmod(0o755)
                verify_elf(output)
            else:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            demand(digest.hexdigest() == expected, f"tar member SHA256 mismatch: {rel}")
            if rel != "MANIFEST.txt":
                checked.add(rel)
    demand(checked == set(source_digests), "tar member list differs from manifest")
    demand(set(binary_names) == {x.name for x in (candidate / "release/bin").iterdir()},
           "declared binaries not present exactly")
    shutil.copy2(mf_path, candidate / "release/MANIFEST.txt")
    shutil.copy2(download / "ELF-AUDIT.txt", candidate / "ELF-AUDIT.txt")
    # Keep the original verified CI tar for one-copy Ansible deployment.
    # This includes *all* shipped widgets, menus, tools, config examples and
    # share/ documentation, not just the 24 executable files.
    shutil.copy2(tar_path, candidate / "nuraloumi-ci.tar")
    with (candidate / "release/SHA256SUMS.bin").open("x") as stream:
        for name in binary_names:
            stream.write(f"{source_digests['bin/' + name]}  bin/{name}\n")
    proof = {
        "schema": SCHEMA, "git_sha": sha, "run_id": run_id,
        "target": TARGET, "ci_conclusion": "success",
        "ci_tar_sha256": sha256(tar_path), "manifest_sha256": sha256(mf_path),
        "binaries": binary_names,
        "mode": "copy-only-staging; no APK installation or activation",
    }
    (candidate / "CI-PROVENANCE.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n"
    )
    verify_payload(candidate, sha, run_id)
    return len(binary_names)


def prepare(nuraloumi_repo, output_root, sha, run_id):
    repo, output_root = Path(nuraloumi_repo), Path(output_root)
    demand(SHA_RE.fullmatch(sha) is not None and run_id > 0,
           "required full Git SHA or positive CI run ID missing")
    verifier = repo / "scripts/verify-ci-artifact.py"
    demand(verifier.is_file(), "sibling nuraloumi verifier missing")
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / sha
    if destination.exists() or destination.is_symlink():
        names = verify_payload(destination, sha, run_id)
        print(f"CI_PAYLOAD_ALREADY_VERIFIED sha={sha} binaries={len(names)} path={destination}")
        return
    with tempfile.TemporaryDirectory(prefix=".nuraloumi-ci-prepare-", dir=output_root) as tmp:
        tmp = Path(tmp)
        downloaded = tmp / "ci"
        subprocess.run(
            [sys.executable, str(verifier), "--lane", "alpine",
             "--run-id", str(run_id), "--sha", sha, "--out", str(downloaded)],
            check=True, timeout=600,
        )
        stage = tmp / "candidate"
        count = import_verified_download(downloaded, stage, sha, run_id)
        stage.rename(destination)  # publish only after ALL checks have passed
        print(f"CI_PAYLOAD_PREPARED sha={sha} binaries={count} path={destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    p = parser.add_subparsers(dest="mode", required=True)
    prepare_cmd = p.add_parser("prepare", help="exact successful CI download; host-only")
    prepare_cmd.add_argument("--nuraloumi-repo", type=Path, required=True)
    prepare_cmd.add_argument("--out-root", type=Path, required=True)
    verify_cmd = p.add_parser("verify", help="fully offline payload integrity gate")
    verify_cmd.add_argument("--root", type=Path, required=True)
    verify_cmd.add_argument("--expected-tar-sha", required=False)
    verify_cmd.add_argument("--expected-manifest-sha", required=False)
    for cmd in (prepare_cmd, verify_cmd):
        cmd.add_argument("--sha", required=True)
        cmd.add_argument("--run-id", required=True, type=int)
    a = parser.parse_args()
    if a.mode == "prepare":
        prepare(a.nuraloumi_repo, a.out_root, a.sha, a.run_id)
    else:
        names = verify_payload(a.root, a.sha, a.run_id,
                               a.expected_tar_sha, a.expected_manifest_sha)
        print(f"CI_PAYLOAD_VERIFIED sha={a.sha} binaries={len(names)}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, tarfile.TarError,
            json.JSONDecodeError) as error:
        print(f"NURALOUMI_CI_PREPARE=FAIL: {error}", file=sys.stderr)
        raise SystemExit(2) from error
