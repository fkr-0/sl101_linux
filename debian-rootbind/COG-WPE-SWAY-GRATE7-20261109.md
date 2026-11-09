# Debian SL101 .100: Grate Prod70 → native Sway → Cog/WPE → NuraLoumi

Live qualification date: **2026-11-09**. Device: ASUS SL101
`sltwrpbootdebian`, Debian 13.7 armhf/glibc; root
`/dev/mmcblk1p1`; **normal ASUS boot without APX**;
kernel `7.0.1-postmarketos-grate`. This is **real on-device
hardware and screenshot evidence**, not a host-only EGL smoke.

## System preflight

- `seatd` and `keyd` active; LVDS-1 internally connected.
- No compositor or Wayland socket existed before the experiment.
- The existing login shell retained older user groups, but
  `id user` in the account database included `video` and
  `render`. Starting the isolated test with fresh
  `sudo -n -u user` obtained the current group privileges without
  reboot or group changes.
- Private Mesa glibc **Prod70**, Gallium ELF SHA256
  `537ed2aa652799bfea857990e0e3f5e2f5f08ffc2bfef6e7a216314cae40c9b7`,
  was selected using
  `/opt/sl101-debian-rootbind/bin/sl101-grate prod70 exec`.
  EGL/GBM as user reports
  `OpenGL ES profile vendor: Grate`,
  `OpenGL ES profile renderer: Tegra`,
  GLES 2.0 Mesa 25.0.7.

## Native Sway test

`sway 1.10.1` was launched as the non-root `user` with
`XDG_RUNTIME_DIR=/run/user/1000`, `LIBSEAT_BACKEND=seatd`,
`WLR_BACKENDS=drm`, `WLR_RENDERER=gles2`,
`WLR_RENDERER_ALLOW_SOFTWARE=0`,
`WLR_DRM_NO_ATOMIC=1`, German XKB layout and the private
Prod70 launcher. An **isolated** minimal configuration under
`/tmp/sl101-sway-cog-prod70-test-20261109.conf` was used.
Neither `/etc/sway/config` nor the user's nonexistent
`~/.config/sway/config` was changed.

Hardware/IPC evidence:

- Real output `LVDS-1` at **1280×800 @ 58.632 Hz**, XR24.
- DRM/GBM successfully allocated scanout buffers; GLES2
  repeatedly created GL framebuffers and committed output.
- `/run/user/1000/wayland-1` became a Wayland socket.
- `swaymsg -t get_tree` reported an actually visible Cog
  window at x0/y0/1280×800.
- wlroots emitted `Failed to parse EDID`, but continued using
  the valid panel mode; output test and commit succeeded.
- No GR3D timeout/DRM GPU fault matched a read-only targeted
  `dmesg` scan during the runs.

The first Sway run was supervised with a 180-second timeout.
A subsequent external-HTTPS test used a separate bounded
900-second Sway launch; Cog had its own bounded lifetime. No
systemd autostart, persistent session or default renderer was
modified.

## Cog / WPE WebKit browser evidence

Installed Debian runtime: `cog 0.18.4`, WPE WebKit `2.48.3`,
`libcogplatform-wl.so`, native Wayland platform.

1. A local HTML fixture at
   `file:///tmp/sl101-cog-prod70-wpe-test-20261109.html`
   exercised CSS colors, JavaScript timers and moving Canvas2D.
   Cog log: `Loaded successfully.`; WPEWebProcess and
   WPENetworkProcess were alive. `swaymsg` identified
   `app_id=com.igalia.Cog`, PID 1228, visible 1280×800.
   Verified `grim` screenshot SHA256
   `a7114917305b4412ae6acdebb92da33404dd440b0f60e1d95d5a1c646eb70c2f`;
   RGB 1280×800 and 409 distinct colors.
2. The live **HTTPS** URL `https://example.com/` was
   successfully fetched and rendered, not a simulated network
   image. Cog log: `Loaded successfully.`; separate sandboxed
   WPEWebProcess and WPENetworkProcess were present; Sway again
   reported visible `com.igalia.Cog` at 1280×800 (PID 1454).
   Screenshot SHA256
   `b033aeb1acdfb8e62d0a63ec809b94d75f205313604f764c5d3116d21c55cd37`.
   The screenshot visibly contains the correct multilingual
   example.com page and clickable `Learn more` link; a
   non-Latin glyph range displays replacement squares (font coverage
   limitation, **not** evidence of Grate corruption).
