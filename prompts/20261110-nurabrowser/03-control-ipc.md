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

# Worker C — secure NuraLoumi control IPC for the browser

Canonical OCP Task: `SL101-NURABROWSER-03-CONTROL-20261110`
Priority 85. Own ONLY `nura-browser/src/control/**` and
`nura-browser/docs/control-protocol.md`.

Implement exact shared ABI
`nurabrowser_control_start(NuraBrowserContext*, const char*socket, GError**)`
and `nurabrowser_control_stop(NuraBrowserContext*)` using GLib
GSocketService/GSocketListener/GIOChannel/GIO streams and native
GMainContext, no web stack dependency except contract.
Private AF_UNIX socket in `XDG_RUNTIME_DIR`, predictable filename
(e.g. `nurabrowser-control.sock`) with directory owner/0700 and
socket 0600; refuse symlink/path traversal and stale owned socket
collisions. Verify local peer UID via platform
`SO_PEERCRED` / GCredentials and reject foreign users; never
trust claimed uid in JSON. Bounded JSONL messages (<8 KiB) e.g.
`{"command":"open","argument":"https://example.org/"}`, navigation
method dispatch via `nurabrowser_nav_dispatch`. No browser-injected
JavaScript access to control socket; no `eval`, shell, unsafe printf
or whole-file buffering. Error and success are JSON lines with no
secrets leaked. Handle partial reads, multiple clients, newline and
UTF-8, malformed JSON, disconnects, backpressure/timeouts, service
stop/restart, stale socket cleanup, avoid blocking GTK/WPE main loop.
Use json-glib-1.0 if available and document dependency to worker D.
Write explicit protocol document and tests (server fake dispatch, invalid
JSON, wrong user, oversized frames, no shell execution), with exact
CPU-only verification and limitations. Do not modify the shared header.
