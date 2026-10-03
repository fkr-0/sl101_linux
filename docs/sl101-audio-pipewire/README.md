# SL101 PipeWire audio

This bundle captures the live-qualified SL101 audio configuration from
2026-10-03 on Nura with kernel 7.0.1-postmarketos-grate.

## Contract

The tablet's WM8903 codec is used through PipeWire/WirePlumber in the
`pro-audio` profile. Playback is pinned to 44.1 kHz and the WM8903 sink is the
default output at 35% volume.

The current kernel/driver capture PCM rejects open/start. WirePlumber used to
retry that source repeatedly and could destabilize the whole ALSA card, so this
configuration deliberately disables only
`alsa_input.platform-sound.pro-input-0`. The monitor source remains available,
but this is **not a microphone-capable PipeWire configuration**.

A second Pulse-compatible socket is exposed at
`/run/sl101-audio/pulse-browser`. It uses Pulse anonymous authentication
because Firefox runs as uid 1000 in an isolated Debian armhf rootfs, but the
socket itself is restricted to mode 0660 and uid/gid access. The Firefox
launcher bind-mounts that socket as
`/run/user/1000/pulse/native` inside the browser rootfs.

Bluetooth audio requires both BlueZ and PipeWire's BlueZ SPA plugin. The
installer therefore installs `pipewire-spa-bluez` and enables the OpenRC
`bluetooth` service. Missing logind/UPower integration on this OpenRC image is
non-fatal.

## Live evidence

After the fix:

- PipeWire 1.6.9, WirePlumber and pipewire-pulse are running.
- Pulse reports `float32le 2ch 44100Hz`.
- Default sink is `alsa_output.platform-sound.pro-output-0`.
- WM8903 playback itself is `s16le 2ch 44100Hz`.
- A Pulse test client completed with rc=0 through the browser socket.
- Firefox ESR 140.16.0, uid 1000, created an uncorked
  `float32le 2ch 44100Hz` stream with the normal cubeb sandbox.
- Chocolate Doom independently created an active stereo 44.1 kHz stream linked
  to both WM8903 playback channels.
- No new 48 kHz rate-mismatch or WM8903 capture-recovery loop appeared after
  the restart.
- BlueZ is running and the SL101 controller exposes Audio Source and Audio Sink
  UUIDs. Pairability/discoverability are left to the UI or an explicit
  `bluetoothctl` operation.

Live file hashes at qualification time:

```text
dddd0031000cc7aa3c9a5be67460050c454e0f70526374cfb51a3b75426c1d69  /etc/pipewire/pipewire.conf.d/10-sl101-clock.conf
d37515d99d71734550f8677659059109fc5635ccce8f8bbec27136ef603563cf  /etc/pipewire/pipewire-pulse.conf.d/10-sl101-browser.conf
286992418e00b9dde610f84d3576f01602a80eb2912b531095ea16d8d09bdfa1  /etc/wireplumber/wireplumber.conf.d/51-sl101-wm8903.conf
23410dc804f34fc423711e6d098eb7a30c843b5065c3f62b95950c8bf08c1320  /usr/local/bin/sl101-audio-session
```

## Install / verify

On the SL101:

```sh
sh docs/sl101-audio-pipewire/install.sh
/usr/local/bin/sl101-audio-session status
pactl info
pactl list short sinks
wpctl status
```

The installer preserves replaced files under a timestamped
`/var/backups/sl101-audio-*` directory before applying the bundle.

The desktop wrapper should invoke `sl101-audio-session start` after creating
its private D-Bus session and before exec'ing labwc. The tracked
`docs/sl101-grate-default/sl101-desktop` carries that hook.
