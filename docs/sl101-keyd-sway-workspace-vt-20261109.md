# SL101 Nura: Super workspaces, LeftCtrl+RightAlt VTs, workstation AltGr (2026-11-09)

## Scope and target

- **Applied on**: `sl101-nura`, 192.168.23.106 (native Alpine/musl).
- Kernel: `7.0.1-postmarketos-grate`; SD CID `/sys/block/mmcblk1/device/cid` = `035344534c31323880ac79a543010300`; `keyd v2.6.0`; Sway via `/usr/local/bin/sl101-sway`.
- Current Sway process observed: PID 1644, runtime `/run/sl101-desktop-user`.
- **Not applied** to separate Debian/rootbind device .100. Its adapted keyd/Sway mirror and hash manifests are a separate parity workstream.
- No compositor restart, kernel changes, flash, reboot, or VT switch was performed.

## Input contract

| Physical chord | Meaning |
| --- | --- |
| `Super+1..9` | Normal Sway `workspace number 1..9` |
| `Super+Shift+1..9` | Move selected container to workspace 1..9 |
| **`RightAlt (AltGr)+LeftCtrl+1..9`** | Emit `Ctrl+Alt+F1..F9` for VT recovery |
| `RightAlt` + any of the 15 mapped keys below | Workstation AltGr remappings |

The slider's home/menu key is `leftmeta`, the AltGr key is physical
`rightalt`, and the other control key is `leftcontrol`. Previous
`keyd [meta]` mappings consumed Super+1..7, preventing Sway from seeing
workspace switches. The new `[main]` keeps `capslock = layer(control)`,
maps `leftcontrol = layer(sl101_lctrl)` and `rightalt = layer(altgr)`.
The `[sl101_lctrl:C]` layer retains ordinary Ctrl semantics.
`[sl101_lctrl+altgr]` maps 1..9 to `C-A-f1..f9`.

The exact workstation-provided `[altgr:G]` mapping is:

```ini
w = G-102nd
e = 102nd
r = S-102nd
j = kprightparen
d = G-8
s = G-7
k = G-9
l = G-0
f = kpleftparen
, = 102nd
. = S-102nd
m = G-102nd
/ = S-7
right = end
left = home
```

Source mirror and deployed paths:

| Source (repository) | Live device |
| --- | --- |
| `docs/sl101-device-config/etc/keyd/sl101.conf` | `/etc/keyd/sl101.conf` |
| `docs/sl101-device-config/home/user/.config/sway/config` | `/home/user/.config/sway/config` |
| `scripts/sl101-keyd-sway-deploy.sh` | `/var/lib/sl101-keyd-sway-20261109/deploy.sh` |

The **live** Sway file also has an unrelated existing `output LVDS-1 bg
#00b050 solid_color` line that was preserved during merge. The tracked
mirror contains the exact requested binding changes without overwriting
that independent live visual test configuration.

## Deployment and verification evidence

Preflight: exact host and kernel; existing Sway PID/socket; standard
`/run/lock/sl101-nura-qualification.lock` held for the apply; source/live
SHA-256 checks, `keyd check`, and `sway -C` with a headless Pixman backend.
Only `keyd reload` and `swaymsg reload` were used for activation. No
second DRM compositor was started.

| Artifact | Before | After |
| --- | --- | --- |
| keyd installed | `08ee8b348ccc13cd050dd714bbb23fe08592ee8bb1d1613beb6d67570d3a3d21` | `b91be7d5e318b3d2d0be8b9052689ac87d41b50ebe65c3fdb26d8832c99daf84` |
| Sway installed | `0e6369dbffed4caac7a9f2712cebd8e0bf056aaba1a41c7f0f5db19fc1c8c058` | `2308762641127b6bf472d46fa71e1cc36cc19a637ef88d8b8b46c919cec5cbb0` |

Device reports `DEPLOY_OK`; both postflight file hashes and the live
Sway IPC `get_config` hash matched the expected after value. `keyd`
remained running; Sway PID remained unchanged at 1644. Sway `get_inputs`
listed keyd virtual keyboard/pointer, AT Raw Set 2 keyboard, and Atmel
touchscreen. `get_workspaces` reported workspace 1 focused. A repeat
`--apply` returned `ALREADY_DEPLOYED (changed=0)`; `--check` returned
`POSTFLIGHT_OK`. Four source-level regression tests passed via
`python3 -m unittest discover -s tests -p 'test_sl101_keyd_sway_workspace_vt_20261109.py'`.
Full repository `make test` ran **1,942 tests: OK (skipped=1)**, and
`make check` completed with exit 0. A wrapper around the first `make test`
invocation mistakenly assigned zsh's read-only `status` variable *after*
the suite had completed; this caused the wrapper to return nonzero, not
the actual unittest suite (whose log ends in `OK (skipped=1)`).

## Rollback and physical acceptance

Original full contents and modes are preserved under the root-owned
`/var/lib/sl101-keyd-sway-20261109/`:

- `keyd.before` (old SHA above);
- `sway.before` (old SHA above);
- `deploy.sh` (guarded deployment/rollback script, retained across reboot).

Safe rollback while a Sway session is running and no later drift has
occurred:

```sh
ssh user@192.168.23.106 'sudo -n sh /var/lib/sl101-keyd-sway-20261109/deploy.sh --rollback'
```

The script refuses rollback over unknown new edits to either installed
file. If Sway is not running, the guarded script cannot connect to
Sway IPC. An operator can instead restore `keyd.before` and
`sway.before` as root, reload keyd, and reload Sway after it starts.

**Still requires physical operator confirmation:** press Super+2 then
Super+1; test AltGr+W/E/R and arrows; then test
RightAlt+LeftCtrl+2 followed by RightAlt+LeftCtrl+1 to round-trip
a text VT. Remote syntax/IPC checks cannot prove keyboard-level event
delivery or that the desktop survives a real VT transition. This test
has deliberately not been synthesized over remote SSH.
