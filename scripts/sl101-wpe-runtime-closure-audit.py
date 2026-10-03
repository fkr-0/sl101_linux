#!/usr/bin/env python3
"""Audit the complete ARMHF runtime closure of an SL101 WPE private root.

Unlike the earlier selected-package audit, this entrypoint requires a prepared
Debian root with dpkg status metadata and audits every ELF object under that
root. It performs no network or device access.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUDITOR = REPO / "work/sl101-wpe-armhf-build-qualification-20261003/audit-armhf-elf.py"
DEFAULT_ROOT_PACKAGES = ("libwpewebkit-2.0-1", "cog")


def is_elf(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        with path.open("rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def _control_paragraphs(text: str) -> list[dict[str, str]]:
    paragraphs: list[dict[str, str]] = []
    for raw in text.split("\n\n"):
        raw = raw.strip("\n")
        if not raw:
            continue
        fields: dict[str, str] = {}
        current: str | None = None
        for line in raw.splitlines():
            if line.startswith((" ", "\t")) and current:
                fields[current] += " " + line.strip()
                continue
            if ": " not in line:
                current = None
                continue
            current, value = line.split(": ", 1)
            fields[current] = value
        paragraphs.append(fields)
    return paragraphs


def parse_dpkg_status(text: str) -> dict[str, dict[str, str]]:
    packages: dict[str, dict[str, str]] = {}
    for fields in _control_paragraphs(text):
        if fields.get("Status") != "install ok installed":
            continue
        name = fields.get("Package")
        if name:
            packages[name] = fields
    return packages


def _dep_name(spec: str) -> str:
    spec = spec.strip()
    for marker in (" (", " [", " <"):
        spec = spec.split(marker, 1)[0]
    parts = spec.split()
    token = parts[0] if parts else ""
    if ":" in token:
        token = token.split(":", 1)[0]
    return token


def dependency_groups(fields: dict[str, str]) -> list[list[str]]:
    result: list[list[str]] = []
    for field in ("Pre-Depends", "Depends"):
        value = fields.get(field, "")
        if not value:
            continue
        for group in value.split(","):
            alternatives = [_dep_name(item) for item in group.split("|")]
            alternatives = [item for item in alternatives if item]
            if alternatives:
                result.append(alternatives)
    return result


def resolve_package_closure(
    packages: dict[str, dict[str, str]], roots: list[str]
) -> tuple[set[str], list[str], list[dict[str, object]]]:
    missing_roots = sorted(name for name in roots if name not in packages)
    visited: set[str] = set()
    missing_groups: list[dict[str, object]] = []
    queue: deque[str] = deque(name for name in roots if name in packages)

    while queue:
        name = queue.popleft()
        if name in visited:
            continue
        visited.add(name)
        for alternatives in dependency_groups(packages[name]):
            chosen = next((candidate for candidate in alternatives if candidate in packages), None)
            if chosen is None:
                missing_groups.append({"package": name, "alternatives": alternatives})
                continue
            if chosen not in visited:
                queue.append(chosen)

    return visited, missing_roots, missing_groups


def discover_elfs(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*") if is_elf(path)}


def evaluate(
    root: Path,
    packages: dict[str, dict[str, str]],
    raw_audit: dict,
    root_packages: list[str],
    allowed_failures: set[str],
) -> dict:
    closure, missing_roots, missing_groups = resolve_package_closure(packages, root_packages)
    discovered = discover_elfs(root)
    records = raw_audit.get("records", [])
    audited = {record.get("path", "") for record in records if record.get("path")}
    missing_audit_records = sorted(discovered - audited)
    extra_audit_records = sorted(audited - discovered)

    raw_failures = {
        record.get("path", ""): list(record.get("issues", []))
        for record in records
        if record.get("path") and record.get("issues")
    }
    allowed = {
        path: issues
        for path, issues in raw_failures.items()
        if path in allowed_failures
    }
    unexpected = {
        path: issues
        for path, issues in raw_failures.items()
        if path not in allowed_failures
    }

    package_info_lists_missing = sorted(
        name
        for name in closure
        if not (root / "var/lib/dpkg/info" / f"{name}.list").is_file()
    )

    passed = not any(
        (
            missing_roots,
            missing_groups,
            missing_audit_records,
            extra_audit_records,
            package_info_lists_missing,
            unexpected,
        )
    )

    return {
        "schema": "sl101.wpe.runtime-closure-audit.v1",
        "root": str(root),
        "pass": passed,
        "root_packages": root_packages,
        "package_closure": {
            "installed_package_count": len(packages),
            "closure_package_count": len(closure),
            "packages": sorted(closure),
            "missing_root_packages": missing_roots,
            "missing_dependency_groups": missing_groups,
            "missing_dpkg_info_lists": package_info_lists_missing,
        },
        "elf_coverage": {
            "discovered_elf_count": len(discovered),
            "audited_elf_count": len(audited),
            "missing_audit_records": missing_audit_records,
            "extra_audit_records": extra_audit_records,
        },
        "isa_failures": {
            "raw_failure_count": len(raw_failures),
            "allowed": allowed,
            "unexpected": unexpected,
        },
        "policy": {
            "target": "ARMv7-A hard-float VFPv3-D16, no NEON/Advanced SIMD",
            "audit_scope": "all ELF objects in supplied prepared root",
            "dependency_scope": "recursive installed Pre-Depends/Depends from dpkg status",
            "network_access": False,
            "device_access": False,
        },
    }


def render_text(payload: dict) -> str:
    closure = payload["package_closure"]
    coverage = payload["elf_coverage"]
    failures = payload["isa_failures"]
    lines = [
        f"PASS: {payload['pass']}",
        f"Root: {payload['root']}",
        f"Closure packages: {closure['closure_package_count']}",
        f"ELF coverage: {coverage['audited_elf_count']}/{coverage['discovered_elf_count']}",
        f"Unexpected ISA failures: {len(failures['unexpected'])}",
        "",
    ]
    if closure["missing_root_packages"]:
        lines.append("Missing root packages: " + ", ".join(closure["missing_root_packages"]))
    for item in closure["missing_dependency_groups"]:
        lines.append(
            f"Missing dependency for {item['package']}: "
            + " | ".join(item["alternatives"])
        )
    for path in coverage["missing_audit_records"]:
        lines.append(f"Missing ELF audit record: {path}")
    for path, issues in failures["unexpected"].items():
        lines.append(f"ISA FAIL {path}: {', '.join(issues)}")
    for path, issues in failures["allowed"].items():
        lines.append(f"Allowed ISA failure {path}: {', '.join(issues)}")
    return "\n".join(lines) + "\n"


def run_raw_auditor(root: Path, raw_json: Path, raw_text: Path) -> dict:
    if not AUDITOR.is_file():
        raise RuntimeError(f"missing ARMHF auditor: {AUDITOR}")
    proc = subprocess.run(
        [
            sys.executable,
            str(AUDITOR),
            str(root),
            "--json",
            str(raw_json),
            "--text",
            str(raw_text),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"ARMHF auditor failed rc={proc.returncode}: {proc.stdout}{proc.stderr}"
        )
    return json.loads(raw_json.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="complete prepared Debian ARMHF browser root")
    ap.add_argument("--json-output", default="-", help="summary JSON path or -")
    ap.add_argument("--text-output", help="optional human-readable summary path")
    ap.add_argument("--raw-audit-json", help="optional persistent raw auditor JSON path")
    ap.add_argument("--raw-audit-text", help="optional persistent raw auditor text path")
    ap.add_argument("--root-package", action="append", dest="root_packages")
    ap.add_argument(
        "--allow-failure",
        action="append",
        default=[],
        help="exact root-relative ELF path whose ISA failure is explicitly accepted",
    )
    args = ap.parse_args()

    root = args.root.resolve()
    status_path = root / "var/lib/dpkg/status"
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    if not status_path.is_file():
        raise SystemExit(
            f"prepared root must retain dpkg status metadata: missing {status_path}"
        )
    packages = parse_dpkg_status(status_path.read_text(encoding="utf-8", errors="replace"))
    roots = args.root_packages or list(DEFAULT_ROOT_PACKAGES)

    if bool(args.raw_audit_json) != bool(args.raw_audit_text):
        raise SystemExit("--raw-audit-json and --raw-audit-text must be supplied together")

    if args.raw_audit_json:
        raw_json = Path(args.raw_audit_json)
        raw_text = Path(args.raw_audit_text)
        raw_json.parent.mkdir(parents=True, exist_ok=True)
        raw_text.parent.mkdir(parents=True, exist_ok=True)
        raw = run_raw_auditor(root, raw_json, raw_text)
    else:
        with tempfile.TemporaryDirectory(prefix="sl101-wpe-closure-") as td:
            raw_json = Path(td) / "raw.json"
            raw_text = Path(td) / "raw.txt"
            raw = run_raw_auditor(root, raw_json, raw_text)

    payload = evaluate(root, packages, raw, roots, set(args.allow_failure))
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.json_output == "-":
        print(rendered, end="")
    else:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    if args.text_output:
        out = Path(args.text_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_text(payload), encoding="utf-8")
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
