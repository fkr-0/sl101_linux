#!/usr/bin/env python3
"""Read-only Linux ARMHF DT_NEEDED closure and attribute audit.

Checks real ELF objects and their direct/transitive DT_NEEDED names against
a supplied ARMHF runtime root. This is NOT a dlopen/module/plugin scan,
instruction-level ISA proof, sandbox validation, or device qualification.
Never executes a target ELF. Exit 1 if any dependency or attribute fails.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import re
import subprocess
import sys

NEEDED = re.compile(r"\(NEEDED\).*Shared library: \[([^\]]+)\]")
MACHINE = re.compile(r"Machine:\s*(.*)")
FLAGS = re.compile(r"Flags:\s*(.*)")
CPU = re.compile(r"Tag_CPU_arch:\s*(.*)")
FPU = re.compile(r"Tag_FP_arch:\s*(.*)")
SIMD = re.compile(r"Tag_Advanced_SIMD_arch:\s*(.*)")

DEFAULT_DIRS = (
    "/usr/lib/arm-linux-gnueabihf",
    "/lib/arm-linux-gnueabihf",
    "/usr/local/lib/arm-linux-gnueabihf",
)


def read_elf(path: Path, flag: str) -> str:
    result = subprocess.run(
        ["readelf", flag, str(path)], capture_output=True, text=True,
        timeout=40, check=False,
    )
    if result.returncode:
        raise ValueError(f"readelf {flag} failed on {path}: exit {result.returncode}")
    return result.stdout


def match_first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def inspect_elf(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError(f"not ELF: {path}")
    header = read_elf(path, "-h")
    attributes = read_elf(path, "-A")
    dynamic = read_elf(path, "-d")
    machine = match_first(MACHINE, header)
    flags = match_first(FLAGS, header)
    cpu = match_first(CPU, attributes)
    fpu = match_first(FPU, attributes)
    simd = match_first(SIMD, attributes)
    needed = NEEDED.findall(dynamic)
    problems: list[str] = []
    if not machine or not re.search(r"^ARM(?:\s|$)", machine):
        problems.append("not ARM ELF")
    if not flags or "hard-float ABI" not in flags:
        problems.append("not ARM EABI hard-float")
    if simd:
        problems.append(f"advanced SIMD declared: {simd}")
    return {
        "path": str(path),
        "needed": needed,
        "machine": machine,
        "flags": flags,
        "cpu": cpu,
        "fp": fpu,
        "simd": simd,
        "problems": problems,
    }


def libindex(directories: list[Path]) -> dict[str, Path]:
    """Index first exact armhf library name, never a host x86 path."""
    index: dict[str, Path] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.name not in index and path.is_file() and (
                ".so" in path.name or path.name.startswith("ld-linux")
            ):
                index[path.name] = path
    return index


def closure(entry: Path, directories: list[Path], max_files: int = 1024) -> dict[str, object]:
    idx = libindex(directories)
    queue: deque[Path] = deque([entry])
    visited: set[Path] = set()
    records: list[dict[str, object]] = []
    missing: list[dict[str, str]] = []
    errors: list[str] = []
    while queue:
        raw = queue.popleft()
        path = raw.resolve(strict=True)
        if path in visited:
            continue
        visited.add(path)
        if len(visited) > max_files:
            errors.append(f"closure cap exceeded ({max_files})")
            break
        try:
            record = inspect_elf(path)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
            continue
        records.append(record)
        for name in record["needed"]:
            dep = idx.get(str(name))
            if dep is None:
                missing.append({"from": str(path), "soname": str(name)})
            else:
                queue.append(dep)
    bad = [
        {"path": record["path"], "problems": record["problems"]}
        for record in records if record["problems"]
    ]
    passed = not (missing or errors or bad)
    return {
        "schema": "sl101.nurabrowser.needed-closure.v1",
        "pass": passed,
        "scope": "DT_NEEDED closure and ARMHF/NEON ELF attributes only",
        "qualifies_full_instruction_closure": False,
        "qualifies_runtime_or_device": False,
        "elf_count": len(records),
        "missing": missing,
        "errors": errors,
        "unsafe": bad,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--libdir", action="append", type=Path)
    args = parser.parse_args()
    directories = args.libdir or [Path(path) for path in DEFAULT_DIRS]
    try:
        report = closure(args.entry, directories)
    except (OSError, ValueError) as exc:
        print(f"closure audit failure: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "pass": report["pass"],
        "elf_count": report["elf_count"],
        "missing": report["missing"][:15],
        "unsafe": report["unsafe"][:15],
        "errors": report["errors"][:15],
        "report": str(args.output),
    }, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
