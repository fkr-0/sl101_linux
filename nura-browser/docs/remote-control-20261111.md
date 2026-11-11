# NuraBrowser — native same-UID remote control (2026-11-11)

## Status

The existing WPEPlatform 2.54 native browser shell has a genuine ARMHF
linked executable, but it is neither Tegra2-runtime-qualified nor installed
on .106. This change adds an actual remote control client to that binary,
without starting another WPE view or changing the pinned Cog fallback.

## Public interface

    ,browse --command uri
    ,browse --command back
    ,browse --command forward
    ,browse --command reload
    ,browse --command stop
    ,browse --command open --url https://example.org/

Exactly one public command remains: ,browse. It runs all existing
private-root provenance and ELF gates, then execs the same native ELF with
an explicit --remote mode before WPE/WebView construction. The native
client uses GIO/GSocket and JSON-GLib to exchange real newline-framed
JSON through XDG_RUNTIME_DIR/nura-browser.sock. No TCP, shell execution,
DOM injection, fake IPC test double, or secondary launcher is used.

## Security and resource contract

- Runtime directory must be absolute, canonical, symlink-free in each
  component, owned by the current UID and exactly mode 0700.
- Socket must be an owned mode-0600 real AF_UNIX socket, not a symlink.
  Kernel SO_PEERCRED must identify the same UID.
- Remote command vocabulary is exactly open, back, forward, reload,
  stop, uri. Only open takes a URL; the service remains the authority
  for HTTP(S) and URL authority/credential/encoded-control validation.
- Requests are bounded to 8191 bytes and replies to 8191 bytes.
  I/O timeouts are 2 seconds. A reply must be one newline-framed
  JSON object with a boolean ok field, and success requires result.
- Failures do not echo user URL text. No socket file is removed or
  replaced by the client. Remote mode creates no WebKit instance.

## Host-only verification

    sh nura-browser/tests/run-remote-host.sh
    sh nura-browser/src/engine/tests/run-host-smoke.sh
    sh nura-browser/src/navigation/tests/run-host-tests.sh
    sh nura-browser/src/control/tests/run-host-tests.sh
    sh nura-browser/tests/run-crosslane-host.sh
    python3 -m unittest discover -s nura-browser/tests -p 'test_*.py'

The new six-case host suite compiles the actual C client and exercises
a real local Unix socket. It covers all six commands, URL arguments,
structured responses, server rejections, invalid requests, unsafe
socket ownership/mode/symlink/runtime paths, oversized replies, missing
newline, embedded NUL and invalid JSON. This does not prove ARM execution.

### Results obtained on 2026-11-11

- Real native client plus launcher: 9/9 unit/integration tests passed.
- Full browser offline Python suite: 50 tests run, 49 passed and one
  expected skip for the independently compiled client harness.
- Engine GLib options: 6/6; native navigation: 6/6;
  control IPC: 13/13; linked navigation+control: 3/3.
- Entire sl101_linux repository: make test 2144 run, 2141 passed
  with 3 skips;
  make check completed successfully; shell syntax and git diff check pass.
- Genuine ARMHF crossbuild against Debian WPE 2.54.0-2, GLib 2.90.1:
  compiled and linked all 9 C objects including remote.c. The ELF is
  ARM EABI5 hard-float VFPv3-D16, with no Advanced SIMD attribute.
  Core ELF SHA256:
  24e55a87aab4c703827d3b9b5f425e10ffd2b08f1866b7a4472f47fcd8846d5c.
- Static ARMHF application qualification: pass (NOT shared-library runtime
  qualification); build manifest generated from the actual ELF and public
  launcher at work/nura-browser-armhf-remote-20261111/artifacts.json.
- No SSH or hardware changes, no tablet deployment, no GUI/pixel proof.

## Remaining gates

1. Resolve non-D16/NEON runtime closure issues among the Debian ARMHF
   WPE 2.54 shared libraries (currently seven ISA suspect libraries).
2. Demonstrate WebKit sandbox, subprocess/plug-in runtime closure,
   protected graphics and real hardware pixels before enabling the new
   browser on .106. Preserve the existing Cog diagnostic path.
3. Bind the IPC to NuraLoumi native address/navigation touch chrome
   in a genuinely same-UID browser session. Never weaken SO_PEERCRED
   or make the socket group/world writable merely to bridge the
   Alpine desktop UID and separate browser UID.
