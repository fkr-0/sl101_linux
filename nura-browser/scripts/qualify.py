#!/usr/bin/env python3
"""Offline, fail-closed WPE 2.54 + ARMv7 hard-float no-NEON build gate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

DEPS = ("glib-2.0", "gio-2.0", "gio-unix-2.0", "gobject-2.0",
        "wpe-webkit-2.0", "wpe-platform-2.0", "json-glib-1.0")
HEADERS = ("wpe/webkit.h", "wpe/wpe-platform.h")
TOOLS = ("arm-linux-gnueabihf-gcc", "arm-linux-gnueabihf-ar",
         "arm-linux-gnueabihf-strip", "arm-linux-gnueabihf-objdump")
FORBIDDEN_SOURCE = (
    re.compile(r"\bWPEBackend[-_]fdo\b"),
    re.compile(r"#\s*include\s*[<\"](?:wpebackend-fdo|wpe/wpebackend)"),
    re.compile(r"\bwpe_view_backend_(?:new|create)\b"),
    re.compile(r"\bwebkit_web_view_backend_new\b"),
    re.compile(r"\bwpe_loader_init\b"),
)
FORBIDDEN_REGISTER = re.compile(r"\b(?:q(?:[0-9]|[12][0-9]|3[01])|d(?:1[6-9]|2[0-9]|3[01]))\b", re.I)
FORBIDDEN_OPCODE = re.compile(r"\b(?:vld[1-4]|vst[1-4]|vtbl|vtbx|vdup|vext|vzip|vuzp|vtrn)\b", re.I)


def run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, env=env)


def parse_status(text: str) -> dict[str, dict[str, str]]:
    result = {}
    for stanza in re.split(r"\n\s*\n", text):
        fields = dict(line.split(": ", 1) for line in stanza.splitlines()
                      if line and not line[0].isspace() and ": " in line)
        if "Package" in fields:
            result[fields["Package"]] = fields
    return result


def dependency_gate(env: dict[str, str], sysroot: Path | None) -> tuple[dict, list[str]]:
    checks = {}
    problems: list[str] = []
    if not shutil.which("pkg-config"):
        return checks, ["missing executable: pkg-config"]
    include_dirs: list[Path] = []
    for dep in DEPS:
        p = run("pkg-config", "--modversion", dep, env=env)
        version = p.stdout.strip() if p.returncode == 0 else None
        checks[dep] = version
        if version is None:
            problems.append(f"missing pkg-config dependency: {dep}")
        elif dep == "wpe-webkit-2.0" and not re.match(r"^2\.(5[4-9]|[6-9][0-9])\.", version):
            problems.append(f"WPE WebKit too old or unpinned major: {version}")
    for dep in ("wpe-webkit-2.0", "wpe-platform-2.0"):
        p = run("pkg-config", "--cflags-only-I", dep, env=env)
        if p.returncode == 0:
            include_dirs.extend(Path(arg[2:]) for arg in shlex.split(p.stdout) if arg.startswith("-I"))
    # pkg-config may elide /usr/include. In cross mode we do NOT accept host headers.
    if sysroot is not None:
        include_dirs.extend((sysroot / "usr/include", sysroot / "usr/include/arm-linux-gnueabihf"))
        include_dirs = [p for p in include_dirs if p.is_relative_to(sysroot)]
    else:
        include_dirs.append(Path("/usr/include"))
    headers = {}
    for header in HEADERS:
        match = next((str(directory / header) for directory in include_dirs
                      if (directory / header).is_file()), None)
        headers[header] = match
        if match is None:
            problems.append(f"missing development header: <{header}>")
    checks["headers"] = headers
    return checks, problems


def audit_elf(path: Path, objdump: str | None = None) -> list[str]:
    """Conservative ARMHF+VFPv3-D16 gate; not full dependency-closure proof."""
    errors = []
    if not path.is_file():
        return [f"ELF missing: {path}"]
    if not shutil.which("readelf"):
        return ["missing executable: readelf"]
    header = run("readelf", "-h", str(path))
    attrs = run("readelf", "-A", str(path))
    if header.returncode or attrs.returncode:
        return [f"readelf failed: {path}"]
    if not re.search(r"Machine:\s*ARM\b", header.stdout):
        errors.append("machine is not ARM")
    if "hard-float ABI" not in header.stdout:
        errors.append("ARM hard-float EABI flag missing")
    if not re.search(r"Tag_CPU_arch:\s*v7\b", attrs.stdout):
        errors.append("ARMv7 attribute missing")
    if not re.search(r"Tag_FP_arch:\s*VFPv3-D16\b", attrs.stdout):
        errors.append("VFPv3-D16 attribute missing or wrong VFP register class")
    if re.search(r"Tag_Advanced_SIMD_arch:\s*\S+", attrs.stdout):
        errors.append("NEON/advanced SIMD attribute present")
    # Readelf attributes alone cannot prove no NEON instructions. Require
    # target-aware objdump, refusing an absent/failed disassembler.
    disassembler = objdump or "arm-linux-gnueabihf-objdump"
    if not shutil.which(disassembler):
        errors.append(f"missing executable: {disassembler}")
    else:
        code = run(disassembler, "-d", str(path))
        if code.returncode:
            errors.append("ARM disassembly failed")
        else:
            for line in code.stdout.splitlines():
                match = re.match(r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2,8}\s+)+\s*([A-Za-z][\w.]*)\s*(.*)$", line)
                if not match:
                    continue
                mnemonic, operands = match.groups()
                if FORBIDDEN_OPCODE.search(mnemonic) or FORBIDDEN_REGISTER.search(operands):
                    errors.append(f"NEON/high-VFP-register instruction: {mnemonic} {operands[:100]}")
                    break
    return errors


def source_gate(root: Path) -> list[str]:
    errors = []
    for path in sorted((root / "src").rglob("*.c")):
        content = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_SOURCE:
            if pattern.search(content):
                errors.append(f"legacy backend API in {path.relative_to(root)}: {pattern.pattern}")
    return errors


def qualify(mode: str, sysroot: Path | None, elfs: list[Path]) -> dict:
    root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    checks: dict = {}
    env = dict(os.environ)
    if mode == "armhf":
        if sysroot is None or not sysroot.is_dir():
            errors.append("missing prepared ARMHF glibc sysroot: --sysroot")
        else:
            for name in TOOLS:
                if not shutil.which(name):
                    errors.append(f"missing ARMHF cross tool: {name}")
            cc = run("arm-linux-gnueabihf-gcc", "-dumpmachine") if shutil.which(TOOLS[0]) else None
            triple = cc.stdout.strip() if cc and cc.returncode == 0 else None
            checks["toolchain_triple"] = triple
            if triple != "arm-linux-gnueabihf":
                errors.append(f"wrong ARMHF cross toolchain: {triple}")
            status = sysroot / "var/lib/dpkg/status"
            if not status.is_file():
                errors.append(f"missing Debian package status: {status}")
            else:
                pkgs = parse_status(status.read_text(encoding="utf-8"))
                for pkg in ("libwpewebkit-2.0-1", "libwpewebkit-2.0-dev"):
                    found = pkgs.get(pkg, {})
                    checks[pkg] = {k: found.get(k) for k in ("Version", "Architecture", "Status")}
                    if (found.get("Version"), found.get("Architecture"), found.get("Status")) != (
                        "2.54.0-2", "armhf", "install ok installed"
                    ):
                        errors.append(f"missing pinned Debian ARMHF package {pkg}=2.54.0-2")
            # Avoid implicit host pkg-config fallback in a cross build.
            libdir = [sysroot / "usr/lib/arm-linux-gnueabihf/pkgconfig",
                      sysroot / "usr/share/pkgconfig"]
            env["PKG_CONFIG_LIBDIR"] = os.pathsep.join(map(str, libdir))
            env["PKG_CONFIG_SYSROOT_DIR"] = str(sysroot)
            env["PKG_CONFIG_PATH"] = ""
    deps, missing = dependency_gate(env, sysroot)
    checks["dependencies"] = deps
    errors.extend(missing)
    errors.extend(source_gate(root))
    checks["elf"] = {}
    for elf in elfs:
        audit = audit_elf(elf)
        checks["elf"][str(elf)] = audit or "pass"
        errors.extend(audit)
    return {
        "schema": "sl101.nurabrowser.build-qualification.v1",
        "mode": mode,
        "pass": not errors,
        "checks": checks,
        "errors": errors,
        "readiness": {
            "source": "requires-source-review",
            "compiled_host": "unverified",
            "armhf": "qualified-elf" if mode == "armhf" and elfs and not errors else "unverified",
            "on_device": "not-tested",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("host", "armhf"), default="host")
    parser.add_argument("--sysroot", type=Path)
    parser.add_argument("--elf", action="append", type=Path, default=[])
    args = parser.parse_args()
    result = qualify(args.mode, args.sysroot.resolve() if args.sysroot else None, args.elf)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
