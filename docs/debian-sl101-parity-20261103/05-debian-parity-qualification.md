# Debian SL101 parity qualification — lane 05

Date: 2026-11-03. OCP identity: `SL101-LINUX-05-DEBIAN-PARITY-QUALIFICATION-20261103-04977C`; dispatch attempt `e90102f9ec1e4f92a69ec08a9bbc24d9`. Scope: read-only Debian device/reference and local source assessment. **Result: BLOCKED for native Debian desktop parity acceptance** (host checks green, target OS confirmed, deployment/physical evidence absent).

## Authority and provenance
- Workspace root: `/home/user/code/sl101_linux` (canonical project `sl101_linux`); inspected HEAD `b2d68cac66c23d6f4b14a02c76145ebfb4d745ac`.
- Read `AGENTS.md`, `README.md`, `docs/MIGRATION-20261003.md`, `docs/sl101-device-config/DEPLOY.md`, and `docs/sl101-native-debian-keyboard.md`. Migration explicitly states historic pre-migration OCP bindings stay with android-infra.
- **Control-plane mismatch:** `ocp_tasks(taskId=SL101-LINUX-05-DEBIAN-PARITY-QUALIFICATION-20261103-04977C, workspaceId=ws-7a692a8ebef17395eb378c11d05505fc)` returns *task belongs to a different project*; no matching Debian parity work packet was listed in this workspace. This independently written report does not pretend to submit/adopt a replacement packet. Coordinator must resolve exact canonical task ownership for typed phase result.
- Worktree was dirty before inspection (numerous unrelated files), intentionally left untouched. Report is confined to lane 05's claimed paths. No device mutation, package install, live session, boot or graphics command.
- Source mirror `docs/sl101-device-config/` exists; **`docs/sl101-debian-device-config/` absent**, as are `docs/debian-sl101-parity-20261103/` and `work/debian-sl101-parity-20261103/` before this lane's report. Therefore no Debian mirror file-by-file diff, deployment hashes, approved producer manifest or rollback mapping can be accepted.

## Read-only device proof (not a desktop test)
Command:
```sh
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes user@192.168.23.100 'hostname; cat /etc/os-release | head -6; uname -r; getconf GNU_LIBC_VERSION; command -v labwc foot keyd cog nuraloumi-panel pipewire 2>/dev/null || :; test -d /opt/grate-mesa25-clean && echo grate-dir-present'
```
Exit 0: `sltwrpbootdebian`, Debian 13.7 trixie, kernel `6.18.45`, `glibc 2.41`, `grate-dir-present`; no listed desktop binaries returned in PATH. Separate read-only query `dpkg --print-architecture; systemctl is-system-running; command -v systemctl loginctl dbus-daemon` returned `armhf`, `degraded`, and all three systemd/logind/DBus commands. The degraded system state needs owning lane diagnosis, not an unreviewed service restart.

## Host tests and isolated static checks
| Command | Result | Limits |
| --- | --- | --- |
| `make test` | exit 0; 199 tests, 2.755 s | Host-only unit tests; no Debian device startup/pixels |
| `make check` | exit 0; `python3 -m compileall -q scripts tests src` | Host-only syntax |
| `sh -n` on `sl101-desktop`, `sl101-audio-session`, `sl101-cog-wpe`, `sl101-chvt`, labwc autostart, ALSA restore | pass | Does not execute programs |
| `python3 -m py_compile` on `sl101-terminal-daemon` and `sl101-video-tui` | pass | Does not test runtime |
| `find docs/sl101-device-config -type f | sort | xargs sha256sum` | available as source hash procedure | No Debian counterpart/deployment hashes to compare |
| Native Debian ARM ELF interpreter, GLIBC version, NEON scan | unverified | No reviewed Debian-specific ELF artifact manifest available |
| Native Debian startup, physical keyboard/VT, displayed GPU pixels, browser/PDF/VNC, audio output | unverified | Prohibited for lane 05 to mutate/start live session |

