#!/usr/sbin/python3
"""Fixed browser actions; no shell evaluation of URLs or process environment."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path('/opt/sl101-cog-wpe-debian')
EXPECTED_HOST = 'sl101-nura'
EXPECTED_SD_CID = '035344534c31323880ac79a543010300'
# The privileged helper starts itself again; use its own path so a copy or a renamed
# install keeps working. The kernel release is deliberately NOT checked anywhere.
SELF = os.path.realpath(__file__)
RENDER_STATUS = Path('/run/sl101-render-status')   # written by sl101-desktop at start
SESSION_LOG = Path('/var/log/sl101-cog-session.log')


def check_hardware():
    """Hardware identity only (two identical tablets exist); say what differs."""
    host = Path('/etc/hostname').read_text().strip()
    if host != EXPECTED_HOST:
        raise ValueError(f'this is not the expected tablet: hostname is {host!r}, expected {EXPECTED_HOST!r}')
    cid = Path('/sys/block/mmcblk1/device/cid').read_text().strip()
    if cid != EXPECTED_SD_CID:
        raise ValueError(f'unexpected SD card: cid {cid}, expected {EXPECTED_SD_CID}')


def read_kv(path):
    data = {}
    try:
        for line in Path(path).read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                data[key.strip()] = value.strip()
    except OSError:
        pass
    return data


def compositor_env():
    """Environment of the RUNNING compositor: the truth, not the configuration."""
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / 'comm').read_text().strip()
            if comm in ('sl101-sway', 'labwc'):
                raw = (proc / 'environ').read_bytes().split(b'\0')
                env = dict(item.decode(errors='replace').split('=', 1) for item in raw if b'=' in item)
                return comm, env
        except (OSError, ValueError):
            continue
    return None, {}


def running_mode(browser):
    """software/gpu of a running Cog, from its own environment."""
    try:
        raw = (browser / 'environ').read_bytes().split(b'\0')
    except OSError:
        return None
    return 'software' if b'WEBKIT_SKIA_ENABLE_CPU_RENDERING=1' in raw else 'gpu'


def render_report(mode):
    status = read_kv(RENDER_STATUS)
    comm, env = compositor_env()
    live = env.get('WLR_RENDERER')
    lines = ['sl101 rendering now:']
    if comm is None:
        desktop = 'no compositor process found, cannot tell how the desktop renders'
    else:
        names = {'gles2': 'GLES2/EGL via Grate (GPU)', 'pixman': 'PIXMAN (software, CPU)'}
        actual = names.get(live, f'WLR_RENDERER={live}')
        desktop = f"{status.get('compositor', comm)} on {status.get('backend', 'DRM/KMS')}, compositor renderer: {actual}"
        if status.get('requested') == 'grate' and live == 'pixman':
            desktop += f"  <-- grate was requested but is NOT used: {status.get('reason', 'reason unknown')}"
        elif not status:
            desktop += '  (no /run/sl101-render-status: requested renderer and reason unknown)'
    lines.append('  desktop : ' + desktop)
    if mode == 'gpu':
        browser = 'Cog GPU mode: WebKit renders through EGL -> Mesa/Grate in the Debian chroot'
    elif mode == 'software':
        browser = 'Cog software mode: WebKit CPU rendering (Skia), buffers via shared memory, no EGL, GPU not used for page content'
    else:
        browser = f'unknown browser mode {mode!r}'
    lines.append('  browser : ' + browser)
    lines.append('  kernel  : ' + os.uname().release + ' (informational, not checked)')
    return '\n'.join(lines)


def announce(mode):
    report = render_report(mode)
    print(report)
    try:
        with open(SESSION_LOG, 'ab') as log:
            log.write((time.strftime('%Y-%m-%d %H:%M:%S ') + report.replace('\n', '\n  ') + '\n').encode())
    except OSError:
        pass


def normalize_url(value):
    value = value.strip()
    if not value or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Enter a URL without spaces or control characters')
    if '://' not in value:
        value = 'https://' + value
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only HTTP/HTTPS URLs without embedded credentials are supported')
    return value


def browser_bus(environ):
    values = dict(item.split(b'=', 1) for item in environ.split(b'\0') if b'=' in item)
    address = values.get(b'DBUS_SESSION_BUS_ADDRESS', b'').decode()
    if not address.startswith(('unix:path=', 'unix:abstract=')) or '\n' in address:
        raise ValueError('Cog session bus is unavailable')
    return address


def current_browser():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / 'cmdline').read_bytes().split(b'\0')
            if cmd[0] == b'/usr/bin/cog' and proc.stat().st_uid == 1000:
                if (proc / 'root').stat().st_ino == ROOT.stat().st_ino:
                    return proc
        except (OSError, IndexError):
            continue
    return None


def main():
    if len(sys.argv) == 2 and sys.argv[1] == 'status':
        browser = current_browser()
        try:
            configured = Path('/etc/sl101-cog-mode').read_text().strip()
        except OSError:
            configured = 'unknown'
        mode = running_mode(browser) if browser else configured
        print(render_report(mode))
        print('  cog     : ' + ('running' if browser else 'not running, next start uses mode ' + mode))
        return
    if len(sys.argv) != 3 or sys.argv[1] not in ('open', 'software', 'gpu'):
        raise ValueError('Usage: sl101-cog-control open|software|gpu URL   or   sl101-cog-control status')
    action, url = sys.argv[1], normalize_url(sys.argv[2])
    if os.geteuid() != 0:
        os.execvp('sudo', ['sudo', '-n', SELF, action, url])
    check_hardware()
    browser = current_browser()
    if action == 'open' and browser:
        announce(running_mode(browser))
        bus = browser_bus((browser / 'environ').read_bytes())
        subprocess.run(['chroot', str(ROOT), '/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--clear-groups',
                        '/usr/bin/env', 'DBUS_SESSION_BUS_ADDRESS=' + bus,
                        '/usr/bin/cogctl', 'open', url], check=True, timeout=15)
        return
    if browser:
        raise ValueError('Close the current Cog session before changing renderer')
    if action == 'open':
        action = Path('/etc/sl101-cog-mode').read_text().strip()
        if action not in ('software', 'gpu'):
            raise ValueError('Invalid installed browser mode')
        announce(action)
        with open('/var/log/sl101-cog-session.log', 'ab') as log:
            child = subprocess.Popen([SELF, action, url],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     start_new_session=True)
        for _ in range(30):
            if child.poll() is not None:
                raise ValueError('Browser startup failed; see /var/log/sl101-cog-session.log')
            if current_browser():
                return
            time.sleep(0.25)
        raise ValueError('Browser is still starting; see /var/log/sl101-cog-session.log')
    with open('/run/lock/sl101-nura-qualification.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        subprocess.run(['/usr/local/bin/sl101-cog-wpe-root', '--' + action, url], check=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('Cog: ' + str(error), file=sys.stderr)
        sys.exit(1)
