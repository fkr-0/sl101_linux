#!/usr/bin/env python3
"""Fail-closed proof of kernel, DTB, module release and VDE patch inclusion.

This only examines build artifacts. It never opens SSH or changes boot slots.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def probe_module(path: Path, field: str) -> str:
    return subprocess.run(['modinfo', '-F', field, str(path)], check=True,
                          capture_output=True, text=True).stdout


def verify(root: Path, release: str, expected_dtb_sha: str | None = None) -> list[str]:
    errors = []
    image = root / 'out/arch/arm/boot/zImage'
    dtb = root / 'out/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb'
    version = root / 'out/include/config/kernel.release'
    modpath = root / 'modules/lib/modules' / release
    if not version.is_file() or version.read_text().strip() != release:
        errors.append('wrong/missing release marker')
    if not image.is_file() or image.stat().st_size < 1024 * 1024:
        errors.append('missing/truncated zImage')
    if not dtb.is_file() or (expected_dtb_sha and sha(dtb) != expected_dtb_sha):
        errors.append('missing or mismatched production DTB')
    modules = sorted(modpath.glob('kernel/**/*.ko.zst')) if modpath.is_dir() else []
    if len(modules) < 500:
        errors.append(f'missing/incomplete matching module tree: {len(modules)} modules')
    if not (modpath / 'modules.dep').is_file():
        errors.append('missing depmod index')
    vde = modpath / 'kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst'
    if not vde.exists():
        errors.append('tegra-vde module absent')
    else:
        try:
            # Nonnegotiable: the cached noncoherent CAPTURE VDE-v2 patch must
            # actually be compiled into the module, not merely on disk.
            params = probe_module(vde, 'parm')
            if 'cached_capture' not in params:
                errors.append('VDE cached_capture parameter ABSENT (VDE v2 patch missing)')
            if not probe_module(vde, 'vermagic').strip().startswith(release + ' '):
                errors.append('VDE module vermagic mismatch')
        except (OSError, subprocess.CalledProcessError) as e:
            errors.append(f'modinfo failed: {e}')
    return errors


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--release', required=True)
    p.add_argument('--expected-dtb-sha', default='')
    args = p.parse_args()
    errors = verify(args.root, args.release, args.expected_dtb_sha or None)
    for message in errors:
        print('BLOCKER:', message, file=sys.stderr)
    if errors:
        return 2
    print(f'KERNEL_STAGE_PREFLIGHT_OK release={args.release}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
