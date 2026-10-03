#!/usr/bin/env python3
"""Inspect, then optionally write the private SL101 image to unmounted removable SD."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path, count=None):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while count is None or count > 0:
            chunk = stream.read(min(4 * 1024 * 1024, count) if count is not None else 4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            if count is not None:
                count -= len(chunk)
    if count:
        raise SystemExit('Short read from target')
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('device', type=Path)
    parser.add_argument('--write', action='store_true', help='Overwrite the inspected removable SD card')
    args = parser.parse_args()
    image = args.image.resolve(strict=True)
    expected = Path(str(image) + '.sha256').read_text().split()[0]
    if digest(image) != expected:
        raise SystemExit('Image checksum mismatch')
    device = args.device.resolve(strict=True)
    tree = json.loads(subprocess.check_output([
        'lsblk', '--json', '--bytes', '--paths', '--output',
        'NAME,TYPE,SIZE,RM,MOUNTPOINTS,MODEL,SERIAL', str(device)]))['blockdevices']
    if len(tree) != 1:
        raise SystemExit('Select exactly one whole SD device')
    target = tree[0]
    if target['name'] != str(device) or target['type'] != 'disk' or not target['rm']:
        raise SystemExit('Target must be a whole removable SD device')
    if target['size'] < image.stat().st_size:
        raise SystemExit('Target is too small')
    def mounted(node):
        return any(node.get('mountpoints') or []) or any(mounted(n) for n in node.get('children', []))
    if mounted(target):
        raise SystemExit('Unmount all target partitions and disable target swap first')
    print(json.dumps(target, indent=2))
    if not args.write:
        print('Inspection only. Add --write to overwrite this SD card.')
        return
    subprocess.run(['dd', f'if={image}', f'of={device}', 'bs=4M', 'conv=fsync', 'status=progress'], check=True)
    if digest(device, image.stat().st_size) != expected:
        raise SystemExit('SD readback checksum mismatch')
    subprocess.run(['blockdev', '--rereadpt', str(device)], check=True)
    print('Written and readback verified. Cold-boot validation is still required.')


if __name__ == '__main__':
    main()
