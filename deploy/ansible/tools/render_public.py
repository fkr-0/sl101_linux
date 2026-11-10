#!/usr/bin/env python3
"""Render a hard comma-command cutover from existing, unique device templates.

No alias manifest or duplicated source trees: filenames in the existing
device-config usr/local/bin directory are the authority. This creates an
ephemeral, host-only staging tree, never connects to a device.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

PROFILES = {"nura": "docs/sl101-device-config",
            "debian": "docs/sl101-debian-device-config"}
CONFIG_FILES = (
    "home/user/.config/sway/config",
    "etc/systemd/user/sl101-desktop.service",
    "usr/share/applications/sl101-browse.desktop",
    "usr/share/applications/sl101-epiphany.desktop",
    "home/user/.config/labwc/autostart",
    "home/user/.config/labwc/rc.xml",
)


def canonical(source_name: str) -> str:
    if not re.fullmatch(r"sl101-[a-z0-9][a-z0-9-]*", source_name):
        raise ValueError(f"Not a supported public binary: {source_name}")
    return "," + source_name.removeprefix("sl101-")


def render(profile: str, workspace: Path, output: Path) -> dict:
    root = workspace / PROFILES[profile]
    binaries = root / "usr/local/bin"
    sources = sorted(p for p in binaries.iterdir()
                     if p.is_file() and p.name.startswith("sl101-"))
    if not sources:
        raise ValueError(f"No public executable templates: {binaries}")

    # Only replace executable call-sites, not service names, pidfiles,
    # process comm values, log files, or other device-specific identifiers.
    names = "|".join(re.escape(p.name) for p in sorted(sources, key=lambda p: -len(p.name)))
    pat = re.compile(
        r"(?P<prefix>/usr/local/bin/|\bexec[ \t]+|\bcommand[ \t]+-v[ \t]+|\bsudo[ \t]+(?:-n[ \t]+)?)"
        r"(?P<name>" + names + r")(?![A-Za-z0-9_-]|\.[A-Za-z0-9_-])"
    )
    # Remove obsolete generated metadata from pre-manifest-free prototypes.
    obsolete = output / "render-result.json"
    if obsolete.exists():
        obsolete.unlink()
    for stale in (output / "bin", output / "config"):
        if stale.exists():
            shutil.rmtree(stale)
        stale.mkdir(parents=True, exist_ok=True)

    def rewrite(data: str) -> str:
        return pat.sub(lambda m: m.group("prefix") + canonical(m.group("name")), data)

    binaries_out = []
    for source in sources:
        target = output / "bin" / canonical(source.name)
        original = source.read_text()
        if not original.startswith("#!"):
            raise ValueError(f"Non-script executable requires binary distribution: {source}")
        transformed = rewrite(original)
        # Marker allows the remote playbook to distinguish an executable
        # previously managed by this role from an unrelated comma-command.
        shebang, separator, rest = transformed.partition("\n")
        if not separator:
            raise ValueError(f"Executable script has no complete shebang: {source}")
        target.write_text(shebang + "\n# Managed by SL101 Ansible public-command cutover\n" + rest)
        target.chmod(0o755)
        if target.read_text().startswith("#!/bin/sh") or target.read_text().startswith("#!/bin/bash"):
            check = subprocess.run(["sh" if target.read_text().startswith("#!/bin/sh") else "bash",
                                    "-n", str(target)], capture_output=True, text=True)
            if check.returncode:
                raise ValueError(f"Shell syntax {source}: {check.stderr}")
        binaries_out.append(target.name)

    # Owned static configuration, not arbitrary application data. Each file is
    # rendered directly from the canonical existing device template.
    config_out = []
    for relative in CONFIG_FILES:
        source = root / relative
        if not source.is_file():
            continue
        target = output / "config" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rewrite(source.read_text()))
        target.chmod(0o644)
        config_out.append(relative)
    if profile == "nura":
        # OpenRC service NAME remains sl101-desktop, but command= must point
        # to the renamed executable. Keep pidfile/socket/log paths intact.
        source = workspace / "scripts/sl101-user-session/desktop.init"
        if not source.is_file():
            raise ValueError("Missing canonical Nura OpenRC desktop service source")
        target = output / "config/etc/init.d/sl101-desktop"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rewrite(source.read_text()))
        target.chmod(0o755)
        config_out.append("etc/init.d/sl101-desktop")
    extra = workspace / "deploy/ansible/public" / profile
    if extra.is_dir():
        for source in sorted(extra.iterdir()):
            if source.name.startswith(",") and source.is_file():
                target = output / "bin" / source.name
                if target.exists():
                    raise ValueError(f"Duplicate canonical public command {target.name}")
                shutil.copy2(source, target)
                target.chmod(0o755)
                binaries_out.append(target.name)
    if len(binaries_out) != len(set(binaries_out)):
        raise ValueError("Canonical command collision")
    # Return ephemeral diagnostics on stdout; create NO command manifest.
    result = dict(profile=profile, commands=sorted(binaries_out),
                  configs=sorted(config_out))
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", choices=sorted(PROFILES), required=True)
    p.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(render(args.profile, args.workspace.resolve(), args.output.resolve()),
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
