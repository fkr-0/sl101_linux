# NuraBrowser: existing Cog/WPE 2.54 headless integration handoff

Date: 2026-11-11. Repo: sl101_linux.
This report supersedes the assumption that the new WPEPlatform app needs
an independently upgraded WPE runtime. Cog already uses the exact
WPE WebKit 2.54.0-2 engine bytes.

## Test target and safety boundary

Target: ASUS SL101 .106, postmarketOS host plus the existing Debian
ARMHF Cog root /opt/sl101-cog-wpe-debian. Cog remains the pinned diagnostic
reference and MUST NOT be overwritten.

- HEADLESS-only; CPU softpipe; WEBKIT_SKIA_ENABLE_CPU_RENDERING=1;
  WEBKIT_USE_SKIA_FOR_COMPOSITION=0 (Cog-compatible software baseline).
- Existing no-SIMD libwebp and libsharpyuv overlays stay ahead of
  stock Debian paths; exact SHA256 hashes are checked.
- All library and launcher mounts live in a newly unshared PRIVATE mount
  namespace. The root's existing /var/tmp is overlaid by a separate
  temporary test directory *inside that namespace only*; the disk
  directory and Cog executable are never overwritten.
- Runs as browser UID 1000, using the pre-existing Cog root and sandbox.
  No live Sway socket, DRI/KMS master, firmware, module, kernel,
  device reboot, rendering override or service restart is requested.
- A hard outer timeout surrounds the native attempt. The inner runner
  explicitly refuses to run in the host's mount namespace.
- WebKit sandbox disable flags are rejected, not used as a workaround.

The actual reviewed runner is
scripts/qualify-cog-runtime-headless.sh. It takes a root-owned
staging directory under /tmp/nurabrowser-smoke-* and the **exact**
core SHA256; it verifies the unchanged Cog WPE shared object, libc,
loader and no-SIMD overrides. The --preflight mode is read-only and
does not attempt a namespace or browser start.

## Source correction: headless result MUST reflect page-load success

Previously --exit-after-ms=N could return 0 simply because a GLib timeout
expired, without any successful WebKit load. This was a false-pass risk.
The engine now listens to actual WebKitWebView load-changed and load-failed
events and only passes a timed headless test when:

1. A WEBKIT_LOAD_FINISHED event has been observed;
2. no main-navigation load-failed event was observed;
3. the deadline expired normally; and
4. no WebProcess crash, display disconnect, view closure or early SIGTERM
   occurred.

The success log is "headless CI PASS" and the failure log includes the
load-finished and load-failed booleans without exposing the page URI.
Non-CI interactive browser behavior remains unchanged. This gate is
necessary but not sufficient: it does not validate visual pixels,
subresource/image decoder exercise, JavaScript behavior or GPU use.

## Exact ARMHF build evidence

Source tree cross-built against the prepared, pinned Debian armhf
WPE WebKit 2.54.0-2 toolchain in
sl101-nurabrowser-wpe-dev:2.54.0-2.
Built binary at ignored workspace path:

    work/nura-browser-armhf-remote-20261111/build/nurabrowser-core

**New ELF SHA256 after the headless-load qualification fix:**

    33485c8e3f20526bdf70504d6ea8cd685f3194c9d329f633932d32a1545293a7

ARM EABI5, armv7, hard-float, Tag_FP_arch: VFPv3-D16, no Advanced SIMD
attribute. This qualifies the application ELF, NOT its complete runtime
closure. Generated manifest:

    work/nura-browser-armhf-remote-20261111/qualified-headless-artifacts.json

Host no-NEON QEMU with the EXACT Cog glibc 2.43-6 loader and libc
successfully launched --help for this revised binary. Separately, the
previous software QEMU sandbox attempt failed with a bubblewrap/QEMU
network namespace error; this was not a WebKit or hardware pass.

## Physical device observations / blocker

An older built ELF SHA256
24e55a87aab4c703827d3b9b5f425e10ffd2b08f1866b7a4472f47fcd8846d5c
was successfully transferred into a temporary root-owned directory
on .106; source/target hashes matched.

The subsequent requested privileged native namespace execution was
**blocked by the execution environment safety gate**. It was not run.

Between this staging and a later read-only preflight, the physical
device's kernel changed from
7.0.1-postmarketos-grate-dmavde1-minus-cma to
7.0.1-postmarketos-grate-dmavde1; the Sway process PID changed,
and the tmpfs staging directory vanished. This is consistent with an
external device reboot, but no restart was initiated by this task.
The read-only preflight properly failed "missing or symlinked stage".
The hardware state had changed, so the test was NOT retried.

**Actual headless browser/WebProcess result on .106: NOT TESTED.**
No new browser or graphics operation was started. No pixel, sandbox
runtime, JPEG/WebP decoder or Wayland qualification is claimed.

The final new ELF hash above has **not** been staged on the device.
The old staged root-owned ELF vanished with the tmpfs reset; a single
short read-only preflight script in /tmp may remain after that check.

## Verification and remaining work

Offline:

    sh nura-browser/src/engine/tests/run-host-smoke.sh
    python3 -m unittest discover -s nura-browser/tests -p 'test_*.py'
    sh nura-browser/tests/run-remote-host.sh
    sh nura-browser/tests/isa/run_no_neon_qemu.sh
    make test && make check

Before another hardware attempt, confirm the intended current kernel
identity/benchmark ownership and stable boot ID. Re-stage the NEW binary
under a fresh root-owned /tmp/nurabrowser-smoke-* path, run the read-only
preflight, then use an explicitly authorized privileged task runner for
the isolated sandboxed headless launch. Do NOT bypass any safety check.
Do not replace Cog or enable GPU/Wayland during this stage.

On a completed native headless run, inspect the real WebProcess/NetworkProcess,
return status, page-load-finished signal, loaded shared library paths,
SIGILL/dmesg, sandbox state, RSS, and cleanup. Only after these pass is a
separate software Wayland and WayVNC pixel test appropriate.
