#!/usr/bin/env python3
"""Build/verify a reversible one-shot SL101 Nura kernel-7 staging bundle.

This is a host-side tool. It never talks to the tablet itself.

The generated OpenRC helper is deliberately fail-back:
- no marker => no action;
- marker is consumed before preflight/kexec load;
- any failure requires a freshly-created marker;
- the internal 6.18 cold-boot path remains untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys


DEFAULT_RELEASE = "7.0.1-postmarketos-grate"
DEFAULT_RECOVERY_RELEASE = "6.18.45"
DEFAULT_ROOT_DEVICE = "/dev/mmcblk1p1"
DEFAULT_CMDLINE = (
    "root=/dev/mmcblk1p1 rootfstype=ext4 rootwait rw "
    "console=tty0 video=tegrafb loglevel=7"
)


class ContractError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_provenance(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "android-infra.sl101-kernel7-consolidation.v1":
        raise ContractError(f"unexpected provenance schema in {path}")
    if not data.get("coherence", {}).get("coherent"):
        raise ContractError("canonical provenance is not coherent")
    return data


def module_files(module_root: Path) -> list[Path]:
    suffixes = (".ko", ".ko.zst", ".ko.xz", ".ko.gz")
    return sorted(
        p
        for p in module_root.rglob("*")
        if p.is_file() and p.name.endswith(suffixes)
    )


def validate_source(source_root: Path, provenance: dict) -> dict:
    artifacts = provenance["artifacts"]
    release = artifacts["release"]
    if release != DEFAULT_RELEASE:
        raise ContractError(f"unexpected canonical release: {release}")

    paths = {
        "kernel": source_root / "boot/vmlinuz",
        "dtb": source_root / "boot/tegra20-asus-sl101.dtb",
        "config": source_root / "boot/config",
        "module_root": source_root / "lib/modules" / release,
    }
    for label, path in paths.items():
        if not path.exists():
            raise ContractError(f"missing canonical {label}: {path}")

    expected = {
        "kernel": artifacts["vmlinuz_sha256"],
        "dtb": artifacts["dtb_sha256"],
        "config": artifacts["config_sha256"],
    }
    observed = {
        label: sha256_file(paths[label])
        for label in ("kernel", "dtb", "config")
    }
    for label, digest in observed.items():
        if digest != expected[label]:
            raise ContractError(
                f"{label} hash mismatch: expected {expected[label]}, got {digest}"
            )

    mods = module_files(paths["module_root"])
    if len(mods) != artifacts["module_count"]:
        raise ContractError(
            f"module count mismatch: expected {artifacts['module_count']}, got {len(mods)}"
        )

    for metadata, key in (
        ("modules.builtin", "modules_builtin_sha256"),
        ("modules.dep", "modules_dep_sha256"),
        ("modules.alias", "modules_alias_sha256"),
    ):
        path = paths["module_root"] / metadata
        if not path.is_file():
            raise ContractError(f"missing module metadata: {path}")
        digest = sha256_file(path)
        if digest != artifacts[key]:
            raise ContractError(
                f"{metadata} mismatch: expected {artifacts[key]}, got {digest}"
            )

    return {
        "release": release,
        "paths": {key: str(value) for key, value in paths.items()},
        "hashes": observed,
        "module_count": len(mods),
    }


def write_module_manifest(module_root: Path, destination: Path) -> None:
    lines: list[str] = []
    for path in sorted(p for p in module_root.rglob("*") if p.is_file()):
        rel = path.relative_to(module_root).as_posix()
        lines.append(f"{sha256_file(path)}  {rel}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_helper(manifest: dict) -> str:
    release = manifest["release"]
    recovery = manifest["expected_recovery_release"]
    root_device = manifest["expected_root_device"]
    cmdline = manifest["command_line"]
    kernel_sha = manifest["kernel_sha256"]
    dtb_sha = manifest["dtb_sha256"]
    config_sha = manifest["config_sha256"]
    return f"""#!/bin/sh
set -eu

TARGET_RELEASE='{release}'
RECOVERY_RELEASE='{recovery}'
EXPECTED_ROOT='{root_device}'
COMMAND_LINE='{cmdline}'
BASE=/opt/nura-kernel7
STATE=/var/lib/sl101-kernel7
MARKER=$STATE/nextboot
PENDING=$STATE/pending
CONSUMED=$STATE/consumed
ERROR=$STATE/last-error
GRACE_SECONDS=${{SL101_KERNEL7_GRACE_SECONDS:-10}}

fail() {{
    mkdir -p "$STATE"
    printf '%s\n' "$*" >"$ERROR"
    echo "sl101-kernel7-oneshot: $*" >&2
    exit 1
}}

