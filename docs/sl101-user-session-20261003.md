# Installed desktop and regular-user session

The SL101 desktop uses host account `user` (UID/GID 10000), including labwc,
NuraLoumi, WayVNC and PipeWire/WirePlumber. Root SSH remains available for
maintenance. Debian browser/Doom processes retain their separate UID 1000.

The installed panel is `/opt/nuraloumi/current/nuraloumi-panel --live`, started
by `/home/user/.config/labwc/autostart`. The initial installed release is
`qualified-20261003`, copied from the already working device binaries; this is
not a rebuild of the concurrently modified NuraLoumi checkout.

To install a subsequent qualified ARMv7 release, copy its binaries to a staging
directory on the tablet, then run as root:

```sh
/usr/local/sbin/sl101-panel-install /path/to/staging RELEASE
```

The repository source is `scripts/sl101-panel-install.sh`. It installs an
immutable release directory, checks its SHA256 manifest and switches `current`.
It retains the preceding target in `previous`. Activation requires restarting
the panel or desktop; installing alone does not interrupt the current session.
To roll back the binary selection, point `current` at the target returned by
`readlink /opt/nuraloumi/previous`, then restart the desktop.

## Session configuration

`scripts/sl101-user-session/` contains the deployed desktop/audio launchers,
OpenRC services and panel autostart. These are target-specific configuration
snapshots, not a general installation script. Their destinations are:

| File | Device destination |
| --- | --- |
| desktop.init | /etc/init.d/sl101-desktop |
| wayvnc.init | /etc/init.d/sl101-wayvnc |
| sl101-desktop | /usr/local/bin/sl101-desktop |
| sl101-audio-session | /usr/local/bin/sl101-audio-session |
| autostart | /home/user/.config/labwc/autostart |
| sl101-doom-root | /usr/local/bin/sl101-doom-root |
| sl101-doom-enter | /usr/local/libexec/sl101-doom-enter |

Prerequisites include account `user` in `seat`, `audio`, `video` and host group
`sl101-browser` (GID 1000), existing seatd/dbus services and the installed native
labwc, WayVNC, PipeWire and NuraLoumi binaries. The VNC configuration directory
is root:user 0750 and its file is root:user 0640; VNC listens on localhost.
The services are enabled in OpenRC's default runlevel.

The desktop owns private runtime directory `/run/sl101-desktop-user` (0700),
separate from login-managed `/run/user/10000`. This keeps desktop sockets
independent of login-session cleanup. Its service creates/chowns runtime and
log directories before dropping privileges. Applications started from the
panel inherit the desktop runtime and session bus. For commands from SSH:

```sh
export XDG_RUNTIME_DIR=/run/sl101-desktop-user
export WAYLAND_DISPLAY=wayland-0
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/sl101-desktop-bus
```

Firefox, Cog and Doom launchers delegate their mount setup through `sudo -n`
to root-owned `sl101-{firefox,cog-wpe,doom}-root` helpers; those helpers launch
the existing isolated Debian environment and drop application privileges.
Only these helpers are allowed in `/etc/sudoers.d/sl101-browser` for `user`.
Their host Wayland binding uses `/run/sl101-desktop-user/wayland-0`, with host
socket ownership 10000:1000. Root helper files must remain root owned.
VLC runs directly as the host user.

Audio uses the WM8903 pro-audio playback sink at 44.1 kHz. Startup waits for the
exact tablet card name, rather than accidentally matching its HDMI prefix,
and reapplies the profile while WirePlumber finishes initial state restoration.
The existing capture-disabled WirePlumber rule remains necessary. The browser
Pulse socket is 10000:1000, mode 0660. An old VLC process holding ALSA directly
was stopped during migration; applications should now use shared PipeWire audio.

German labwc layout, console `/etc/keymap/de.bmap.gz` and the enabled keyd
Caps-to-Control configuration are retained.

## Renderer and recovery

`/etc/sl101-desktop-renderer.conf` explicitly selects **pixman**. Native EGL/Grate
worked in a trial session, but EGL initialization and renderer strings alone do
not qualify correct texture/ALU/compositor pixels. See the deployment-readiness
and working-EGL notes. This installation does not promote the experimental
renderer. The launcher still supports the existing hash-checked Grate bundle.

The pre-migration backup is on the device at
`/var/lib/sl101-session-before-user-20261003.tar.gz`. Stop WayVNC and the desktop
before restoring it. It contains prior service/launcher/config files; it does
not undo added group memberships, installed release directories or sudoers.
Restoring the old browser launchers requires removing their new delegating
sudo rules too. Keep SSH recovery available during any session rollback.

Host CI runs the unit suite, Python syntax and shell syntax on pushes and PRs.
The archived hardware-evidence test skips when its external evidence bundle is
absent; CI does not claim GPU, browser pixels, audio audibility or hardware boot
qualification.

## Reboot evidence

An ordinary reboot completed after deployment, changing boot ID from
`ed58d6b0-680c-4d86-94d4-e055f2d2584c` to
`43f9f6eb-0058-4742-bede-3fc0dab30750`. The tablet returned through SSH on kernel
`7.0.1-postmarketos-grate`, with both kexec-loaded flags zero. Labwc, one installed
panel, WayVNC and all three audio processes started as `user`; WayVNC listened
on 127.0.0.1:5900 and PipeWire selected the WM8903 playback sink at 44.1 kHz.
This verifies an ordinary reboot, not a physical power-off/on cycle or human
confirmation of display/input/audio.

The post-reboot Firefox launcher started its application under Debian UID 1000.
Native VLC's version command also succeeds under the host user. Doom's launcher
now selects the already installed shareware `doom1.wad`, but Chocolate Doom
still segfaults during sound precaching; a `-nosound` attempt also segfaulted.
The launcher privilege transition is installed, but Doom runtime qualification
is unresolved. Its preceding enter helper is preserved on the device at
`/var/lib/sl101-doom-enter-before-user-review`.
