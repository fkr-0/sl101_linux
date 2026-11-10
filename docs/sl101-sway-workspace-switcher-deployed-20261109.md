# NuraLoumi Sway workspace switcher deployed to SL101 Nura — 2026-11-09

## Scope and artifact authority

- Device: `sl101-nura`, `user@192.168.23.106`.
- Exact kernel: `7.0.1-postmarketos-grate`.
- Exact SD CID: `035344534c31323880ac79a543010300`.
- Source: sibling `nuraloumi` repository, commit `ccf7e3a`.
- Release binary: `target/armv7-unknown-linux-musleabihf/release/nuraloumi-sway-workspace-switcher`.
- SHA256: `373d4b9e54426e3df8307ef1df49e6f4fb5f73a5e358db83923b6c3649613a6e`.
- Installed executable: `/usr/local/bin/nuraloumi-sway-workspace-switcher` (mode 0755, root-owned).
- ELF: ARM32 musl, VFPv3-D16, no detected NEON, no upper double registers, no HW divide. ELF inspection and on-device `--help`, `--fixture` succeeded without SIGILL.

## Sway integration

- Active Sway config: `/home/user/.config/sway/config`.
- Config SHA256 before change: `8d9a54631a844c386d9db6404a67388d2114b08028f2d82b9b0379eee02de007`.
- Config SHA256 after change: `fce544a81a51546bb398d192486e977379a0bfc2190994424ecb2c181ea80c83`.
- Replaced only original `$mod+1` through `$mod+9` direct workspace commands with `exec --no-startup-id $ws_picker N`; also added `--release Super_L` and `Super_R` bindings.
- Preserved workspace 10, `$mod+Shift+1..9` move-to-workspace, keyd RightAlt+LeftCtrl+1..9 -> VT, reload and `exec_always /usr/local/bin/sl101-sway-panel`.
- Preserved *live-only* green `output LVDS-1 bg #00b050 solid_color` indicator: this line is not in the repository mirror and MUST be preserved on any future full-config deployment.
- Version in target Sway: 1.12. Reloaded through existing IPC; Sway PID `1634` unchanged.
- The `get_bindings` IPC message is not supported by the installed `swaymsg`; instead the active configuration was verified through `swaymsg -t get_config` (all 9 selectors, both releases, panel hook, green indicator).

## Verification and remaining manual test

- Sway `-C` preflight passed in isolated `WLR_BACKENDS=headless WLR_RENDERER=pixman LIBSEAT_BACKEND=builtin` environment; no second DRM compositor was started.
- Target binary checksum matched staging. On-device `--fixture` showed deterministic workspaces and selected state.
- Live switcher invocation for *already focused* workspace 1, followed by explicit `--release`, exited 0 after 1-second poll; workspace 1 remained focused. Sway and panel PIDs remained `1634` and `3355`. No reboot, keyd reload, or kernel/driver mutation.
- NuraLoumi switcher Rust tests: 19 passed. ARMv7 build-script tests: 3 passed. SL101 focused tests: 5 panel-reload and 3 new workspace switcher tests passed. The earlier keyd/Sway regression was updated to assert the switcher owns Super+digits while preserving all nine VT and move-to-workspace mappings (4 focused tests passed).
- Full SL101 `make test`: **1952 tests passed, 1 skipped** after adapting the previous direct-workspace assertion. `make check` and `git diff --check`: passed.
- **Unverified on physical keyboard:** whether Sway emits `Super_L`/`Super_R` release binding after a held `Super+digit`; verify with actual slider keyboard. Blue-border appearance, visual screenshot quality and latency are not proven by the CLI smoke test.

## Rollback

Device backup: `/home/user/.local/state/sl101-workspace-switcher-rollback-20261109/config.before` (SHA256 `8d9a54631a844c386d9db6404a67388d2114b08028f2d82b9b0379eee02de007`).

Restore only Sway bindings (keeps the binary installed harmlessly):

```sh
cp -p /home/user/.local/state/sl101-workspace-switcher-rollback-20261109/config.before /home/user/.config/sway/config
XDG_RUNTIME_DIR=/run/sl101-desktop-user \
SWAYSOCK=/run/sl101-desktop-user/sway-ipc.10000.1634.sock \
swaymsg reload
```

The IPC socket embeds Sway's PID and must be rediscovered after any compositor restart. Do not overwrite device input/boot configuration during rollback.
