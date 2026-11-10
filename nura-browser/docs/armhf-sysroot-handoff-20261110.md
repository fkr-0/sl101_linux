# NuraBrowser WPE 2.54.0-2 ARMHF build preparation

Date: 2026-11-10. Scope: **host-only**, no tablet access, deployment,
runtime sandbox bypass or changes to global Mesa/WebKit.

## Archived inputs verified by SHA-256

The exact ARMHF package inputs are stored only in the ignored work tree:

    work/nura-browser-armhf-20261110/packages/
      libwpewebkit-2.0-1_2.54.0-2_armhf.deb
      libwpewebkit-2.0-dev_2.54.0-2_armhf.deb

- Runtime package SHA256:
  0b3713cae5520fb44a6fcb099b0b23b8f2802bf3e3a57415fc36b9616bc84ffb
- Dev package SHA256:
  8fe43cebac76de223b5e181eaa049bb21f788fb935dd620fdc640e3b440486f9
- Runtime originally archived with prior project evidence
  work/sl101-wpe-armhf-build-qualification-20261003/wpe-audit.
- Development package from the Debian snapshot:
  https://snapshot.debian.org/archive/debian/20260919T000000Z/pool/main/w/wpewebkit/libwpewebkit-2.0-dev_2.54.0-2_armhf.deb

The dev archive was inspected, not substituted by a test-double.
It ships actual headers at
usr/include/wpe-webkit-2.0/wpe/webkit.h and
usr/include/wpe-webkit-2.0/wpe-platform/wpe/wpe-platform.h,
plus ARMHF pkg-config files wpe-webkit-2.0.pc and wpe-platform-2.0.pc
at version 2.54.0. Header checks verified that the SDK declares
webkit_web_view_get_wpe_view() and wpe_view_get_display().

**Additional observed real-header host validation:** GCC 16 completed a
joint -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror -fsyntax-only
pass over all seven production C units, using the *actual* 2.54.0-2 WPE
headers extracted from the ARMHF development package and host GLib, GIO,
GObject, JSON-GLib, libsoup and libwpe headers. Result: exit 0. This is
stronger than a fake-header unit test, but it is **not** target compilation,
linkage, full dependency audit, or runtime proof.

## Why the original Debian 13 builder image was insufficient

The already present Docker image
sl101-wpe-armhf-builder:20261003 includes
arm-linux-gnueabihf-gcc, linker, and objdump. It is based on Debian
trixie / glibc 2.41. Pinned WPE 2.54.0-2 runtime requires ARMHF
libc6 >= 2.43 and additional unstable-era packages (for example ICU 78).

The new image recipe packaging/Dockerfile.armhf-wpe-dev adds Debian unstable
package sources **inside Docker only**, installs real target libraries,
libglib2.0-dev:armhf, libjson-glib-dev:armhf and the two exact pinned WPE
.deb inputs, then verifies the installed WPE versions with dpkg-query.
Docker BuildKit caches downloaded apt packages so retries do not discard
partially completed downloads.

**Important:** only the two WPE packages are SHA-pinned. Other unstable
libraries move over time; the output needs an exact dpkg-version manifest
and complete target ELF dependency closure audit before production use.
This is development bootstrap, not final immutable deployment sysroot.

## Single-command host-only workflow

From repository root:

    sh nura-browser/packaging/prepare-armhf-sysroot.sh --image-only

To build the actual NuraBrowser application as ARMHF:

    sh nura-browser/packaging/prepare-armhf-sysroot.sh

The wrapper verifies both package SHA256s **before** Docker build. It
uses an isolated image sl101-nurabrowser-wpe-dev:2.54.0-2 and compiles
with scripts/build-armhf.sh inside Docker, using its root as the ARMHF
sysroot. The project is mounted read-only, the only writable bind mount
is ignored work/nura-browser-armhf-20261110/out, and the compiler
container runs with --network none and the caller's UID/GID.

The preexisting cross build uses Tegra2 flags:

    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -fno-tree-vectorize

It rejects missing genuine WPEPlatform package metadata and does not
enable WebKit emergency sandbox-bypass flags. No test-only WebKit stubs
are part of this build.

After success, inspect:

    work/nura-browser-armhf-20261110/out/build/nurabrowser-core

Do not confuse a successful application ELF with validation of every
transitive runtime library. The independently required no-NEON dynamic
closure audit and WebKit sandbox/actual rendering are separate gates.
Neither tablet was contacted.

## Actual successful host execution (2026-11-10)

