# NuraBrowser — WPEPlatform-native ARMv7 browser shell

This is a NEW native shell against **WPE WebKit 2.54+** with the stable
WPEPlatform API, not a Cog fork. The canonical NuraLoumi public command will
eventually be `,browse`. Implement the browser in isolated C modules and
make the project's existing Cog/browser launcher available only as an
internal diagnostic reference (no permanent dual user-facing aliases).

## Source ownership and integration contract

- `include/nurabrowser/contract.h` — **coordinator-owned**, immutable
  cross-worker API for this four-worker batch.
- `src/engine/` — worker A: GLib entry, real WPE WebKit WebView/toplevel,
  signal lifecycle and headless-first startup.
- `src/navigation/` — worker B: native navigation/session logic,
  validated URL handling, main-context callbacks.
- `src/control/` — worker C: private JSONL Unix socket control channel
  with same-UID authentication for NuraLoumi.
- `meson.build`, `tests/`, `packaging/`, `scripts/` — worker D:
  build, offline tests, no-NEON ARMHF package/audit and launcher.

Engine must call the nav attach/start/stop functions declared in the shared
header, with no WebKit callback from a foreign worker thread.
Native browser chrome/navigation belong to the shell+NuraLoumi; there is
no DOM-injection dependency for basic browser UX. Existing Cog+JS is retained
as a diagnostic/reference until hardware-rendered pixel comparisons pass.

## Mandatory platform boundaries

WPEPlatform built-in Wayland/DRM/headless backend can be chosen via
`WPE_PLATFORM`. These are separate hardware qualifications; do not acquire
DRM master during any host-only build. CPU softpipe is the default test mode,
the pinned Grate Mesa prefix is explicit opt-in. WebKit sandboxing and CPU
Tegra2 no-NEON ABI are non-negotiable. A successful compile is **not** device
or GPU qualification.

**User's device .106 is still unreachable following RC2 kexec.** Do not
SSH, reboot, install, or modify either SL101 tablet during this batch.
All four workers must implement and test against repository artifacts/host.
Do not touch the dirty Mesa patch series or unrelated uncommitted files.
