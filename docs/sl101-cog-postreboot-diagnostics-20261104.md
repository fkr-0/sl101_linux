# SL101 Cog post-reboot diagnostic, 2026-11-04

## Scope and provenance

Read-only inspection plus two **bounded** live KMS GPU browser smoke tests
after the user reported that Cog may have frozen the tablet.
Canonical workspace: `sl101_linux`; device identity observed as
`sl101-nura`, kernel `7.0.1-postmarketos-grate`.
No Mesa/libdrm/kernel files, boot settings, persistent desktop defaults,
or Cog launchers were modified by this follow-up.

At initial contact, only labwc was active (no Cog/WebProcess), and uptime was
about 28 minutes. Device RTC reported boot at 2026-11-04 06:48:36 UTC.
The current boot recorded `EXT4-fs (mmcblk1p1): 1 orphan inode deleted`
and `recovery complete`, consistent with an unclean prior shutdown but **not**
proof that a GPU hang caused it. No current-boot dmesg entries matched the
target GR3D/host1x timeout/reset, OOM-kill or watchdog patterns. Prior-boot
persistent GPU trace was not recovered; a kernel freeze could leave none.

## Installed software and shader limitation

Current deployed private chroot driver:
`/opt/sl101-cog-wpe-debian/opt/grate-mesa25-clean/lib/arm-linux-gnueabihf/libgallium-25.0.7.so`
SHA256 `e5870bdd03ddcb6c4adf72435e264648083277dfb0a0706b9399aba2edbef0b5`.
This **matches** the verified crash-containment deployment in
`docs/sl101-fragcoord-crash-20261104.md`; its previous library was
`07d88eaf18a5d6df6bcdeab8235fa3fa46a69fc14f936b8042014777f28e6b7b`.
The separate host musl Grate overlay was not changed.
Existing rollback: `/var/lib/sl101-fragcoord-crash-20261104/rollback.sh`.

Patch `0042-grate-fragcoord-contract-and-safe-rejection.patch` fixes the
previous NIR `lower_fragcoord` invalid-options assertion, but explicitly
**rejects** fragment `TGSI_SEMANTIC_POSITION`. Therefore
`fragment POSITION (gl_FragCoord) input unsupported` and the resulting
dropped draw are expected with a shader using that builtin. This is not a
correct `gl_FragCoord` implementation; do not map POSITION to ordinary
vertex-varying export `input+1` or mark this GLES feature qualified.
The host regression `python3 -m unittest tests.test_sl101_grate_fragcoord -v`
passes, checking the *safe rejection* contract.

## Live KMS qualification after reboot

The existing `sl101-cog-drm-root` launcher and
`sl101-cog-kms-session` supervisor were inspected before execution.
It takes `/run/lock/sl101-nura-qualification.lock`, stops labwc,
launches Cog in its own process group, enforces `--timeout`,
and restores the desktop. The canonical project presence indicated no
other currently active graphics worker; ownership was announced on
`.wsbridge:graphics` before the tests.

1. `sudo -n /usr/local/bin/sl101-cog-drm-root --timeout 15 --gpu https://example.org/`
   - Cog and WebProcess observed live; page reported `Loaded successfully`.
   - Exit code **124** was the expected intentional deadline.
   - Desktop resumed; labwc observed, no remaining Cog/WebProcess.
   - No new matching GR3D/host1x faults observed.
2. `sudo -n /usr/local/bin/sl101-cog-drm-root --timeout 30 --gpu https://www.tagesschau.de/`
   - Page reported `Loaded successfully`; SSH remained responsive during
     the test. Memory pressure remained near zero; zram was essentially unused.
   - Exit code **124**, expected deadline; labwc was restored.
   - No remaining browser processes or matching kernel GPU faults.
   - The previously reported session D-Bus, PipeWire `client.conf`,
     OpenAL Soft and ALSA `card '0'` errors were reproduced. No new
     `gl_FragCoord` rejection appeared in this 30-second log window;
     this does not demonstrate rendering support for that builtin.

No pixel-oracle readback or camera capture was obtained in this round.
Neither page-load success nor clean timeout proves correct pixels,
no flicker, tear-free scanout, or long-run stability.
The prior controlled KMS pixel oracle remains documented in
`docs/sl101-kms-gpu-qualified-20261104.md`.

## Audio and D-Bus evidence (separate defect)

On the Alpine host `aplay -l` lists
`card 0: WM8903 [Asus EeePad Transformer WM8903]` and
`card 1: HDMI [NVIDIA Tegra20 HDMI]`; `/dev/snd` exists.
The private Debian root lacks `/opt/sl101-cog-wpe-debian/dev/snd`, and the
host `/run/user/1000/bus` socket was absent at inspection. Thus ALSA's
`cannot find card '0'` is consistent with missing device visibility inside
Cog's isolated environment, not proof that the kernel audio card is absent.
PipeWire's missing `client.conf` and session D-Bus propagation require their
own scoped diagnosis and should not be folded into a Grate shader fix.
Do not bind the entire host `/dev` into the sandbox as an unreviewed shortcut.

## Host regression and remaining gates

- `python3 -m unittest tests.test_sl101_grate_fragcoord -v`: PASS (1 test).
- `make test`: PASS (270 tests, 1 skipped). Suite output includes a
  pre-existing nonfatal patch-replay rejection; it was not treated as a replay
  success.
- `make check`: PASS.
- `git diff --check`: PASS.

Remaining:
- Find real Tegra20 fragment window-position support or a verified lowering;
  implement and test XYZW GLES semantics before removing safe rejection.
- For flicker/hang: controlled producer/scanout observation (and physical
  panel evidence where necessary) with a recoverable test window; correlate
  boot ID, GPU fences, KMS pageflips and temperature/load. Do not assume
  gl_FragCoord draw rejection caused the hard reset.
- Diagnose audio/DBus separately, preserving browser sandbox boundaries.

Recovery after leaving any Cog KMS session:
`sudo sh /var/lib/sl101-fragcoord-crash-20261104/rollback.sh`
restores the prior chroot driver if that particular deployment must be undone.
The KMS session supervisor also restores labwc automatically; the prior
`sl101-gpu-finish-20261104` rollback has broader scope and should not be
used as a generic first action.
