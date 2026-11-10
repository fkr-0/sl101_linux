#!/usr/bin/env python3
"""Fail-closed, host-only final validation of an SL101 hard comma cutover.

The user explicitly does NOT want a parallel legacy command namespace or
a second alias manifest. Derive the old set from actual source filenames;
assert that every active executable invocation is migrated before any
device changes. Text heuristics deliberately fail closed on ambiguities.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

PROFILES = {
    "nura": "docs/sl101-device-config",
    "debian": "docs/sl101-debian-device-config",
}
ACTIVE_RELATIVE = (
    "etc/init.d",
    "etc/systemd",
    "etc/keyd",
    "home/user/.config",
    "usr/share/applications",
)
EXCLUDED = {"README", "README.md", ".gitignore"}
EXCLUDED_DIRS = {".git", "__pycache__", ".cache", "node_modules", "build"}
MAX_FILE = 1024 * 1024


def is_active(path: Path) -> bool:
    if path.is_symlink() or not path.is_file() or path.name in EXCLUDED:
        return False
    if path.name.startswith(".") and path.name not in (".profile",):
        return False
    if any(p in EXCLUDED_DIRS for p in path.parts):
        return False
    return path.stat().st_size <= MAX_FILE


def get_old_names(template_dir: Path) -> list[str]:
    original = template_dir / "usr/local/bin"
    if not original.is_dir():
        raise ValueError("device public source directory missing")
    names = []
    for p in sorted(original.iterdir()):
        if p.name.startswith("sl101-") and p.is_file() and not p.is_symlink():
            names.append(p.name)
    if not names:
        raise ValueError("no canonical public source filenames found")
    return names


def executable_reference(line: str, old: str) -> bool:
    """Consider only code lines that attempt to invoke an executable.

    Service unit names (`rc-service sl101-desktop`), pid/lock/status file
    names and standalone labels are *not* public command invocations.
    """
    s = line.strip()
    if not s or s.startswith(("#", "//", ";")):
        return False
    escaped = re.escape(old)
    # Real absolute command path. Reject suffix path labels.
    if re.search(r"/usr/local/bin/" + escaped + r"(?![A-Za-z0-9_.-])", s):
        return True
    # XDG desktop Exec keys may rely on PATH rather than absolute names.
    if s.startswith("Exec=") and re.search(r"(?<=Exec=)" + escaped +
                                            r"(?![A-Za-z0-9_.-])", s):
        return True
    # Bare shell invocations in active config: explicit exec/command/sudo.
    if re.search(
        r"\b(?:exec|command\s+-v|sudo(?:\s+-n)?|env\s+-i)"
        r"\s+" + escaped + r"(?![A-Za-z0-9_.-])", s
    ):
        return True
    # Explicit Sway exec action (including `exec --no-startup-id foo`).
    if re.search(r"\bexec\s+(?:--[a-z-]+\s+)*" +
                 escaped + r"(?![A-Za-z0-9_.-])", s):
        return True
    # A command at start of a shell statement with optional environment
    # assignments or control operators.
    if re.search(r"(^|[;&|()]\s*)" + escaped +
                 r"(?=\s|$|;|[&|()])", s):
        return True
    return False


def scan_file(path: Path, names: list[str], location: str) -> list[dict]:
    if not is_active(path):
        return []
    raw = path.read_bytes()
    if b"\0" in raw[:4096]:
        return []
    try:
        data = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"invalid active UTF-8 file {location}") from exc
    unresolved = []
    heredoc_marker = None
    for number, line in enumerate(data.splitlines(), 1):
        if heredoc_marker is not None:
            if line.strip() == heredoc_marker:
                heredoc_marker = None
            continue
        # Literal help/usage and embedded fixture examples aren't commands.
        # The introducer itself may still invoke a real binary: scan it first.
        delimiter = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        for old in names:
            if executable_reference(line, old):
                unresolved.append({
                    "file": location,
                    "line": number,
                    "command": old,
                    "text": line.strip()[:200],
                })
        if delimiter:
            heredoc_marker = delimiter.group(1)
    return unresolved


def validate(workspace: Path, profile: str, output: Path) -> dict:
    workspace = workspace.resolve()
    output = output.resolve()
    if profile not in PROFILES:
        raise ValueError("unknown deployment profile")
    template_dir = workspace / PROFILES[profile]
    names = get_old_names(template_dir)
    canonical_dir = output / "bin"
    generated_config = output / "config"
    # These basename patterns denote launchers owned by service/root
    # infrastructure, not intentionally user-facing programs. Block
    # publication in /usr/local/bin until their source is moved into
    # libexec and their service callers are migrated. This is a POLICY
    # guard, not a redundant alias registry.
    private_sources = [
        name for name in names
        if name.endswith("-root") or name == "sl101-desktop"
    ]
    if not canonical_dir.is_dir() or not generated_config.is_dir():
        raise ValueError("rendered commands/config not present")
    canonical = sorted(
        p.name for p in canonical_dir.iterdir()
        if p.is_file() and p.name.startswith(",")
    )
    expected = {"," + x[6:] for x in names}
    missing = sorted(expected.difference(canonical))
    if missing:
        raise ValueError(f"missing canonical binaries: {missing}")
    if any(p.is_symlink() for p in canonical_dir.iterdir()):
        raise ValueError("symlinks in rendered public executable directory")

    problems = []
    # Scan all rendered scripts and active configurations, not just
    # chmod +x files; mode does not prove a configuration is harmless.
    for base in (canonical_dir, generated_config):
        for p in sorted(base.rglob("*")):
            problems.extend(scan_file(p, names, str(p.relative_to(output))))

    # The render step is intentionally selective. Detect *unrendered*
    # owned configurations still launching old binaries and refuse to
    # remove those entrypoints. This is not a new command registry.
    for rel in ACTIVE_RELATIVE:
        source = template_dir / rel
        if not source.exists():
            continue
        for p in sorted(source.rglob("*")):
            if not is_active(p):
                continue
            relative = p.relative_to(template_dir)
            replacement = generated_config / relative
            if replacement.is_file():
                continue
            problems.extend(scan_file(p, names, str(relative)))

    if profile == "nura":
        source = workspace / "scripts/sl101-user-session/desktop.init"
        if is_active(source) and not (
            generated_config / "etc/init.d/sl101-desktop").is_file():
            problems.extend(scan_file(source, names,
                                      "scripts/sl101-user-session/desktop.init"))

    return {
        "profile": profile,
        "canonical_count": len(canonical),
        "old_public_count": len(names),
        "scan": "offline-host-staged-and-unrendered-active-config",
        "unresolved_references": problems,
        "private_helpers_misclassified_as_public": private_sources,
        "gate_pass": not problems and not private_sources,
        "note": "Cannot prove dynamic commands, foreign installed files, or live device state",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(args.workspace, args.profile, args.output)
    except (ValueError, OSError) as exc:
        print(f"REFUSING_CUTOVER: {exc}", file=sys.stderr)
        return 70
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["gate_pass"]:
        print("REFUSING_CUTOVER: dangling active legacy callers OR "
              "privileged/service helpers exposed as public commands",
              file=sys.stderr)
        return 71
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