Source fingerprint examples from current dirty checkout: `sl101-desktop` SHA256 `90c9149dffbe56356287b697adfc8395032abc5ccf6be3a6b0c84ebfa953601b`; `sl101-audio-session` `6c07f92a33b44f7ec33ec3d2a1fc1af0da14f85efa81a78a28a65755191d2896`; `labwc/autostart` `4cce248dca14551a490d0919837c70d42c2472746839cc339affd081e7c622fb`; `keyd/sl101.conf` `08ee8b348ccc13cd050dd714bbb23fe08592ee8bb1d1613beb6d67570d3a3d21`. These are **source observations only**, not verified installed file hashes. Full manifest requires producer release snapshot and stable hashes; do not blindly copy this mutable tree.

## Capability decision table
| Capability | Status | Evidence and required owner action |
| --- | --- | --- |
| Native Debian OS and SSH reachability | **working** | Read-only armhf / trixie 13.7 / kernel 6.18.45 / glibc 2.41 |
| Desktop dependencies | **blocked** | labwc, foot, keyd, cog, NuraLoumi, PipeWire not returned in PATH. 02/03 producers publish dependency + artifact manifests; 04 verifies installation |
| Separate Debian config mirror | **blocked** | 01 mirror producer: create Debian-adapted `docs/sl101-debian-device-config/` with exact file manifest; never wholesale Alpine clone |
| systemd/logind/DBus ownership | **unverified** | Existing `sl101-desktop` defaults to seatd, custom /run runtime and forks dbus-daemon; 01 specify systemd user sessions/RuntimeDirectory, permissions, service dependencies and rollback |
| Keymap/VT recovery | **staged only in reference** | keyd, labwc binding and `sl101-chvt` in reference; 01 adapt and 04/05 obtain supervised physical recovery check |
| WM8903 / ALSA restore / PipeWire | **staged only in reference** | OpenRC `/etc/local.d/sl101-alsa-restore.start` must be replaced with Debian service semantics; audio script uses hardcoded uid/runtime/Pulse paths; 01/03 adapt, 04 validate audible output/state |
| Browser, PDF, VNC routing | **staged only in reference** | `sl101-browse`, Cog/WPE chroot launcher, zathura, noVNC scripts exist; 01/03 publish native Debian paths/packages, 04 verify actual rendering/navigation |
| NuraLoumi panel features | **unverified** | labwc autostart references `/opt/nuraloumi/current/nuraloumi-panel`; no target PATH evidence. 03 provide revision-pinned armhf build; 04 prove panel position/session/reload as available |
| Grate Mesa / EGL | **unverified** | /opt directory exists but contains no attested bundle in this qualification. Existing renderer gate accepts kernel `7.0.1-postmarketos-grate`, not 6.18.45. 02 publish native glibc artifact with dynamic loader, required GLIBC symbols, no unsupported NEON and device/kernel-specific tests; 04 must retain pixman recovery |
| Native desktop/pixels/input acceptance | **unverified** | No authorized read-only physical proof; 04 exclusively owns session mutation and should produce session logs, screenshots/pixel hashes and safe VT recovery observations |
| File backups, rollback and deployed hashes | **blocked** | 04 must publish pre-change backup manifest, exact source/build/deploy hashes and recovery commands; 05 must independently compare before acceptance |

## Acceptance criteria and next action
1. **01 config mirror:** complete Debian-native systemd/logind/DBus audio/keyd/VT/browser config with source-to-target mapping and SHA256, explicit rollback and diff against reference mirror.
2. **02 Mesa and 03 apps:** immutable source revisions, build recipes, artifact paths/hashes, `readelf -l -d -V`, `file`, `readelf -A` (or other executable ABI inspection), SONAME dependency closure, native target loader resolution, NEON compatibility test; chroot results on .106 cannot substitute for .100.
3. **04 deployment:** verify exact host and hashes before each phase; deploy only reviewed ready artifacts with backup/rollback; capture bounded native startup, audio, browser/PDF/VNC, pixel and physically supervised input/VT results. No boot-default switch or unsupported acceleration promotion.
4. **05 final review:** compare stable manifests with actual target checksums, classify tested vs staged vs unverified per capability; rerun `make test` and `make check`. Keep Grate7 evidence separate from kernel 6.18.45.
5. **Coordinator:** reconcile task/project mismatch against the original OCP task; do not invent successor task, legacy next.md or falsely complete typed result.

**Current handoff:** BLOCKED on upstream artifacts and live observations, while host-side tests and target OS identity are verified. No hardware/client parity claim is authorized.
