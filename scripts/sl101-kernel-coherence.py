#!/usr/bin/env python3
"""Read-only SL101 kernel/config/module coherence gate.

The gate compares the config embedded in the running kernel with the installed
/boot/config and module tree. It is intentionally observational: it never
loads/unloads modules, writes boot files, or changes the target.

Typical live use:
    python scripts/sl101-kernel-coherence.py --ssh root@192.168.23.106

Fixture/local-root use:
    python scripts/sl101-kernel-coherence.py --root /path/to/root
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys


CRITICAL_BUILTINS = (
    (
        "CONFIG_MFD_ASUS_TRANSFORMER_EC",
        "asus-transformer-ec",
        "ASUS Transformer EC",
    ),
    (
        "CONFIG_SERIO_ASUS_TRANSFORMER_EC",
        "asus-transformer-ec-kbc",
        "ASUS Transformer EC keyboard",
    ),
)

BOOT_HASH_PATHS = (
    "/boot/vmlinuz",
    "/boot/zImage-ec-current",
    "/boot/tegra20-asus-sl101.dtb",
    "/boot/tegra20-asus-sl101-ec-current.dtb",
)


@dataclass(frozen=True)
class Snapshot:
    kernel_release: str
    runtime_config: str
    boot_config: str
    module_files: tuple[str, ...]
    modules_builtin: tuple[str, ...]
    boot_hashes: dict[str, str]
    source: str


def parse_config(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
            continue
        prefix = "# "
        suffix = " is not set"
        if line.startswith(prefix + "CONFIG_") and line.endswith(suffix):
            out[line[len(prefix) : -len(suffix)]] = "n"
    return out


def normalized_module_name(path: str) -> str | None:
    name = Path(path).name
    for suffix in (".zst", ".xz", ".gz"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if not name.endswith(".ko"):
        return None
    return name[:-3].replace("_", "-")


def sha256_path(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_runtime_config(root: Path) -> str:
    gz = root / "proc/config.gz"
    if gz.exists():
        with gzip.open(gz, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    plain = root / "proc/config"
    return read_text(plain) if plain.exists() else ""


def collect_root(root: Path) -> Snapshot:
    release_path = root / "proc/sys/kernel/osrelease"
    release = read_text(release_path).strip() if release_path.exists() else ""
    runtime_config = read_runtime_config(root)
    boot_path = root / "boot/config"
    boot_config = read_text(boot_path) if boot_path.exists() else ""

    module_files: list[str] = []
    builtin: list[str] = []
    if release:
        module_root = root / "lib/modules" / release
        if module_root.exists():
            for path in module_root.rglob("*"):
                if path.is_file() and normalized_module_name(path.name) is not None:
                    module_files.append(path.relative_to(module_root).as_posix())
            builtin_path = module_root / "modules.builtin"
            if builtin_path.exists():
                builtin = [
                    line.strip()
                    for line in read_text(builtin_path).splitlines()
                    if line.strip()
                ]

    hashes: dict[str, str] = {}
    for absolute in BOOT_HASH_PATHS:
        digest = sha256_path(root / absolute.lstrip("/"))
        if digest:
            hashes[absolute] = digest

    return Snapshot(
        kernel_release=release,
        runtime_config=runtime_config,
        boot_config=boot_config,
        module_files=tuple(sorted(module_files)),
        modules_builtin=tuple(sorted(builtin)),
        boot_hashes=hashes,
        source=str(root),
    )


def _ssh(host: str, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, command],
        text=True,
        capture_output=True,
        check=False,
    )


def _ssh_text(host: str, command: str) -> str:
    result = _ssh(host, command)
    if result.returncode != 0:
        return ""
    return result.stdout


def collect_ssh(host: str) -> Snapshot:
    release = _ssh_text(host, "uname -r").strip()
    runtime_config = _ssh_text(
        host,
        "if [ -r /proc/config.gz ]; then zcat /proc/config.gz; "
        "elif [ -r /proc/config ]; then cat /proc/config; fi",
    )
    boot_config = _ssh_text(host, "cat /boot/config 2>/dev/null || true")

    quoted_release = shlex.quote(release)
    module_files = tuple(
        sorted(
            line.strip()
            for line in _ssh_text(
                host,
                "r=/lib/modules/"
                + quoted_release
                + "; if [ -d \"$r\" ]; then "
                + "find \"$r\" -type f \\( -name '*.ko' -o -name '*.ko.xz' "
                + "-o -name '*.ko.zst' -o -name '*.ko.gz' \\) "
                + "-print 2>/dev/null | sed \"s#^$r/##\"; fi",
            ).splitlines()
            if line.strip()
        )
    )
    builtin = tuple(
        sorted(
            line.strip()
            for line in _ssh_text(
                host,
                "cat /lib/modules/"
                + quoted_release
                + "/modules.builtin 2>/dev/null || true",
            ).splitlines()
            if line.strip()
        )
    )

    hash_command = (
        "for f in "
        + " ".join(shlex.quote(path) for path in BOOT_HASH_PATHS)
        + "; do [ -f \"$f\" ] && sha256sum \"$f\"; done"
    )
    hashes: dict[str, str] = {}
    for line in _ssh_text(host, hash_command).splitlines():
        fields = line.split(None, 1)
        if len(fields) == 2:
            hashes[fields[1].strip()] = fields[0]

    return Snapshot(
        kernel_release=release,
        runtime_config=runtime_config,
        boot_config=boot_config,
        module_files=module_files,
        modules_builtin=builtin,
        boot_hashes=hashes,
        source=f"ssh:{host}",
    )


def config_differences(runtime: dict[str, str], boot: dict[str, str]) -> list[dict[str, str]]:
    differences: list[dict[str, str]] = []
    for key in sorted(set(runtime) | set(boot)):
        r = runtime.get(key, "<missing>")
        b = boot.get(key, "<missing>")
        if r != b:
            differences.append({"symbol": key, "runtime": r, "boot": b})
    return differences


def analyze(snapshot: Snapshot) -> dict:
    findings: list[dict] = []
    runtime = parse_config(snapshot.runtime_config)
    boot = parse_config(snapshot.boot_config)

    if not snapshot.kernel_release:
        findings.append(
            {
                "severity": "error",
                "code": "kernel_release_missing",
                "message": "running kernel release is unavailable",
            }
        )

    if not runtime:
        findings.append(
            {
                "severity": "error",
                "code": "runtime_config_missing",
                "message": "running kernel config is unavailable from /proc/config.gz or /proc/config",
            }
        )

    if not boot:
        findings.append(
            {
                "severity": "error",
                "code": "boot_config_missing",
                "message": "/boot/config is unavailable or empty",
            }
        )

    differences = config_differences(runtime, boot) if runtime and boot else []
    if differences:
        findings.append(
            {
                "severity": "error",
                "code": "kernel_config_mismatch",
                "message": (
                    f"embedded running config and /boot/config differ in "
                    f"{len(differences)} symbols"
                ),
                "difference_count": len(differences),
                "differences": differences[:100],
                "differences_truncated": len(differences) > 100,
            }
        )

    module_names = {
        name
        for path in snapshot.module_files
        if (name := normalized_module_name(path)) is not None
    }
    builtin_names = {
        name
        for path in snapshot.modules_builtin
        if (name := normalized_module_name(path)) is not None
    }

    module_tree_present = bool(snapshot.kernel_release) and (
        bool(snapshot.module_files) or bool(snapshot.modules_builtin)
    )
    if snapshot.kernel_release and not module_tree_present:
        findings.append(
            {
                "severity": "error",
                "code": "module_tree_missing",
                "message": f"/lib/modules/{snapshot.kernel_release} has no module metadata/files",
            }
        )

    critical: list[dict] = []
    for symbol, module_name, label in CRITICAL_BUILTINS:
        value = runtime.get(symbol, "<missing>")
        item = {
            "symbol": symbol,
            "runtime": value,
            "module": module_name,
            "module_file_present": module_name in module_names,
            "builtin_metadata_present": module_name in builtin_names,
        }
        critical.append(item)
        if value == "y" and module_name in module_names:
            findings.append(
                {
                    "severity": "error",
                    "code": "builtin_has_stale_module_file",
                    "message": (
                        f"{label} is built into the running kernel ({symbol}=y) "
                        f"but a loadable {module_name}.ko file is installed"
                    ),
                    **item,
                }
            )
        if value == "y" and module_name not in builtin_names:
            findings.append(
                {
                    "severity": "error",
                    "code": "builtin_metadata_mismatch",
                    "message": (
                        f"{label} is built into the running kernel ({symbol}=y) "
                        f"but modules.builtin does not identify {module_name}"
                    ),
                    **item,
                }
            )

    errors = [finding for finding in findings if finding["severity"] == "error"]
    return {
        "schema": "android-infra.sl101-kernel-coherence.v1",
        "source": snapshot.source,
        "kernel_release": snapshot.kernel_release,
        "coherent": not errors,
        "summary": {
            "errors": len(errors),
            "config_difference_count": len(differences),
            "module_file_count": len(snapshot.module_files),
            "builtin_metadata_count": len(snapshot.modules_builtin),
        },
        "critical_drivers": critical,
        "boot_hashes": dict(sorted(snapshot.boot_hashes.items())),
        "findings": findings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only SL101 kernel artifact coherence gate. Compares running "
            "kernel config, /boot/config, module metadata/files, and critical "
            "ASUS EC/KBC built-in state."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--root",
        type=Path,
        default=Path("/"),
        help="inspect a local/fixture root (default: /)",
    )
    group.add_argument(
        "--ssh",
        metavar="USER@HOST",
        help="capture the same evidence read-only over SSH",
    )
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        snapshot = collect_ssh(args.ssh) if args.ssh else collect_root(args.root)
        result = analyze(snapshot)
    except (OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    print(
        json.dumps(
            result,
            indent=2 if args.pretty else None,
            sort_keys=True,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0 if result["coherent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
