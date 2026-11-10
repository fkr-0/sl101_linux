#!/usr/bin/env python3
"""Read-only preflight for the *hard* SL101 public-command comma cutover.

There is intentionally NO alias manifest. Deployed public executable
filenames, in the checked-in /usr/local/bin staging trees, are the
sole authority. Inventory and cross-file references are computed.

No SSH, device mutations, file renames, or output-file writes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = (
    "docs/sl101-device-config/usr/local/bin",
    "docs/sl101-debian-device-config/usr/local/bin",
    "deploy/ansible/public/nura",
    "deploy/ansible/public/debian",
)
REFS = (
    "docs/sl101-device-config",
    "docs/sl101-debian-device-config",
    "debian-rootbind/config",
    "scripts",
    "deploy/ansible",
)
EXTENSIONS = {
    ".sh", ".py", ".toml", ".ini", ".cfg", ".conf", ".yaml", ".yml",
    ".json", ".xml", ".desktop", ".service", ".socket", ".target", ".timer",
    ".init", ".bash", ".zsh", ".fish", ".js", ".ts", ".env", ".rules",
}
BARE_NAMES = {
    "autostart", "config", "environment", "rc.xml", "sway", "sway.config",
    "profile", "bashrc", "zshrc", "xinitrc", "keyd", "rc.local",
}
SKIP_DIRS = {
    ".git", ".state", "node_modules", ".venv", "__pycache__", "build",
    "cache", ".cache", ".gitignore", "assets", "output", "tmp",
}
CUSTOM_PREFIX = ("sl101-", "nuraloumi-")
COMMA = re.compile(r"^,[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class Reference:
    file: str
    line: int
    snippet: str


@dataclass
class Command:
    name: str
    proposed: str
    source: str
    target: str
    status: str
    references: list[Reference]


def _safe_repo_path(root: Path, raw: str) -> Path:
    p = (root / raw).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {raw}") from exc
    return p


def _text_sources(path: Path):
    if path.is_file() and not path.is_symlink():
        yield path
    elif path.is_dir() and not path.is_symlink():
        for p in sorted(path.rglob("*")):
            if (not p.is_file() or p.is_symlink()
                    or set(p.relative_to(path).parts[:-1]) & SKIP_DIRS):
                continue
            if p.suffix in EXTENSIONS or p.name in BARE_NAMES:
                yield p


def _text(path: Path) -> str | None:
    try:
        if path.stat().st_size > 512 * 1024:
            return None
        data = path.read_bytes()
        if b"\0" in data[:1024]:
            return None
        return data.decode("utf-8")
    except (OSError, UnicodeError):
        return None


def _public_names(root: Path, dirs: tuple[str, ...]):
    for raw in dirs:
        public_dir = _safe_repo_path(root, raw)
        if not public_dir.is_dir():
            continue
        for p in sorted(public_dir.iterdir()):
            if p.is_dir() or p.name.startswith("."):
                continue
            if p.is_symlink():
                # A public link is a compatibility alias, not a canonical
                # source. Always flag instead of following it.
                kind = "symlink"
            elif p.is_file():
                kind = "file"
            else:
                kind = "unknown"
            yield p, raw, kind


def audit(root: Path, public_dirs=PUBLIC, refs_dirs=REFS) -> dict:
    root = root.resolve()
    names = []
    scanroots = tuple(refs_dirs)
    for path, directory, kind in _public_names(root, tuple(public_dirs)):
        name = path.name
        if COMMA.fullmatch(name):
            proposed = name
            status = "canonical" if kind == "file" else "symlink-not-allowed"
        elif name.startswith(CUSTOM_PREFIX):
            proposed = "," + name.split("-", 1)[1]
            status = "legacy" if kind == "file" else "symlink-not-allowed"
        else:
            proposed = ""
            status = "unclassified"
        if proposed and not COMMA.fullmatch(proposed):
            status = "invalid-name"
        names.append((name, proposed, path.relative_to(root).as_posix(),
                      directory, status))

    # Scanner intentionally ignores Markdown prose, build artifacts, and
    # arbitrary binary files: this is an *active config/script* gate,
    # not a repo-wide grep or a claim to know device runtime state.
    source_texts: dict[str, str] = {}
    # Public wrappers often have NO file suffix; scan their contents as
    # first-class active references. Do not mistake a command's own name
    # merely appearing as its source filename for an executable call.
    for path, _directory, _kind in _public_names(root, tuple(public_dirs)):
        if path.is_file() and not path.is_symlink():
            value = _text(path)
            if value is not None:
                source_texts[path.relative_to(root).as_posix()] = value
    for raw in scanroots:
        path = _safe_repo_path(root, raw)
        for source in _text_sources(path):
            value = _text(source)
            if value is not None:
                source_texts[source.relative_to(root).as_posix()] = value

    old_names = set(name for name, proposed, *_ in names
                    if proposed and not name.startswith(","))
    # After the old public file disappears it can still be invoked by
    # stale Sway/OpenRC/script callers. Infer possible old names from the
    # *canonical filename*, not a redundant alias registry.
    inferred = set()
    for name, proposed, *_ in names:
        if name.startswith(",") and proposed:
            inferred.update(prefix + name[1:] for prefix in CUSTOM_PREFIX)
    old_names = sorted(old_names | inferred)
    patterns = {
        name: re.compile(r"(?<![A-Za-z0-9_,.-])" + re.escape(name)
                         + r"(?![A-Za-z0-9_-])") for name in old_names
    }
    refs: dict[str, list[Reference]] = defaultdict(list)
    for relpath, value in source_texts.items():
        for number, line in enumerate(value.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(("#", "//", "/*", "*")):
                continue
            for name, pattern in patterns.items():
                if pattern.search(line):
                    refs[name].append(Reference(relpath, number, line.strip()[:180]))

    live_legacy_names = {name for name, proposed, *_ in names
                         if proposed and not name.startswith(",")}
    stale_references = [
        {"legacy": name, "references": [asdict(ref) for ref in matches]}
        for name, matches in sorted(refs.items())
        if name not in live_legacy_names and matches
    ]
    collisions = defaultdict(list)
    for name, proposed, source, target, status in names:
        if proposed:
            collisions[(target, proposed)].append(source)

    commands = [
        Command(name, proposed, source, target, status, refs.get(name, []))
        for name, proposed, source, target, status in names
    ]
    blocked = [
        {"target": target, "command": proposed, "sources": paths}
        for (target, proposed), paths in sorted(collisions.items())
        if len(paths) > 1
    ]
    legacy = [c for c in commands if c.status == "legacy"]
    invalid = [c for c in commands
               if c.status not in ("legacy", "canonical")]
    blockers = (len(legacy) + len(invalid) + len(blocked)
                + len(stale_references))
    return {
        "schema": "sl101-public-command-hard-cutover-audit-v1",
        "mode": "offline-read-only",
        "source": "public executable filenames; no alias manifest",
        "public_count": len(commands),
        "legacy_count": len(legacy),
        "reference_count": sum(len(c.references) for c in commands),
        "canonical_count": len([c for c in commands if c.status == "canonical"]),
        "unsafe_count": len(invalid),
        "collisions": blocked,
        "stale_references": stale_references,
        "blockers": blockers,
        "gate_pass": blockers == 0,
        "commands": [asdict(c) for c in commands],
        "limitations": (
            "Not a live device inventory. Dynamic/indirect launch references "
            "and shell aliases must also be inspected before a hard switch."
        ),
    }


def markdown(result: dict) -> str:
    lines = [
        "# SL101 public command cutover audit",
        "",
        f"Public source entries: **{result['public_count']}**; "
        f"legacy **{result['legacy_count']}**; canonical "
        f"**{result['canonical_count']}**; "
        f"active textual references **{result['reference_count']}**.",
        "",
        "| Source target | Installed basename | Canonical name | Status | Active refs |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for c in result["commands"]:
        lines.append(f"| {c['target']} | `{c['name']}` | "
                     f"`{c['proposed'] or 'REVIEW'}` | "
                     f"{c['status']} | {len(c['references'])} |")
    lines.extend(["", "## Cutover blockers", ""])
    if result["collisions"]:
        lines.extend(
            f"- Collision in {c['target']} for `{c['command']}`: "
            + ", ".join(c["sources"]) for c in result["collisions"]
        )
    if result["legacy_count"]:
        lines.append("- Legacy public filenames remain: hard cutover not complete.")
    for stale in result["stale_references"]:
        lines.append(f"- Dangling legacy caller of `{stale['legacy']}` despite "
                     f"removed public executable: "
                     + ", ".join(f"{x['file']}:{x['line']}" for x in stale['references'][:6]))
    if result["unsafe_count"]:
        lines.append("- Unclassified names or public symlinks require review.")
    if not result["blockers"]:
        lines.append("- No filename-level blockers; runtime callers still need a live audit.")
    lines.extend(["", "## Active references", ""])
    for c in result["commands"]:
        if c["references"]:
            lines.append(f"### `{c['name']}` → `{c['proposed']}`")
            for ref in c["references"][:60]:
                lines.append(f"- {ref['file']}:{ref['line']}: `{ref['snippet']}`")
            if len(c["references"]) > 60:
                lines.append(f"- … {len(c['references']) - 60} additional references")
    lines.extend(["", f"_Limitation: {result['limitations']}_"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--public-dir", action="append",
                        help="Override default public directories; repeat as needed")
    parser.add_argument("--refs-dir", action="append",
                        help="Override default active reference directories; repeat")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--gate", action="store_true",
                        help="Nonzero exit when legacy/unclassified/colliding command remains")
    args = parser.parse_args()
    try:
        result = audit(args.root, args.public_dir or PUBLIC, args.refs_dir or REFS)
    except ValueError as exc:
        print(f"audit: {exc}", file=sys.stderr)
        return 64
    print(json.dumps(result, indent=2, sort_keys=True) if args.format == "json"
          else markdown(result), end="")
    return 2 if args.gate and not result["gate_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
