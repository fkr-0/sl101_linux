#!/usr/bin/env python3
"""Compatibility CLI for the canonical NuraBrowser ARMHF runtime closure audit.

An attribute-only check is a screen, never a shipping qualification.
Retains --entry/--output/--libdir but delegates resolution/ISA decisions to
scripts/audit-runtime-closure.py.
"""
from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

CORE = Path(__file__).resolve().parents[1] / "scripts/audit-runtime-closure.py"
spec = spec_from_file_location("nurabrowser_canonical_closure", CORE)
assert spec is not None and spec.loader is not None
canonical = module_from_spec(spec)
spec.loader.exec_module(canonical)


def closure(entry: Path, directories: list[Path] | None = None,
            root: Path = Path("/"), max_files: int = 2048) -> dict:
    """Legacy output shape with explicit *non-release* attribute gate."""
    result = canonical.scan(
        root, entry, full=False, objdump="arm-linux-gnueabihf-objdump",
        library_dirs=tuple(map(str, directories)) if directories else canonical.LIB_DIRS,
        max_files=max_files,
    )
    unsafe_by_path: dict[str, list[str]] = {}
    for issue in result["forbidden"]:
        unsafe_by_path.setdefault(issue["path"], []).append(issue["reason"])
    unsafe = [{"path": path, "problems": problems}
              for path, problems in sorted(unsafe_by_path.items())]
    # The earlier "pass=true" was possible despite no disassembly/loader
    # or WPE plugin and child-process coverage. Never claim release pass.
    return {
        "schema": "sl101.nurabrowser.needed-closure.v2",
        "pass": False,
        "attributes_clean": not result["missing"] and not unsafe,
        "scope": "DT_NEEDED + PT_INTERP; ARMHF + FP/NEON attributes only",
        "qualifies_full_instruction_closure": False,
        "qualifies_runtime_or_device": False,
        "elf_count": result["files_scanned"],
        "missing": result["missing"],
        "errors": [],
        "unsafe": unsafe,
        "records": result["files"],
        "limitations": result["limitations"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--libdir", action="append", type=Path)
    parser.add_argument("--max-files", type=int, default=2048)
    args = parser.parse_args()
    if args.max_files < 1:
        parser.error("--max-files must be positive")
    try:
        result = closure(args.entry, args.libdir, args.root, args.max_files)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"closure audit failed closed: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "pass": result["pass"], "attributes_clean": result["attributes_clean"],
        "elf_count": result["elf_count"],
        "missing": result["missing"][:15],
        "unsafe": result["unsafe"][:15],
        "report": str(args.output),
    }, indent=2))
    # Attribute-only report is never sufficient for release.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