The complete build was executed using the real ARMHF glibc development
packages inside Docker. Initial compilation exposed the strict C11
lstat() feature-test macro gate; the centrally owned meson.build now
passes -D_POSIX_C_SOURCE=200809L. A second invocation compiled and
linked every production source module using arm-linux-gnueabihf-gcc 14.2
and the actual WPEPlatform SDK (2.54.0, Debian 2.54.0-2).

Docker image identity:

    sha256:5d7f46c14a1667aa77a7bc17fcbef9e0910e15fa6dd360540dfebdcb33553a17

Actual core artifact SHA256:

    1eb3c26c370037c7713250a2ce0cca3e821e9e6bebc8bacab3237d47ce583853

Native ARM ELF verification: ELF32 ARM, EABI hard-float,
Tag_CPU_arch v7, Tag_FP_arch VFPv3-D16, no Tag_Advanced_SIMD_arch
and complete objdump NEON/high-VFP-register gate PASS. No target
executable was run. The generated manifest reports
"static-armhf-audited-not-runtime-qualified".

    work/nura-browser-armhf-20261110/out/
      build/nurabrowser-core
      nurabrowser-artifacts.json
      builder-image-id.txt
      builder-packages.tsv
      stage/usr/bin/,browse
      stage/usr/libexec/nura-browser/nurabrowser-core

Local packaging/staging succeeded. The staged launcher SHA256 is
0dcd3f81098600f76a310e4d4a7e826d27e01ec84e38952e5a330c5acf8007b9.
Root repository tests: 2092 tests OK (3 skipped), make check exit 0.
NuraBrowser offline tests: 31/31 passed.

### Hard release blocker: non-NEON target transitive dependency

The target WPE-WebKit library directly declares NEEDED libwebp.so.7.
The currently installed Debian unstable ARMHF libwebp.so.7 has
Tag_Advanced_SIMD_arch: NEONv1 (Tag_FP_arch: VFPv3), which Tegra2 T20
**does not support**. libwebpdemux and libwebpmux had no explicit
NEON attributes, but this is not a complete disassembly audit.

A **new private-root libwebp build with NEON disabled** and subsequent
full dependency-closure/ISA audit are mandatory before any deployment
or runtime qualification. Never copy the unstaged Docker target closure
to the tablet based on this application-core-only PASS. Further runtime
sandbox verification is still required and untouched.

## New actual DT_NEEDED attribute-level closure (blocked)

The read-only auditor `packaging/audit-armhf-needed.py` follows the
application's actual DT_NEEDED entries recursively through the installed
ARMHF multiarch library directories. It checks ARM, hard-float and
`Tag_Advanced_SIMD_arch` on each referenced ELF. It **does not** cover
dynamically loaded plugins, all executable instructions, feature-dispatch
runtime branches or the WebKit sandbox. It never executes ARM code.

Reproduce in the completed development image, on the host only:

    docker run --rm --network none --user "$(id -u):$(id -g)" \
      --mount type=bind,src="$PWD/nura-browser",dst=/src,readonly \
      --mount type=bind,src="$PWD/work/nura-browser-armhf-20261110/out",dst=/out \
      --entrypoint /bin/sh sl101-nurabrowser-wpe-dev:2.54.0-2 \
      -c 'python3 /src/packaging/audit-armhf-needed.py --entry /out/build/nurabrowser-core --output /out/armhf-needed-audit.json'

Observed: exit **1 (intentional fail-closed)**, 148 ARMHF ELF entries,
zero unresolved DT_NEEDED names, and **five** unsafe NEON-attribute
declarations:

| Installed ARMHF library | Observed attribute |
| --- | --- |
| libc.so.6 | NEONv1 |
| libjpeg.so.62 | NEONv1 |
| libgcrypt.so.20 | NEON for ARMv8 |
| libwebp.so.7 | NEONv1 |
| libsharpyuv.so.0 | NEONv1 |

For these five, arm-linux-gnueabihf-objdump -d also emitted NEON-form
instructions (examples `vst3.8`, `vld1.8`, `vaddl.u8`,
`vqsub.u8`). Some libjpeg/libgcrypt output includes
`<illegal reg ...>` disassembly artifacts; treat those as suspicious,
not a proof that instructions on the actual execution path would trap.
The .ARM.attributes alone requires blocking release, regardless of
whether NEON-optimized paths are feature-dispatched.

Detailed machine-readable report:

    work/nura-browser-armhf-20261110/out/armhf-needed-audit.json

**No release approval:** this rolling Debian unstable sysroot is a
development/link environment only. Build a private, fully pinned,
Tegra2-compatible GLIBC closure (including libc, JPEG, gcrypt, webp,
sharpyuv) with no NEON, perform an instruction-level audit on every
shipped ELF plus dlopen-discovered plugins, test loader and sandbox,
and only then consider on-device deployment with separate authorization.
