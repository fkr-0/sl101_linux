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
    if len(sys.argv) != 3 or sys.argv[1] not in ('open', 'software', 'gpu'):
        raise ValueError('Usage: sl101-cog-control open|software|gpu URL')
    action, url = sys.argv[1], normalize_url(sys.argv[2])
    if os.geteuid() != 0:
        os.execvp('sudo', ['sudo', '-n', '/usr/local/sbin/sl101-cog-control', action, url])
    if Path('/etc/hostname').read_text().strip() != 'sl101-nura' or os.uname().release != '7.0.1-postmarketos-grate':
        raise ValueError('Tablet identity mismatch')
    if Path('/sys/block/mmcblk1/device/cid').read_text().strip() != '035344534c31323880ac79a543010300':
        raise ValueError('Tablet SD identity mismatch')
    browser = current_browser()
    if action == 'open' and browser:
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
        with open('/var/log/sl101-cog-session.log', 'ab') as log:
            child = subprocess.Popen(['/usr/local/sbin/sl101-cog-control', action, url],
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
