#!/usr/bin/env python3
"""Generate a local integrity manifest ONLY from a real ARMHF build artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qualify import audit_elf  # noqa: E402


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def make_manifest(executable: Path) -> dict:
    errors = audit_elf(executable)
    if errors:
        raise ValueError("ARMHF/NEON audit failed: " + "; ".join(errors))
    launcher = ROOT / "scripts/launch.sh"
    return {
        "schema": "sl101.nurabrowser.artifact-manifest.v1",
        "status": "static-armhf-audited-not-runtime-qualified",
        "target": "armv7-linux-gnueabihf-vfpv3-d16-no-neon",
        "wpe_debian_version": "2.54.0-2",
        "public_command": ",browse",
        "artifacts": [
            {"install_path": "/usr/libexec/nura-browser/nurabrowser-core",
             "sha256": digest(executable), "size": executable.stat().st_size},
            {"install_path": "/usr/bin/,browse",
             "sha256": digest(launcher), "size": launcher.stat().st_size},
        ],
        "readiness": {"compiled_armhf": True, "on_device": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = make_manifest(args.build_dir / "nurabrowser-core")
    except ValueError as exc:
        print(f"Refusing package manifest: {exc}", file=sys.stderr)
        return 1
    # Manifest output is an explicit local file, never a deployment or system path.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote ARMHF-only manifest: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
