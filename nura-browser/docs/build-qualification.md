# NuraBrowser — Worker D: build / packaging / offline qualification

**Date:** 2026-11-10
**Canonical dispatch:** `SL101-LINUX-04-BUILD-QA-INTEGRATION-20261110-1F5B0A`
**Implementation lane:** `SL101-NURABROWSER-04-BUILD-QA-20261110`
**Scope:** host-only; tablets are offline/unqualified and were not contacted.

## Source architecture and exact ownership

This lane owns `nura-browser/meson.build`,
`meson_options.txt`, `packaging/**`, `scripts/**`,
`tests/**` and this document. No other worker's source or immutable
`include/nurabrowser/contract.h` is changed by Worker D.

Meson uses C11 and an **explicit** source inventory, not a directory glob:

| Lane | Compiled source files |
| --- | --- |
| Engine A | `src/engine/main.c`, `engine.c`, `options.c` |
| Navigation B | `src/navigation/navigation.c`, `state.c`, `url.c` |
| Control C | `src/control/control.c` |

Dependencies: `glib-2.0` (>=2.70), `gio-2.0`, `gio-unix-2.0`,
`gobject-2.0`, `json-glib-1.0`, `wpe-webkit-2.0` (>=2.54.0),
`wpe-platform-2.0`. Runtime API target headers are strictly
`<wpe/webkit.h>` and `<wpe/wpe-platform.h>`; legacy WPEBackend-fdo
and libwpe backends are not linked or installed by this project.
Note: the development headers were **not available** on this host, so C
signature correctness and full linking of the concurrent A/B/C source
changes have not been verified, even though WPEPlatform symbol names in
the archived 2.54.0-2 binaries were checked in the historical qualification.

## Cross-build: correct sequence, no device mutation

The prepared sysroot must contain Debian armhf **glibc** packages
`libwpewebkit-2.0-1=2.54.0-2` and
`libwpewebkit-2.0-dev=2.54.0-2`, as well as the target WPEPlatform,
GLib/GIO/JSON-GLib development and runtime closure. The package-status
check is against the exact sysroot. `pkg-config` is confined to that
sysroot; host package metadata is never used as a crossbuild fallback.
The APT/Dev-package installation itself is owned by the separate
root-preparation/coordinator lane, not this worker.

```sh
# On a build host with a *pre-existing* matching ARMHF sysroot:
sh nura-browser/scripts/build-armhf.sh /absolute/prepared-debian-armhf-root \
    /absolute/output/build-nurabrowser

# Only after compile and ARMHF/no-NEON static ELF audit succeed:
python3 nura-browser/packaging/create-manifest.py \
    --build-dir /absolute/output/build-nurabrowser \
    --output /absolute/output/nurabrowser-artifacts.json

# An integrator may stage installation, never deploy from this lane:
DESTDIR=/absolute/output/stage meson install -C /absolute/output/build-nurabrowser
```

Target flags:
`-march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard`,
plus `-fno-tree-vectorize` for the C application. Meson cross-file
target: ARM little-endian Linux / `arm-linux-gnueabihf`.
The post-compile audit requires ARM ELF + hard-float ABI,
`Tag_CPU_arch: v7`, `Tag_FP_arch: VFPv3-D16`, absence of
`Tag_Advanced_SIMD_arch`, and inspected disassembly without NEON
instructions / D16..D31 or Q registers. If readelf/ARM objdump are
missing or fail, packaging **fails closed**. This still does not
substitute for a complete **shared-library closure** scan, which is a
separate release gate. Never globally replace system Mesa or WebKit.

The manifest hashes the actual built `nurabrowser-core` and launcher
source, installs them at `/usr/libexec/nura-browser/nurabrowser-core`
and `/usr/bin/,browse`, and explicitly marks on-device as untested.
It is an integrity record, **not** a deployment or alias manifest.
There is no public `sl101-browse` compatibility command.

## Launcher policy and integrator handoff

`scripts/launch.sh` installs as the public `,browse` command **inside**
the separately prepared private Debian browser root. It performs no
chroot/mount/SSH/reboot/flash/deploy/KMS operations. Its initial
`--platform` is `headless`; initial `--renderer` is `software`.
`--url` accepts an absolute HTTP(S) URL passed as a quoted argument,
never shell-interpreted. Unknown CLI options and invalid URLs fail.

Before any execution the launcher **requires**:

1. Execution inside the already established private glibc root
   (`NURABROWSER_PRIVATE_ROOT=/`, supplied by its trusted runner).
2. `/etc/nura-browser/private-root-id` exactly containing
   `SL101-NURABROWSER-GLIBC-ARMHF-2.54.0-2`. This marker is **not**
   itself an integrity proof.
3. Externally pinned `NURABROWSER_EXPECTED_STATUS_SHA256` (64 lowercase
   hex characters) matching `/var/lib/dpkg/status`, AND an installed
   `libwpewebkit-2.0-1=2.54.0-2` with architecture `armhf`.