3. At the subsequent on-device status check Cog had remained
   running for **over ten minutes**, with `--webprocess-failure=exit`
   enabled and without recorded WebProcess failure.

These tests establish real GPU compositor and visible native
WPE browser content, but do **not** yet qualify scrolling,
touch, physical keyboard shortcuts, video/audio playback, long-term
memory behavior, all JavaScript graphics features, or browser
process recovery after repeated faults.

Host-private screenshot/log evidence:
`work/sl101-sway-cog-debian-20261109/`.
Equivalent on-device volatile screenshots and logs use the
`/tmp/sl101-cog-prod70-*` and
`/tmp/sl101-sway-prod70-*` prefixes.
Do not treat these transient log paths as permanent installed
packages.

## NuraLoumi Debian-glibc package now staged and live-smoked

GitHub Actions run
`https://github.com/fkr-0/nuraloumi/actions/runs/42611227679`
**PASS** at commit
`0b06635304dfe99ec4e7c56a910e00d63848234c`.
The artifact `nuraloumi-debian13-armv7-gnueabihf-4`
is an **armv7-unknown-linux-gnueabihf** package
(version `0.0.4-dev.1`), not the incompatible Alpine/musl
variant. TAR SHA256
`a6667e0187279b8513240d1ae8daf3270332de0387b2cb1eb5e891ffd46bcd43`.
The full per-file SHA256 manifest (38 files), all 22 executable
binary targets, ELF32/ARM hard-float VFPv3-D16 and glibc
interpreter checks passed on the host.

On `.100`, **only the SD filesystem** was modified to
stage the *new*, hash-verified directory:

    /opt/sl101-debian-rootbind/nuraloumi-candidates/0.0.4-dev.1-0b06635-glibc/

The temporary transferred TAR was removed after validation.
The deployment did **not** replace `/usr/bin`,
`/opt/nuraloumi/current`, compositor startup, login, or any
eMMC/boot slot. At rest the candidate remains immutable and
root-owned.

On-device runtime smoke results:

- All **22** binary files present;
- `ldd` for panel, menu and ctl resolved glibc and the expected
  system Cairo/XKB libraries, no missing DSO;
- `nuraloumi-panel --help`,
  `nuraloumi-menu --help`,
  `nuraloumi-ctl --help` succeeded without SIGILL;
- headless launcher menu produced **8,321 bytes of JSON**;
- an explicitly bounded 50-second, unprivileged
  `nuraloumi-panel --live` created a real Cairo/wl_shm
  layer-shell panel over Cog. Log:
  `nuraloumi-panel-provider-refresh: initial live snapshot ready`.
  The overlaid screenshot SHA256:
  `1320f5029e0b4af8e949f5f99de0485c566eacd536a935a2d3bad9bf8bfe7800`.
  No `--enable-power-actions`,
  `--enable-renderer-switch` or suspend capability was enabled.

**Visible follow-ups from the actual panel screenshot:**
NuraLoumi currently displays `Unknown` for its renderer and
`Network: Disconnected` even while Cog successfully displays an
HTTPS page. This does **not** mean the GPU or network are actually
unavailable: NuraLoumi renderer provider reads
`/run/sl101-desktop.pid` from the managed Nura desktop service,
which **does not exist** for this ad hoc Debian Sway trial.
Moreover its Gallium-path whitelist does not yet include
`/opt/sl101-debian-rootbind/grate-prod70-private/`, so just
writing a PID file would not fix full Grate classification.
The renderer/network status provider paths need a separate
Debian-aware change and tests; do not spoof a PID file
or mutate a running Sway environment to make the indicator green.

## Rollback, next qualifications

- The browser and compositor were launched with **bounded
  supervisors** and no system service changes; they end
  automatically. Do not assume they will persist across chat turns
  or reboot.
- `keyd`, `seatd`, saved ASUS LNX and the original SSH are
  unaffected. No reboot or flash occurred during this lane.
- Keep the staged Nura package as a candidate; promote only after
  representative touch/keyboard checks, a sustained GUI test,
  renderer/provider fixes and a separate rollback review.
- A future persistent Debian Sway/Cog/NuraLoumi session should use
  a real logind/seat lifecycle and an installed/owned configuration,
  rather than copying transient `/tmp` launch scripts blindly.