[ -f "$MARKER" ] || exit 0

mkdir -p "$CONSUMED"
BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown)
STAMP=$(date +%s 2>/dev/null || echo 0)
ATTEMPT="$CONSUMED/$BOOT_ID-$STAMP"

# Consume the retry-capable marker before the grace window.  A power loss now
# leaves only PENDING, so the next cold boot cannot retry without a fresh marker.
if [ -f "$PENDING" ]; then
    mv "$PENDING" "$CONSUMED/stale-$BOOT_ID-$STAMP"
fi
mv "$MARKER" "$PENDING"

# Give a physically-present/remote operator a bounded cancellation window.
# Cancellation removes PENDING; NEXTBOOT has already been consumed.
sleep "$GRACE_SECONDS"
[ -f "$PENDING" ] || exit 0

# Preserve evidence of the one attempt before any preflight or kexec load.
mv "$PENDING" "$ATTEMPT"

[ "$(uname -r)" = "$RECOVERY_RELEASE" ] ||
    fail "recovery kernel mismatch: expected $RECOVERY_RELEASE, got $(uname -r)"

ROOT_SOURCE=$(findmnt -n -o SOURCE / 2>/dev/null || awk '$2 == "/" {{print $1; exit}}' /proc/mounts)
[ "$ROOT_SOURCE" = "$EXPECTED_ROOT" ] ||
    fail "root device mismatch: expected $EXPECTED_ROOT, got $ROOT_SOURCE"

command -v sha256sum >/dev/null 2>&1 || fail "sha256sum unavailable"
command -v kexec >/dev/null 2>&1 || fail "kexec unavailable"

printf '{kernel_sha}  %s\n' "$BASE/vmlinuz" | sha256sum -c - >/dev/null ||
    fail "kernel hash mismatch"
printf '{dtb_sha}  %s\n' "$BASE/tegra20-asus-sl101.dtb" | sha256sum -c - >/dev/null ||
    fail "DTB hash mismatch"
printf '{config_sha}  %s\n' "$BASE/config" | sha256sum -c - >/dev/null ||
    fail "config hash mismatch"

MODULE_ROOT=/lib/modules/$TARGET_RELEASE
[ -d "$MODULE_ROOT" ] || fail "missing module tree $MODULE_ROOT"
(
    cd "$MODULE_ROOT"
    sha256sum -c "$BASE/modules.sha256" >/dev/null
) || fail "module tree hash mismatch"

rm -f "$ERROR"
sync
kexec -l "$BASE/vmlinuz" \
    --dtb="$BASE/tegra20-asus-sl101.dtb" \
    --command-line="$COMMAND_LINE" ||
    fail "kexec load failed"

sync
exec kexec -e
"""


def render_openrc_service() -> str:
    return """#!/sbin/openrc-run
description="One-shot handoff from SL101 recovery kernel to canonical Nura 7.x"
command="/usr/local/sbin/sl101-kernel7-oneshot"
command_background="no"

