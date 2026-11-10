# NuraBrowser native navigation — worker B handoff

## Ownership and public ABI

- Canonical OCP: `SL101-LINUX-02-NAVIGATION-20261110-83DEEF`
- Source: `nura-browser/src/navigation/navigation.c`,
  `url.{c,h}` and `state.{c,h}`. Public ABI declarations remain
  exclusively in the frozen `nura-browser/include/nurabrowser/contract.h`.
- Test double and host checks: `nura-browser/src/navigation/tests/`.
- No changes to `contract.h`, project Makefile, Ansible, Mesa, engine or
  control lanes. No access to either SL101 device.

The engine must call `nurabrowser_nav_attach(ctx)` **after** creating a valid
`WebKitWebView` and setting the `state_dir` and optional GLib `loop`. It
must call `nurabrowser_nav_shutdown(ctx)` on the same main thread **before**
freeing the context, stopping its main-loop context, or discarding the view.
Repeated attach/shutdown calls are idempotent. The navigation module holds a
strong reference to the view while attached.

The control lane calls
`nurabrowser_nav_dispatch(ctx, command, argument, &response, &error)` only
from the engine's GLib main thread. The command is one of `open`, `back`,
`forward`, `reload`, `stop`, `uri`. Arguments to every command except
`open` must be NULL or empty. `open` accepts only absolute HTTP(S) URLs,
not `about:blank`; no URI is interpreted as shell input or JavaScript.

On success the function allocates **one JSON object string**, e.g.

    {"command":"uri","uri":"https://example.org/","title":"Example","is_loading":false,"can_go_back":false,"can_go_forward":false}

The caller always owns the returned buffer and must `g_free(response)`.
Important for control lane C: the buffer is *already JSON*. Parse/insert it
as a JSON object for `result`, or consciously expose it as a string; never
concatenate an untrusted argument into outbound JSON. On failure `response`
is NULL and a constant-length `G_IO_ERROR` is provided; caller owns
`g_clear_error(&error)`. Navigation reports current URI, title, loading and
back/forward state using WebKit APIs. The URI can be provisional during load.
It is **not** a remote scripting interface.

## URL and runtime validation

`url.c` bounds the original input to 8192 bytes (including a NUL-terminated
C string), requires valid UTF-8 and strict `http://` or `https://`
authority, uses `g_uri_parse`, rejects userinfo, percent escapes and `@`
in authority, invalid ports, raw space/control/backslash, encoded CR/LF/NUL,
and unsupported schemes. Hosts are restricted to ASCII domain names or IP
addresses; IDNs must be passed as ASCII/Punycode. There is no automatic
search-keyword, base URL, or implicit-scheme interpretation.

`navigation.c` checks that the current thread matches the thread which
called attach. Control lane must marshal incoming socket operations into
that thread; this module does **not** spawn threads, run a child process or
perform any DOM injection. Signals `notify::uri`, `notify::title`,
`notify::is-loading`, and `load-changed` refresh the native snapshot.
Handlers and pending timer are destroyed on shutdown.

## Private, atomic session resume

On `WEBKIT_LOAD_COMMITTED`, navigation records the last validated HTTP(S)
URI; burst updates are coalesced with a GLib timeout. Shutdown synchronously
flushes the last committed URI. The state file is
`<ctx->state_dir>/navigation-state.v1` with version header
`NURABROWSER_STATE_V1`, followed by one URL and newline.

- The state directory must **already exist**, be an absolute path, owned by
  the current UID, with exact `0700` permissions. All path components are
  opened with `openat(O_DIRECTORY|O_NOFOLLOW)`. Navigation does not create
  the directory.
- The input state file must be a regular, single-link, same-UID, non-group/
  world-accessible file (maximum 8256 bytes); read uses `O_NOFOLLOW`.
  Corrupt, oversized, unsafe or disallowed URL content is silently ignored.
- Writes use a unique `O_EXCL|O_NOFOLLOW`, mode `0600` temp file in the
  opened directory; fsync/renameat/fsync directory ensures no partial state.
  Renaming over a symlink replaces that link rather than following it.
- On startup, a valid previous URI is loaded only if the WebView has no URL
  (or is still on `about:blank`); an already selected page is not displaced.
  Unsafe or missing state_dir disables persistence but **not** navigation.

**Scope limitation:** persistence is last committed URL, *not* serialized
WebKit in-memory back/forward history, tabs, cookies or WebKit session data.
Back and forward remain fully native for the running WebView. A later browser
session/history feature must be integrated with WebKit's own session
mechanisms rather than scripting page history.

## Reproducible host evidence and integration gate

Host-only fixture compilation:

    sh nura-browser/src/navigation/tests/run-host-tests.sh

It compiles navigation against a deliberately isolated fake
`tests/stubs/wpe/webkit.h`. It checks dispatch, live URI/title/loading
snapshots, back/forward/reload/stop, unsupported commands, injected
credentials/control bytes, arbitrary-length URL rejection, wrong-thread
rejection, signal cleanup, secure state restoration and symlink cases.
**This is not a real WebKit compilation, nor proof of ARMHF or device success.**

The real WPE 2.54+ integration gate must independently run on a host/cross
sysroot containing both packages, with the test stub directory *absent*:

    pkg-config --modversion wpe-webkit-2.0 wpe-platform-2.0
    cc -std=c11 -D_POSIX_C_SOURCE=200809L -fsyntax-only \
       -I nura-browser/include \
       $(pkg-config --cflags wpe-webkit-2.0 wpe-platform-2.0 gio-2.0) \
       nura-browser/src/navigation/navigation.c \
       nura-browser/src/navigation/url.c \
       nura-browser/src/navigation/state.c

Worker D must add the three production `.c` units to `meson.build`.
For the final ARMHF build, use the pinned GLIBC WPE sysroot, ARMv7 Tegra2
VFPv3-D16 **without NEON**, and audit dependencies. Do not disable the
WebKit sandbox. The host executing this lane has neither
`wpe-webkit-2.0.pc` nor `wpe-platform-2.0.pc`; therefore real WPE syntax,
link, ARMHF compile, runtime sandbox, display and GPU tests are still **open
gates**, not recorded as passing.

Upstream API cross-check: WebKit `WebKitWebView.h.in` in
https://github.com/WebKit/WebKit/blob/main/Source/WebKit/UIProcess/API/glib/WebKitWebView.h.in
and WPEPlatform architecture
https://wpewebkit.org/about/architecture.html .
