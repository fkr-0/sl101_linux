# NuraBrowser engine — 2026-11-10 implementation handoff

## Scope and ownership

Canonical OCP task: SL101-LINUX-01-ENGINE-CORE-20261110-55DD25.
Worker A: SL101-NURABROWSER-01-ENGINE-20261110.

Owned: nura-browser/src/engine/** and this documentation file.
The cross-worker include/nurabrowser/contract.h is immutable and unmodified.

Host-only operation: no SSH, KMS, kexec, reboot, flashing, deployments,
or changes to either tablet. Future ONLY public command is ,browse
(worker D owns packaging). No public sl101-browse compatibility alias.

## Files

- src/engine/main.c: real native C main entry and exit handling.
- src/engine/options.h / options.c: GLib options, URL/platform validation.
- src/engine/engine.h / engine.c: WebKit + WPEPlatform + GLib lifecycle.
- src/engine/tests/test_options.c: six compiled offline GLib tests.
- src/engine/tests/run-host-smoke.sh: static API checks, GLib tests and
  conditional WPE 2.54+ native-header syntax gate.

Engine constructs a real WebKitWebView with
g_object_new(WEBKIT_TYPE_WEB_VIEW, NULL), retrieves a real WPEView using
webkit_web_view_get_wpe_view(), and lets WPEPlatform supply the display
and toplevel. There is no Cog fork, legacy libwpe view backend, FFI,
faux WebView, outside UI toolkit or manual framebuffer management.

The engine owns NuraBrowserContext.view and .loop, with a real private
state directory in .state_dir. It attaches WPEView::closed (normal
exit, Wayland), WPEDisplay::disconnected (failure), the WebKit
web-process-terminated signal (nonzero exit, no restart loop), and
load-failed (log error domain+code, default WebKit error page).
SIGINT/SIGTERM and the headless test timeout are GLib sources.

After constructing the real view it invokes nurabrowser_nav_attach(ctx);
if control enabled, it calls nurabrowser_control_start(ctx, socket, &err).
On stop it removes GLib sources, calls nurabrowser_control_stop(ctx),
then nurabrowser_nav_shutdown(ctx), disconnects signals, unreferences the
WebView and GMainLoop and frees state path. The borrowed WPEView and
WPEDisplay are never separately unrefed. Failed control startup still
runs nav teardown; no fake navigation or socket implementation is added.

## CLI and safety

Examples after worker D integration:

    ,browse --url https://example.org --platform wayland
    ,browse --platform headless --no-control --exit-after-ms=1000
    WPE_PLATFORM=wayland ,browse --url https://example.org

--help is provided by GLib. --platform supports headless, wayland, drm.
It overrides an existing WPE_PLATFORM environment value, otherwise that
value is preserved. If neither is specified, the engine **explicitly
chooses headless**, preventing silent DRM acquisition. The default URL
is about:blank. --url accepts only about:blank or absolute HTTP(S)
with a host and without URL credentials or literal control characters.
No positional URI, JS evaluation, shell execution or dynamic command
generation. --exit-after-ms takes 0..3600000 and is rejected on anything
other than headless.

Control-enabled startup requires an existing, canonical, private,
real XDG_RUNTIME_DIR owned by the caller: socket default is
XDG_RUNTIME_DIR/nura-browser.sock. There is no /tmp fallback and no
creation of arbitrary runtime directories. Worker C is responsible for
actual socket mode 0600, SO_PEERCRED validation, bound requests and
main-loop dispatch. --no-control supports standalone CI.

Persistent browser data directory is
g_get_user_state_dir()/nura-browser; final directory must be real,
owned by this UID and mode 0700 (creation explicitly mode 0700).

WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS is rejected; this engine never
disables WebKit sandboxing. The 2022 GLib WPE API excludes the old
WebKitWebContext sandbox setter. Worker D must independently check that
Linux bubblewrap sandbox *actually works* in runtime qualification.

## Verification and integration gate

Offline command:

    sh nura-browser/src/engine/tests/run-host-smoke.sh

Observed result on host, 2026-11-10:

    PASS: static API and integration guards
    ok 1 /nura/engine/defaults
    ok 2 /nura/engine/explicit-platform
    ok 3 /nura/engine/env
    ok 4 /nura/engine/url-rejected
    ok 5 /nura/engine/options-rejected
    ok 6 /nura/engine/env-rejected
    GATE: WPE 2.54+ headers unavailable; real WPE compile/crosslink NOT verified

The GLib-only tests compile with -Wall -Wextra -Werror -Wpedantic and
do not simulate a WebView. The smoke script performs WPE syntax checks
*only* if genuine wpe-webkit-2.0 >= 2.54.0 and wpe-platform-2.0
development headers are installed. A host GLib test or host WPE syntax
check must never be reported as a successful ARMHF link/build.

Worker D's Meson sources MUST explicitly include:

    src/engine/main.c
    src/engine/engine.c
    src/engine/options.c
    src/navigation/navigation.c
    src/control/control.c

At the time of writing worker D's in-progress meson.build listed only
engine/main.c, so a coordination note was sent to .wsbridge:nura-browser
asking that worker to add engine.c and options.c. This worker does not
modify any other lane or the shared Meson file.

Real build gates remain: integrate workers B/C ABI implementations;
crosscompile against real WPE 2.54+ WebKit/WPEPlatform headers; link
for Tegra2 ARMHF VFPv3-D16 **without NEON** in the private GLIBC root;
audit ELF/ABI; test the sandbox and headless signal/crash lifecycles.
No device/graphics qualification has taken place.

## Upstream verification sources (accessed 2026-11-10)

- https://wpewebkit.org/blog/2026-10-06-wpe-platform.html
  Documents new WebView constructor, WPEView getter, closed signal,
  WPE_PLATFORM selection, headless/Wayland/DRM, and legacy API removal.
- https://github.com/WebKit/WebKit/blob/main/Tools/MiniBrowser/wpe/main.cpp
  Demonstrates display disconnect and WebProcess-terminated signals.
- https://github.com/WebKit/WebKit/blob/main/Source/WebKit/UIProcess/API/glib/WebKitWebContext.h.in
  Confirms the modern WPE 2022 GLib API omits old sandbox setter.
- https://github.com/WebKit/WebKit/blob/main/Source/cmake/OptionsWPE.cmake
  Linux bubblewrap sandbox is a build/runtime qualification gate.
