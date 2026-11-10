# Canonical implementation handoff

@projmgrauth
Set repo: sl101_linux

**Implement real code, not just a plan.** Task is host-only; device
`192.168.23.106` is offline after an unconfirmed RC2 kexec boot. Do NOT
SSH, reboot, flash, KMS test, deploy or touch either real tablet. Preserve all
existing uncommitted work (Mesa, Ansible and sessions) and work ONLY on owned
files. Begin authenticated workspace session in checkout mode, coordinate
claims, checkpoint progress and verify tests. Read `AGENTS.md`,
`nura-browser/README.md` and the immutable cross-lane ABI
`nura-browser/include/nurabrowser/contract.h` first.

Use **WPE WebKit 2.54+ WPEPlatform**, headers `<wpe/webkit.h>`,
`<wpe/wpe-platform.h>`, pkg-config `wpe-webkit-2.0`,
`wpe-platform-2.0`. Not `libwpe` legacy/WPEBackend-fdo and not a
Cog fork. WPE_PLATFORM=headless/wayland/drm; hardware access is out of
scope. Real WebKit API names must be confirmed against installed headers
or upstream WPE 2.54 docs; if headers unavailable, leave explicit
host-crossbuild gate, NEVER fake a passing ARMHF compilation.

Canonical eventual user command: `,browse` ONLY (hard cutover);
no alias manifest and no permanent old `sl101-browse` public executable.
Target Tegra2 ARMHF VFPv3-D16 **without NEON**; private GLIBC WebKit
browser root; WebKit sandbox must not be disabled. No dynamic shell
execution from pages, browser URL input or IPC.

Deliver source files, tests and precise evidence. Leave a concise
implementation handoff with tests, limitations and owned paths. Do not
change `contract.h`, other workers' directories, shared `Makefile`,
`AGENTS.md`, or Ansible while workers run; coordinator integrates.

# Worker A — NuraBrowser engine and lifecycle (real WPEPlatform)

Canonical OCP Task: `SL101-NURABROWSER-01-ENGINE-20261110`
Priority 85. Own ONLY `nura-browser/src/engine/**` and
`nura-browser/docs/engine-implementation.md`.

Implement native C `main.c` with real WPE WebKit 2.54 `WebKitWebView`,
`WPEView`, GMainLoop, WPEPlatform-selected Wayland/headless/DRM backend.
Core `NuraBrowserContext` is defined in immutable shared contract;
init and teardown of nav and control functions are real calls:
`nurabrowser_nav_attach(ctx)`, `nurabrowser_control_start(ctx, socket, &err)`,
`nurabrowser_control_stop(ctx)`, `nurabrowser_nav_shutdown(ctx)`.
Use WPEView close signal to exit and robust WebProcess-crashed/error
handling without busy restart. CLI `--url https://...`,
`--platform headless|wayland|drm`, `--no-control`, `--help`;
allow `WPE_PLATFORM` existing env, never silently assume DRM.
Ensure webpage and context are correctly refcounted. Make explicit
default URL from user args (about:blank permitted).
Secure socket default under `XDG_RUNTIME_DIR`; do not create arbitrary
runtime paths. Exit cleanly on SIGINT/SIGTERM; headless test exit hook
(`--exit-after-ms=N`) for CI, with no external device access.
Keep logic in main.c/engine.c, optional engine private header.
No FFI bindings, no outside UI toolkit.
Provide independent static/API smoke tests inside your owned engine dir
and instructions to compile when development headers are available.
Avoid C++ (unless WebKit source truly demands it). Acceptance: no
deprecated Cog/libwpe source and no fake WebView, real WPE WebKit API,
compilable once worker D's Meson integration is available.
