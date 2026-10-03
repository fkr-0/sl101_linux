# SL101 remote control

Deployed 2026-10-02 to the online Nura tablet at `192.168.23.106`.
The eMMC/SD CIDs match the persistent-U-Boot reference tablet; the IP changed
from the original `.166`. The other address was unreachable during deployment.

WayVNC 0.10.0 shares the running root labwc `wayland-0` session on
`/run/user/0`, including pointer and keyboard input. The compositor remains on
pixman. No GPU/kernel/boot files were changed. Its OpenRC service
`sl101-wayvnc` is enabled in the default runlevel and supervised with a ten-second
respawn delay. It requires labwc to be running; enabling this service does not
itself start labwc. Capture is capped at 10 FPS and viewer-driven resizing is
disabled to preserve the physical 1280x800 display.

The tablet listens only on `127.0.0.1:5900`. SSH local forwarding was initially
disabled; `/etc/ssh/sshd_config.d/00-sl101-vnc.conf` now allows local forwarding
only to that destination. The configuration was checked and sshd reloaded.
A fresh SSH connection is required because existing connections retain the old
forwarding policy. VNC relies on the SSH tunnel for authentication/encryption.

## Connect

```sh
scripts/sl101-vnc.sh
```

This uses a dedicated SSH control connection, verifies the tablet host key, and
opens the installed `gvncviewer`. It may prompt for the tablet SSH password.
The tunnel remains available after closing the viewer. For this deployment an
active tunnel/viewer already exists at `127.0.0.1:5901`.

For a manual tunnel (choose another local port if 5901 is already occupied):

```sh
ssh -o ControlMaster=no -o ControlPath=none -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -N \
  -L 127.0.0.1:5902:127.0.0.1:5900 root@192.168.23.106
gvncviewer 127.0.0.1:2
```

The verified ED25519 fingerprint is
`SHA256:XKuYz3NnSwlnN9OJxxmiqo0Es2wUuBqlSGoMhP4nWiM`.
It matches the provisioned public host key under
`tmp/sl101-nura/deploy/private/access/etc/ssh/ssh_host_ed25519_key.pub`.
The stale `.106` known_hosts entry was replaced after that comparison; the
pre-change file is backed up as `~/.ssh/known_hosts.before-sl101-vnc-20261002`.

## Validation and operation

The RFB 3.8 handshake and full 1280x800 framebuffer transfer succeeded through
SSH. A temporary test foot window appeared in the captured framebuffer.
A VNC pointer click focused that test window and a key event delivered byte
`0x76` (`v`) to its one-byte reader; the test window then exited. This verifies
screen, pointer focus, and keyboard input through the deployed server.
The existing desktop terminal was left running. Smoke artifacts are in
`tmp/sl101-remote-control/`. Reboot persistence is configured but has not been
cold-boot tested; no reboot was needed for this deployment.

```sh
ssh root@192.168.23.106 'rc-service sl101-wayvnc status'
ssh root@192.168.23.106 'tail /var/log/sl101-wayvnc.log'
```

To disable remote control, stop `sl101-wayvnc` and remove it from the default
runlevel. Removing its SSH config snippet and reloading sshd restores the
original forwarding policy. Deployment templates live alongside this document
in `docs/sl101-remote-control/`.

### Terminal characters visible only after Return

After deployment the existing foot terminal (`/dev/pts/4`) had `-echo`
with canonical input enabled. VNC keystrokes arrived but were not echoed.
Restored that terminal with `stty sane -F /dev/pts/4` and re-enabled `iutf8`.
No VNC or compositor restart was needed. The equivalent command inside an
affected terminal is `stty sane; stty iutf8` (type it even if input is invisible).
