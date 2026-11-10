# NuraBrowser — coordinated host-only integration review (2026-11-10)

## Scope and source baseline

Project: sl101_linux. Source lanes A/B/D already committed to main before
this integration review:

- A engine: 1ca022a — main.c / engine.c / options.c and host options tests.
- B navigation: d44793c — navigation.c / state.c / url.c and host tests.
- D build: 9482753 — Meson, private-root launch, ARMHF/no-NEON gates.
- C control: C's completed OCP checkpoint was verified and its file claim
  relinquished before integrating the uncommitted AF_UNIX JSONL sources.

No shared contract.h, root Makefile, Mesa, Ansible, session settings, or either
tablet was modified. No KMS/DRM, SSH, flash, deployment or boot operations.

## Concrete integration changes

1. Repaired a committed Meson syntax regression: a set of test declarations
   accidentally contained literal leading '+' patch markers. Meson parses
   the resulting file; configuration then fails **for the right reason**:
   host wpe-webkit-2.0 development package is absent.
2. Meson now registers isolated host tests for A, B, C and one new *linked*
   B+C test. These only run when a full WPE-capable Meson build is possible.
   Independent shell tests can run without it.
3. A real CPU B+C link includes the original navigation and control .c
   files together, tested using a fake WebKit view confined to the test
   include path. The integration sends JSONL over a genuine local AF_UNIX
   socket and checks native open, uri, back, forward, and rejection of
   file:, javascript:, credentials and unknown commands.
4. The public control socket basename is now consistently
   nura-browser.sock, matching the explicit Engine A path and the control
   default. Its location remains the 0700 XDG_RUNTIME_DIR and mode 0600.
5. The native B dispatcher returns a JSON snapshot. The C IPC response
   previously encoded that snapshot again as an escaped string; it now embeds
   valid snapshot JSON as a real object under result. Non-JSON return strings
   remain escaped as strings. Errors remain fixed, non-sensitive codes.
6. Additional offline guards validate Meson source inventories, dependency
   requirements, A/C start/stop ordering, actual socket path and hard-cutover
   launcher policy.

Expected representative wire output:

    {"ok":true,"result":{"command":"uri","uri":"https://example.org/","title":"Example","is_loading":false,"can_go_back":false,"can_go_forward":false}}
    {"ok":false,"error":"navigation_failed"}

## Verification commands

Run from the sl101_linux repository root:

    sh nura-browser/src/engine/tests/run-host-smoke.sh
    sh nura-browser/src/navigation/tests/run-host-tests.sh
    sh nura-browser/src/control/tests/run-host-tests.sh
    sh nura-browser/tests/run-crosslane-host.sh
    python3 -m unittest discover -s nura-browser/tests -p 'test_*.py' -q
    make test && make check

Meson source/gate check:

    meson setup /tmp/nurabrowser-integrate-host-20261110 nura-browser --prefix=/usr -Dlibexecdir=libexec

This must fail on the unavailable wpe-webkit-2.0 dependency until the true
WPEPlatform WebKit 2.54+ development sysroot is provided. It must NOT
skip the web engine and report a successful ARMHF build using test stubs.

## Release gates / blocked work

**Not a shipping browser binary.** Real headers and libraries
wpe-webkit-2.0 >= 2.54.0 and wpe-platform-2.0 are missing from this
host. A real WPE compilation/link, ARMHF VFPv3-D16 no-NEON crossbuild,
full dependency closure / libwebp audit, actual WebKit sandbox
validation, private GLIBC root setup, device/UI testing and Grate/DRM
qualification remain strictly unverified.

Private-root launch is designed for exactly one eventual user-facing command,
,browse. The old sl101-browse remains a legacy device artifact until an
authorized switchover; do not create a compatibility alias or deploy either
version from host-only integration.

Security test scope: mocked credential mismatch is tested, but a real
foreign-UID socket peer was not attempted. The B+C host test uses a fake
WebKit GObject as a navigation test double, never the actual WPE renderer.
Both tablets remain untouched.

The command must not weaken WebKit sandboxing; the private root must verify
its real mount namespace and glibc runtime/dependency closure independently.
