# Debian SL101: keyd, AltGr, Sway workspaces and VT recovery

**Status: deployed to `sltwrpbootdebian` (`192.168.23.100`) on 2026-11-09.**

## Requested keybindings

| Physical chord | Behaviour |
| --- | --- |
| `Super+1..9` | Sway workspace 1..9 |
| `Super+Shift+1..9` | Move active Sway container to workspace 1..9 |
| `RightAlt (AltGr)+LeftCtrl+1..9` | Emit Ctrl+Alt+F1..F9; text VT native handling / Sway chvt helper |
| `RightAlt+W/E/R/J/D/S/K/L/F/,/./M///arrows` | Workstation's 15-key AltGr layer, as requested |

The active Debian `keyd` configuration no longer has the old `[meta]` interception of Super+1..7. Physical RightAlt activates `[altgr:G]`; the separate `[sl101_lctrl+altgr]` layer generates VT F-keys. `capslock = layer(control)` is preserved.

## Target identity and actual changes

| Check | Verified value |
| --- | --- |
| Host | `sltwrpbootdebian`, Debian 13.7, armhf |
| Kernel | `7.0.1-postmarketos-grate` |
| Root | `/dev/mmcblk1p1` |
| SD CID | `03534453553332478030be3f6400b900` |
| eMMC CID | `7001004d4d43333247447e682c336e00` |
| Boot ID | `adcb71bc-c2ed-48a0-a560-cb408d2edc6d` |
| Keyd | Debian `keyd 2.5.0-4`; `/usr/bin/keyd.rvaiya` |
| Backup | `/var/lib/sl101-debian-input-20261109/` (root only) |

**Installed/changed files:**

- `/etc/keyd/sl101.conf` SHA256 `b91be7d5e318b3d2d0be8b9052689ac87d41b50ebe65c3fdb26d8832c99daf84`, root:root 0644.
- `/home/user/.config/sway/config` SHA256 `378d51dd859f11d21c758f0da92c10fa5f4b9827b1c4148b47d56452582b4422`, user:user 0644. This is the Debian rootbind variant with existing foot/tmux/Cog launchers, not the Alpine-specific template.
- `/usr/local/bin/sl101-chvt` SHA256 `d210218aee4d5672d80e20c0eca55f0004ce87200637627d779e43f216fee711`, root:root 0755; permits **only** VT numbers 1..9.
- `/var/lib/sl101-debian-input-20261109/deploy.sh`, root:root 0700, hash-gated deployment and rollback script. Root-owned backup `keyd.before` retains the original SHA256 `08ee8b348ccc13cd050dd714bbb23fe08592ee8bb1d1613beb6d67570d3a3d21`; recorded Sway and helper destinations were previously absent.

The Debian packages `kbd 2.7.1-2`, `console-setup-linux 1.242~deb13u1` and `console-setup 1.242~deb13u1` were installed via APT so that `/usr/bin/chvt` exists. No other system or graphical packages were upgraded. The package installer enabled its normal console/keyboard setup units. These packages are not removed by config rollback.

## Proof and limitations

- Strict SSH to `user@192.168.23.100` succeeded after initial authentication failures, without copying another public key.
- All candidate source and installed SHA256 hashes matched the deployment manifest.
- The guarded script passed `PREFLIGHT_OK` (hostname, kernel, architecture, root device, SD/eMMC CIDs, live keyd baseline, absent Sway/helper destinations, Debian chvt, candidate hashes, headless/Pixman `sway -C`).
- Deployment returned `DEPLOY_OK`, and rerunning `--check` and `--apply` returned `ALREADY_DEPLOYED changed=0`.
- `keyd.service` was restarted successfully; new PID 1151; at 20:11:16 the journal logged reading the new `/etc/keyd/sl101.conf` and matching the AT Raw Set 2 keyboard. `keyd` and `seatd` remain active; keyd virtual keyboard and touchscreen remain enumerated.
- `sway -C` succeeded on the installed Sway configuration. The installed VT helper safely rejects VT0 with exit code 64. No valid VT was switched remotely.
- After installation a new Sway session started naturally: process **PID 1446**, `sway --config /home/user/.config/sway/config`, environment `WLR_BACKENDS=drm,libinput`, `LIBSEAT_BACKEND=seatd`, `WLR_RENDERER=gles2`. The live Sway IPC `get_config` SHA256 exactly matched the installed config (`378d51dd...`) and contained **18 workspace bindings** (9 switch + 9 move) and **9 VT bindings**. IPC `get_inputs` enumerated keyd virtual keyboard/pointer, AT Raw Set 2 keyboard and Atmel touchscreen; seat0 reported six devices and capabilities 7. Thus the earlier DRM-only empty-seat symptom is **not present in this session**. No Sway IPC reload was necessary, because the newly started Sway loaded the deployed file.
- Actual physical keyboard chords, real VT switching, and onscreen visual behaviour are **not yet qualified**. No reboot, kernel change, flash or forced graphics restart was performed.
- The independent Nura device `192.168.23.106` was not changed.

## Rollback

When Sway is **not running**, this guarded command restores the original keyd config and removes the newly created Sway config and VT helper:

```sh
ssh user@192.168.23.100 'sudo -n sh /var/lib/sl101-debian-input-20261109/deploy.sh --rollback'
```

The rollback refuses changed hashes and an active Sway process. It leaves the Debian `kbd` and console-setup packages installed; removing those is a separate APT change.

## Repository sources and regression tests

- `docs/sl101-debian-device-config/etc/keyd/sl101.conf`
- `debian-rootbind/config/sway/config`
- `docs/sl101-debian-device-config/home/user/.config/sway/config` (alternate non-rootbind template)
- `docs/sl101-debian-device-config/usr/local/bin/sl101-chvt`
- `docs/sl101-debian-device-config/files-manifest.json` and `source-parity.json`
- `scripts/sl101-debian-keyd-sway-deploy.sh`
- `tests/test_sl101_debian_keyd_sway_workspace_vt_20261109.py`

The full suite before the final helper extension ran 1,947 tests (1 skipped; all others passed). After the helper extension and **concurrent Nura workspace-switcher changes in the shared checkout**, `make test` ran 1,952 tests and reported **9 failures**, all in `test_sl101_keyd_sway_workspace_vt_20261109.test_sway_workspace_and_vt_bindings`: that separate Nura test still assumes direct `$mod+1..9` bindings, while another worker modified Nura Sway for a workspace switcher. This is not a failure of Debian's files, which have their own independent test. The six focused Debian regression tests, manifest integrity check, `make check` and `git diff --check` pass. The older Debian mirror's full source-coverage check also sees nine unrelated new Nura reference files absent from its historical source-parity inventory.