4. `bwrap` and `xdg-dbus-proxy`; absence fails. WebKit emergency
   sandbox-disable env is rejected regardless of its value.
5. Runtime/core ELF identity: ARMv7, hard float, VFPv3-D16, no NEON
   declared attribute. Full no-NEON *instruction* proof and full
   dependency closure remain host artifact gates.

Software mode sets softpipe/swrast and clears private GPU library
overrides. `--renderer grate` requires the private Grate tree at
`/opt/nura-browser/grate` and an externally pinned
`NURABROWSER_EXPECTED_OVERLAY_SHA256` matching the overlay integrity
receipt; no global Mesa path is modified. `--platform wayland` requires
a valid Unix socket; `--platform drm` additionally requires
`NURABROWSER_ALLOW_DRM=1` plus a local DRM character device.
These checks do **not** authorize device tests or prove GPU correctness.
The root integrator must separately provide XDG state/runtime directories
with correct ownership and install the compiled C binary.

**Caution:** A root marker plus a status hash is not an isolated
execution environment by itself. The session/sandbox integrator must
verify and enforce the prepared root's mount/namespace identity and
full dependency-closure manifest *before* invoking `,browse`.
The launcher intentionally cannot create or verify mount namespaces.

## Actual host log and outcomes (2026-11-10)

Complete captured stdout/stderr with trailing numeric `EXIT_CODE` for
these commands is preserved under owned `nura-browser/tests/` files:
`offline-qa-20261110.log`, `repository-make-test-20261110.log`,
`repository-make-check-20261110.log`, `meson-host-configure-20261110.log`,
and `wpe-header-gate-20261110.log`. Meson also retains its diagnostic
log under the temporary host build directory; it is not a passing build.

| Command / gate | Exit | Observed result |
| --- | ---: | --- |
| `sh -n` for each of `nura-browser/scripts/launch.sh` and `build-armhf.sh` | 0 | POSIX shell syntax accepted |
| `python3 -m py_compile nura-browser/scripts/qualify.py nura-browser/packaging/create-manifest.py` | 0 | Python scripts syntactically valid |
| `python3 nura-browser/scripts/qualify.py --mode host` | 1 | **Expected refusal**: missing `wpe-webkit-2.0`, `wpe-platform-2.0` pkg-config modules and `<wpe/webkit.h>`, `<wpe/wpe-platform.h>` development headers |
| `meson setup /tmp/nurabrowser-workerD-offline-meson nura-browser --prefix=/usr -Dlibexecdir=libexec` | 1 | Native C compiler found (GCC 16.2.1), GLib 2.88.3 found; Meson stops at missing `wpe-webkit-2.0` dependency; no fake compilation |
| `python3 -m unittest discover -s nura-browser/tests -p 'test_*.py' -v` | 0 | **22/22 offline tests** (CLI, shell safety, Meson deps, no-legacy API scan, ARMHF flags, native ELF/package rejection, private root and sandbox guards) |
| `sh nura-browser/src/engine/tests/run-host-smoke.sh` | 0 | 6/6 GLib option tests; WPE C syntax check explicitly gated on missing headers |
| `sh nura-browser/src/navigation/tests/run-host-tests.sh` | 0 | 6/6 native-host test-double tests |
| `sh nura-browser/src/control/tests/run-host-tests.sh` | 0 | 13/13 native-host IPC tests |
| `make test` (repository root) | 0 | **2,092 tests**, 3 skipped (the suite emits some nonfatal historical patch/ResourceWarning messages); unrelated repo state preserved |
| `make check` (repository root) | 0 | `python3 -m compileall -q scripts tests src` |

There was no WPE native/ARMHF compilation, no ARMHF executable, and no
on-device verification. The exact native diagnostic was:

```text
Run-time dependency wpe-webkit-2.0 found: NO (tried pkg-config and cmake)
nura-browser/meson.build:21:9: ERROR: Dependency "wpe-webkit-2.0" not found
```

The existing historical package check
`scripts/sl101-wpeplatform-host-qualify.py` and
`scripts/sl101-wpe-runtime-closure-audit.py` document why selected
package ELF checks cannot prove the installed runtime closure: stock
libwebp previously caused a Tegra2 SIGILL from an NEON instruction.
The prepared Debian root must be requalified with those controls and
the post-build loader/ELF audits before **any** device rollout.

## Readiness — independent gates

| Gate | Readiness | Outstanding evidence |
| --- | --- | --- |
| Source/build infrastructure | **Implemented; offline QA passes** | Joint A/B/C review and actual header-compatible C compilation |
| Native host compiled binary | **Blocked** | Matching 2.54+ WPE headers and pkg-config modules |
| ARMHF glibc binary | **Blocked** | Prepared pinned 2.54.0-2 dev sysroot, cross compiler, link and no-NEON ELF/closure audit |
| On-device/WPE rendering | **Not run** | Coordinator-exclusive serial hardware qualification only after recovery from RC2 boot |

No production-default change, no tag or deployment, no private-root
creation, no sandbox weakening and no tablet access occurred in Worker D.
