#!/usr/sbin/python3
"""Root-owned, fixed-mode, runtime-only compositor switch with recovery."""
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

PREFIX = Path('/usr/local/lib/sl101-grate-32784d505bc5df524d373ef1ab8572c73640099f1b98cdbdd716eaea07289b88')
HASHES = {
 'lib/libgbm.so.1.0.0': '1c4042212d694238eaa81f924735b716dc58b2289b2deb4ff4d293c56e968415',
 'lib/libdrm_tegra.so.0.0.0': '6755a68138398759982b8ecae68c67e38c9ac518108d4c7b451642fa89656f75',
 'lib/libGLESv2.so.2.0.0': '3d85e5bb8b58270c1a77927e855ba7e76fd376014f24f50af99a2539749d87c6',
 'lib/libgallium-25.0.7.so': '32784d505bc5df524d373ef1ab8572c73640099f1b98cdbdd716eaea07289b88',
 'lib/gbm/dri_gbm.so': '5536db796752fc07654ec4fe74e5ba1acee54c83aa0937427f5a9916303afce3',
 'lib/libEGL.so.1.0.0': '0f33c2c5bce42c719dcea633edef5c6d4dfac994cd1f6ad0d812a02d4fb13148',
}
OVERRIDE = Path('/run/sl101-desktop-renderer.conf')
LOCK = Path('/run/lock/sl101-nura-qualification.lock')

def validate_grate(prefix=PREFIX):
    if os.uname().release != '7.0.1-postmarketos-grate':
        raise RuntimeError('Grate kernel mismatch')
    for link in prefix.rglob('*'):
        if link.is_symlink():
            resolved = link.resolve(strict=True)
            if not resolved.is_relative_to(prefix) or str(resolved.relative_to(prefix)) not in HASHES:
                raise RuntimeError(f'Untrusted runtime symlink: {link}')
    for relative, expected in HASHES.items():
        path = prefix / relative
        for parent in (path, *path.parents):
            st = parent.stat()
            if st.st_uid != 0 or st.st_mode & 0o022:
                raise RuntimeError(f'Untrusted runtime permissions: {parent}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Grate runtime hash mismatch: {relative}')

class Services:
    def command(self, service, operation):
        subprocess.run(['/sbin/rc-service', service, operation], check=True, timeout=20,
                       env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root'})
    def select(self, mode):
        temporary = OVERRIDE.with_suffix('.new')
        temporary.write_text(f'SL101_DESKTOP_RENDERER={mode}\n')
        temporary.chmod(0o644)
        temporary.replace(OVERRIDE)
    def ready(self, mode):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                pid = int(Path('/run/sl101-desktop.pid').read_text().strip())
                proc = Path(f'/proc/{pid}')
                env = (proc / 'environ').read_bytes().split(b'\0')
                alive = (proc / 'comm').read_text() == 'labwc\n'
                socket = Path('/run/sl101-desktop-user/wayland-0').is_socket()
                wanted = b'WLR_RENDERER=pixman' if mode == 'pixman' else b'WLR_RENDERER=gles2'
                gpu = mode != 'grate' or (b'MESA_LOADER_DRIVER_OVERRIDE=grate' in env
                       and b'WLR_RENDERER_ALLOW_SOFTWARE=0' in env
                       and str(PREFIX / 'lib/libgallium-25.0.7.so') in (proc / 'maps').read_text())
                if alive and socket and wanted in env and gpu:
                    time.sleep(2)
                    if proc.exists():
                        return True
            except (OSError, ValueError):
                pass
            time.sleep(.25)
        return False

def change(mode, services):
    """All service effects go through an injected backend for offline tests."""
    if mode not in ("pixman", "grate"):
        raise ValueError("invalid renderer")
    try:
        services.command('sl101-wayvnc', 'stop')
    except Exception:
        pass
    try:
        services.command('sl101-desktop', 'stop')
        services.select(mode)
        services.command('sl101-desktop', 'start')
        if not services.ready(mode):
            raise RuntimeError(f'{mode} startup health check failed')
    except Exception:
        if mode != 'grate':
            raise
        print('Grate startup failed; recovering Pixman', flush=True)
        try:
            services.command('sl101-desktop', 'stop')
        except Exception:
            pass
        services.select('pixman')
        services.command('sl101-desktop', 'start')
        if not services.ready('pixman'):
            raise RuntimeError('Pixman recovery failed')
    services.command('sl101-wayvnc', 'start')


def acquire_lock(path=LOCK):
    lock = path.open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('A browser/graphics qualification owns the device; close it before switching')
    return lock


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('pixman', 'grate'):
        raise RuntimeError('usage: sl101-renderer-switch pixman|grate')
    if os.geteuid() != 0:
        raise RuntimeError('requires root via the installed sudo rule')
    mode = sys.argv[1]
    # Prevent accidental installation/use on another machine.
    if Path('/etc/hostname').read_text().strip() != 'sl101-nura':
        raise RuntimeError('not the SL101 review device')
    if Path('/sys/block/mmcblk1/device/cid').read_text().strip() != '035344534c31323880ac79a543010300':
        raise RuntimeError('SL101 root SD identity mismatch')
    with acquire_lock() as lock:
        if mode == 'grate':
            validate_grate()
        # Return before stopping the caller's compositor. Keep the inherited lock.
        child = os.fork()
        if child:
            print(f'Requested {mode}; restarting labwc (boot defaults unchanged)', flush=True)
            os._exit(0)
        os.setsid()
        log = os.open('/var/log/sl101-renderer-switch.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        null = os.open('/dev/null', os.O_RDONLY)
        os.dup2(null, 0)
        os.dup2(log, 1)
        os.dup2(log, 2)
        print(f'{time.strftime("%Y-%m-%dT%H:%M:%S")} requested={mode}', flush=True)
        change(mode, Services())
        print('Switch finished', flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'sl101-renderer-switch: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
