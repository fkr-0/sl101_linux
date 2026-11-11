# NuraBrowser — WPEPlatform-native ARMv7 browser shell

This is a NEW native shell against **WPE WebKit 2.54+** with the stable
WPEPlatform API, not a Cog fork. The canonical NuraLoumi public command will
eventually be `,browse`. Implement the browser in isolated C modules and
make the project's existing Cog/browser launcher available only as an
internal diagnostic reference (no permanent dual user-facing aliases).

**Runtime clarification (2026-11-11):** the installed Cog on SL101 .106
already uses WPE WebKit 2.54.0-2, the same exact WebKit shared-library
bytes used by our ARMHF NuraBrowser build. Cog differs by using the legacy
libwpe backend, not an older engine. The confirmed Tegra2 WebP SIGILL is
worked around by the existing private no-SIMD overlay; six other static
ISA-suspect libraries do NOT automatically require six rebuilds.
Repeatable no-NEON QEMU probes and a safe isolated-runtime qualification
plan are in docs/wpe254-tegra2-runtime-investigation-20261111.md.

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

**Historical 2026-11-10 worker restriction:** .106 was unreachable following
RC2 kexec; that four-worker batch was host-only. As of 2026-11-11 the device
is reachable, but this new browser is still NOT authorized for deployment:
its Debian ARMHF WPE 2.54 dependency closure has unresolved Tegra2 ISA risks.
Preserve unrelated Mesa, boot, and session state.

## Native browser navigation (2026-11-11, host-tested)

The single public command (,browse) now supports remote navigation of an
existing WPE WebView through private AF_UNIX JSONL control IPC. It uses
the SAME compiled nurabrowser-core executable, not a second browser or
a public alias:

    ,browse --command uri
    ,browse --command back
    ,browse --command forward
    ,browse --command reload
    ,browse --command stop
    ,browse --command open --url https://example.org/

This requires the prepared private ARMHF root, the browser's same numeric
UID, a private 0700 runtime directory and a 0600 socket. The client checks
kernel peer credentials, frame limits, and I/O timeouts; the navigation
engine remains the URL validation authority. JSON output is suitable for
future NuraLoumi touch/keyboard controls. Host-only tests:

    sh nura-browser/tests/run-remote-host.sh

See docs/remote-control-20261111.md. The WPE 2.54 ARMHF runtime closure
has selected remaining Tegra2 NEON/VFPv4 reachability and sandbox tests;
the NEW WPEPlatform frontend is NOT yet device-qualified. See the
2026-11-11 runtime investigation before proposing library rebuilds.
