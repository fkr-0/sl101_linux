# NuraBrowser native control IPC

Task: SL101-LINUX-03-CONTROL-IPC-20261110-D62D6B
Implementation: src/control/control.c, control-private.h.
Public ABI: unchanged include/nurabrowser/contract.h.

## Engine lifecycle

Call from the owning GTK/GLib main thread with a live context:

    gboolean nurabrowser_control_start(NuraBrowserContext *ctx,
                                       const char *socket_path, GError **error);
    void nurabrowser_control_stop(NuraBrowserContext *ctx);

NULL socket path binds $XDG_RUNTIME_DIR/nura-browser.sock. A custom path
must be absolute and directly under the exact XDG_RUNTIME_DIR directory;
its basename can contain only ASCII letters/digits, dot, hyphen and underscore.
Runtime directory must be canonical, symlink-free in every component,
owned by effective UID, mode exactly 0700. The socket is 0600.

Pre-existing entries, even stale owned sockets or symlinks, are rejected:
NEVER auto-unlink an occupied socket. On stop, listener and clients are closed;
the node is unlinked only if device and inode still match the bound socket.
Repeated stop is safe. No external thread may call start/stop concurrently.

Peer authentication uses Linux kernel SO_PEERCRED through GLib GSocket's
GCredentials, and accepts ONLY matching effective UID. Missing credentials
fail closed. JSON-claimed UID has no authority. The socket is never exposed
through browser JavaScript or a TCP/HTTP transport. No shell/eval/subprocess
exists in the implementation.

## JSONL protocol

A client can send multiple LF-terminated UTF-8 JSON objects on one stream.
Partial frames are supported, length strictly less than 8192 bytes, excluding
LF. Each object must have string member "command" and optional "argument".

Requests:

    {"command":"open","argument":"https://example.org/"}
    {"command":"back"}
    {"command":"forward"}
    {"command":"reload"}
    {"command":"stop"}
    {"command":"uri"}

The exact command vocabulary is open, back, forward, reload, stop, uri.
Only open requires an argument: string, up to 4096 bytes, passed to the
native navigation dispatcher for HTTP/HTTPS URL validation. Others require
argument absent or JSON null. Unknown members and command names fail closed.

Replies are also one JSON line per request:

    {"ok":true,"result":{"command":"uri","uri":"https://example.org/"}}
    {"ok":true,"result":null}
    {"ok":false,"error":"invalid_json"}

Error code vocabulary: invalid_frame, invalid_utf8, invalid_json,
invalid_request, invalid_argument, unknown_command, navigation_failed,
result_too_large, frame_too_large. Raw GError, private paths, auth data
and internal diagnostic text never appear in error responses. Successful result values come only from nurabrowser_nav_dispatch. Native
navigation B returns serialized JSON snapshots: these are parsed and embedded
as a structured result object rather than a doubly escaped JSON string.
Non-JSON native result strings are still JSON escaped as ordinary strings.
Policy for exposing current URI in that explicit navigation query belongs
to the navigation lane. Raw NUL bytes and Unicode NUL escapes are refused.

## Resource and failure limits

- Maximum 32 clients, each with one async GIO reader and writer.
- Input reads are 2048 bytes, per-frame buffering capped below 8192.
- Output queue capped at 32768 bytes per client; reads pause at 16384.
- Frame length reaching 8192 produces an error then drain-and-close.
- Idle timeout 15 seconds; dedicated host test uses 1 second.
- Async cancellable reads/writes; no waiting on peer I/O in GTK/WPE loop.
- Disconnections, partial writes and stop while pending are handled.
- No dynamic code execution, eval, system, popen, shell or unsafe printf.

## Worker D build and integration handoff

Compile the module using:

    pkg-config --cflags --libs glib-2.0 gio-2.0 gio-unix-2.0 json-glib-1.0

Add src/control/control.c to Meson sources, and gio-unix-2.0 plus json-glib-1.0
to dependencies. The shared ABI header stays coordinator-owned; no changes
to top-level Makefile, Meson, Ansible or other worker lanes were made.
Do not use old libwpe or WPEBackend-fdo; target WPE 2.54+ WPEPlatform.
Engine must call stop before the context is torn down.

## CPU-only host verification

    sh nura-browser/src/control/tests/run-host-tests.sh

This compiles the real module and a fake navigation ABI against installed
GLib/json-glib. For the missing WebKit host package, only an opaque
WebKitWebView type is forward-declared in a test-only stub. The stub does
NOT fake a passing WebKit compile or ARMHF link. Tests include live AF_UNIX
socket interactions, permissions, partial/multiple frames, malformed
JSON and UTF-8, nonmatching/absent credentials, oversized frames,
path/symlink/stale collision, restart and no shell interpretation.

Verified host evidence (10 Nov 2026):

    sh nura-browser/src/control/tests/run-host-tests.sh
    # 13 / 13 passed; -Wall -Wextra -Werror; test idle timeout 1s

    make test && make check
    # 2092 tests, OK (skipped=3); make check exit 0

Some unrelated baseline test commands print expected patch-failure diagnostics
and Python ResourceWarning lines; the aggregate exit status is 0.

Remaining gates: end-to-end foreign-UID Linux peer test (same-UID test only
unit-exercises credential mismatch), WPE WebKit >=2.54 headers and
wpe-webkit-2.0 / wpe-platform-2.0 sysroot dependencies, target GLIBC ARMHF
VFPv3-D16 **without NEON** crosscompile, WebKit sandbox/real navigation,
hardware test and renderer qualification. Device 192.168.23.106 is offline;
no devices were accessed by this task.
