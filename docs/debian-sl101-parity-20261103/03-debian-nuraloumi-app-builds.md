# Debian ARMv7 application-build lane — 2026-11-03

Canonical OCP identity: `SL101-LINUX-03-DEBIAN-NURALOUMI-APP-BUILDS-20261103-BABFE9` (dispatch `f53668b188924135bd790622a39652dd`). State: **partial / blocked**, not build-qualified. No device mutation.

## Sources inspected and provenance
- `sl101_linux` HEAD `b2d68cac66c23d6f4b14a02c76145ebfb4d745ac`, dirty unrelated changes protected. NuraLoumi checkout HEAD `ea99cb506a25f8a8020af14b2d48caca8688c967`, unrelated untracked files protected.
- Read `AGENTS.md`, `README.md`, migration notes, Alpine config `DEPLOY.md`, Debian glibc overlay/browser qualification, plus NuraLoumi `AGENTS.md`, `ROADMAP.md`, `DESIGN.md`, architecture/contracts, build and linker scripts.
- `nuraloumi/scripts/build-sl101-armv7.sh` targets `armv7-unknown-linux-musleabihf`; demands Alpine sysroot, musl loader, target pkg-config, release Cargo metadata and no-NEON flags. `scripts/armv7-sl101-linker.sh` hardcodes `armv7-alpine-linux-musleabihf`, Alpine CRT/GCC directory, `/lib/ld-musl-armhf.so.1`. Neither is a glibc build.
- Historical Debian ARMHF Mesa overlay and Cog/Firefox private-root evidence are specific to the reference .106, not current .100 native package/runtime validation. Firefox ESR140 was functional on .106 but is not a maintained primary browser security baseline. Browser `--version` is insufficient for no-SIGILL or headed behavior.

## Host-only verification
| Command | Result | Meaning |
| --- | --- | --- |
| `make test` | exit 0, 199 tests, OK | host tests only |
| `make check` | exit 0, Python compileall | host syntax only |
| ws-bridge `exec_command` | error `Tool exec_command not found` | no shell sysroot/ELF/build probe |
| OCP exact task lookup | `belongs to a different project` under `sl101_linux` and legacy `android-infra` | packet binding unresolved |

No glibc artifacts, source/ELF SHA manifest, Debian package inventory, independent review, native startup, GPU tests or device-side verification were produced. The user's coordinator's Debian .100 inventory is not a device readiness proof and was not reprobed.

## Required standalone glibc target
- Rust `armv7-unknown-linux-gnueabihf`, pinned toolchain and `Cargo.lock`, target-specific `PKG_CONFIG_SYSROOT_DIR` and `PKG_CONFIG_LIBDIR`; **isolated** `CARGO_TARGET_DIR` and NuraLoumi snapshot/worktree, never shared source edits.
- Authenticated Debian 13 armhf sysroot with package versions/hashes, Cairo, xkbcommon, freetype, harfbuzz, fribidi, libgcc/CRT and all link dependencies.
- GCC/Clang configured `-march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard`, no NEON or VFP d16-d31; glibc interpreter `/lib/ld-linux-armhf.so.3` with actual `NEEDED` SONAME closure verified against Debian sysroot, not Alpine musl.
- Discover shipping targets from Cargo metadata, include panel, shell, provider probe, thumbnail helper and declared assets; build `--locked --release`, audit via `readelf -h -A -l -d`, `file`, objdump and checksums. Audit instruction streams, not architecture attributes alone.
- NuraLoumi draws Cairo -> wl_shm -> labwc/pixman, without mandatory EGL; software rendering default. Do not enable renderer GPU, autostart or browser acceleration here.

## Package and launcher requirements for config/deploy lanes
Candidates to resolve against **signed Debian trixie armhf indexes**, not claimed available/installed: `labwc`, `foot`, `tmux`, `keyd`, `pipewire`, `wireplumber`, `cog`/WPE, `zathura`, `zathura-pdf-mupdf`, `novnc`/websockify. Firefox must be qualified as an actual headed browser on Tegra20; package ARMHF alone is not evidence of instruction compatibility. Resolve dependencies and supported Debian service names before writing unit/launcher interfaces. OpenRC `/etc/local.d`, Alpine `apk` commands and Nura .106 browser-root bindings must not be copied into native Debian mirror. Preserve `XDG_RUNTIME_DIR`, `WAYLAND_DISPLAY`, session D-Bus, and pixman recovery path. Only lane 04 may install packages, mutate .100 files/services/session or run on-device qualification; .106 remains read-only reference.

## Exact component readiness
| Component | Status | Next evidence |
| --- | --- | --- |
| NuraLoumi panel/shell/providers | blocked | isolated glibc cross-build, ELF no-NEON and SONAME audit |
| NuraLoumi assets/config | requirements staged | source inventory + deterministic artifact manifest |
| labwc/foot/tmux/keyd | blocked | signed Debian armhf versions, installed closure, launch policy |
| PipeWire/WirePlumber | blocked | Debian runtime service and WM8903/audio evidence |
| Cog/WPE and browser | blocked | signed packages, no-SIGILL headed HTML/JS/graphics fixture |
| PDF/noVNC | blocked | packages, dependency verification and client runtime |
| Native .100 deployment | not attempted | reviewed artifacts, identity recheck, lane 04 |

## Next action
Resolve the exact OCP project/packet identity without creating a replacement; restore bounded host shell/toolchain access; independently build from a pinned isolated NuraLoumi snapshot against a hashed Debian armhf sysroot. Publish binaries and hash/dependency manifest under ignored lane-local work, obtain review, and hand it to lane 04. No claim of completion or live parity before actual tests.
