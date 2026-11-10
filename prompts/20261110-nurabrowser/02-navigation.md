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

# Worker B — native navigation, history, action handler

Canonical OCP Task: `SL101-NURABROWSER-02-NAVIGATION-20261110`
Priority 85. Own ONLY `nura-browser/src/navigation/**` and
`nura-browser/docs/navigation-implementation.md`.

Implement the exact shared ABI in the frozen contract:
`nurabrowser_nav_dispatch(ctx, command, argument, &response, &error)`,
`nurabrowser_nav_attach(ctx)`,
`nurabrowser_nav_shutdown(ctx)`.
Supported commands `open`, `back`, `forward`, `reload`, `stop`,
`uri`. Validate absolute http/https URLs (optionally allow about:blank
for empty startup); do not accept shell/file/javascript/data URI via
remote IPC. Avoid ambiguous authority, credentials or CRLF injection;
length limit ~8 KiB for URL, bounded GError messages.
Stateful navigation callback uses WebKitWebView current URI, loads,
can-go-back/forward and title. No JS DOM injection needed. Implement
native browser session persistence (atomic state file under private
0700 state_dir; no untrusted symlinks; robust read on startup) if
feasible, otherwise clearly isolate it for later and implement tests.
Return one allocated response (caller frees); do not return borrowed
WebKit pointers. Make all WebKit calls on main GLib context. Worker C
will call dispatch from private Unix-socket control; never start separate
threads or invoke subprocess. Headless tests can use fake/stub WebKit
if no development headers, but no pretend integration success.
Provide URL normalization/validation tests and dispatch test fixtures,
with correct signal cleanup and invalid-state handling.