depend() {
    need localmount
    after networkmanager sshd
}
"""


def build_bundle(source_root: Path, provenance_path: Path, out: Path) -> dict:
    provenance = load_provenance(provenance_path)
    observed = validate_source(source_root, provenance)
    artifacts = provenance["artifacts"]
    release = observed["release"]

    if out.exists():
        shutil.rmtree(out)
    (out / "opt/nura-kernel7").mkdir(parents=True)
    (out / "lib/modules").mkdir(parents=True)
    (out / "usr/local/sbin").mkdir(parents=True)
    (out / "etc/init.d").mkdir(parents=True)
    (out / "etc/runlevels/default").mkdir(parents=True)

    base = out / "opt/nura-kernel7"
    shutil.copy2(source_root / "boot/vmlinuz", base / "vmlinuz")
    shutil.copy2(
        source_root / "boot/tegra20-asus-sl101.dtb",
        base / "tegra20-asus-sl101.dtb",
    )
    shutil.copy2(source_root / "boot/config", base / "config")

    source_modules = source_root / "lib/modules" / release
    target_modules = out / "lib/modules" / release
    shutil.copytree(source_modules, target_modules, symlinks=True)
    for name in ("build", "source"):
        candidate = target_modules / name
        if candidate.is_symlink():
            candidate.unlink()

    write_module_manifest(target_modules, base / "modules.sha256")

    manifest = {
        "schema": "android-infra.sl101-kernel7-oneshot.v1",
        "release": release,
        "expected_recovery_release": DEFAULT_RECOVERY_RELEASE,
        "expected_root_device": DEFAULT_ROOT_DEVICE,
        "command_line": DEFAULT_CMDLINE,
        "kernel_sha256": artifacts["vmlinuz_sha256"],
        "dtb_sha256": artifacts["dtb_sha256"],
        "config_sha256": artifacts["config_sha256"],
        "module_count": artifacts["module_count"],
        "canonical_provenance_sha256": sha256_file(provenance_path),
        "marker_path": "/var/lib/sl101-kernel7/nextboot",
        "service_enabled_by_bundle": False,
        "cold_boot_recovery_preserved": True,
    }
    (base / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    helper = out / "usr/local/sbin/sl101-kernel7-oneshot"
    helper.write_text(render_helper(manifest), encoding="utf-8")
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    service = out / "etc/init.d/sl101-kernel7-oneshot"
    service.write_text(render_openrc_service(), encoding="utf-8")
    service.chmod(service.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Intentionally do not place a symlink under etc/runlevels/default.
    # Enabling the service is a separate human-present deployment step.

    lines: list[str] = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        if path.name == "SHA256SUMS":
            continue
        lines.append(f"{sha256_file(path)}  {path.relative_to(out).as_posix()}")
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def verify_bundle(out: Path) -> dict:
    base = out / "opt/nura-kernel7"
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file():
        raise ContractError("bundle manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "android-infra.sl101-kernel7-oneshot.v1":
        raise ContractError("unexpected bundle schema")

    expected = {
        base / "vmlinuz": manifest["kernel_sha256"],
        base / "tegra20-asus-sl101.dtb": manifest["dtb_sha256"],
        base / "config": manifest["config_sha256"],
    }
    for path, digest in expected.items():
        if not path.is_file() or sha256_file(path) != digest:
            raise ContractError(f"bundle artifact mismatch: {path}")

    module_root = out / "lib/modules" / manifest["release"]
    if not module_root.is_dir():
        raise ContractError("bundle module tree missing")
    mods = module_files(module_root)
    if len(mods) != manifest["module_count"]:
        raise ContractError("bundle module count mismatch")

    for symlink in ("build", "source"):
        if (module_root / symlink).exists() or (module_root / symlink).is_symlink():
            raise ContractError(f"host-only module symlink present: {symlink}")

    sums = out / "SHA256SUMS"
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        path = out / rel
        if not path.is_file() or sha256_file(path) != digest:
            raise ContractError(f"bundle SHA mismatch: {rel}")

    helper = out / "usr/local/sbin/sl101-kernel7-oneshot"
    text = helper.read_text(encoding="utf-8")
    required = (
        "mv \"$MARKER\" \"$PENDING\"",
        "mv \"$PENDING\" \"$ATTEMPT\"",
        "kexec -l",
        "exec kexec -e",
        "module tree hash mismatch",
        "root device mismatch",
        "recovery kernel mismatch",
    )
    for needle in required:
        if needle not in text:
            raise ContractError(f"helper safety contract missing: {needle}")

    if (out / "etc/runlevels/default/sl101-kernel7-oneshot").exists():
        raise ContractError("bundle must not enable OpenRC service automatically")

    return {
        "release": manifest["release"],
        "module_count": len(mods),
        "service_enabled": False,
        "one_shot_marker": manifest["marker_path"],
        "verified": True,
    }


def evaluate_preflight(
    *,
    marker_exists: bool,
    current_release: str,
    root_device: str,
    kernel_hash_ok: bool,
    dtb_hash_ok: bool,
    config_hash_ok: bool,
    module_tree_ok: bool,
) -> tuple[bool, str]:
    """Pure model of the runtime preflight for unit tests/review."""
    if not marker_exists:
        return False, "no-marker"
    if current_release != DEFAULT_RECOVERY_RELEASE:
        return False, "recovery-kernel-mismatch"
    if root_device != DEFAULT_ROOT_DEVICE:
        return False, "root-device-mismatch"
    if not kernel_hash_ok:
        return False, "kernel-hash-mismatch"
    if not dtb_hash_ok:
        return False, "dtb-hash-mismatch"
    if not config_hash_ok:
        return False, "config-hash-mismatch"
    if not module_tree_ok:
        return False, "module-tree-mismatch"
    return True, "ready-for-one-shot-kexec"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build host-only staging bundle")
    build.add_argument("--source-root", type=Path, required=True)
    build.add_argument("--provenance", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)

    verify = sub.add_parser("verify", help="verify a staging bundle")
    verify.add_argument("--bundle", type=Path, required=True)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            result = build_bundle(args.source_root, args.provenance, args.out)
        else:
            result = verify_bundle(args.bundle)
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
