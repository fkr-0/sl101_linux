# Independent ARMHF review — NuraBrowser WPE 2.54.0-2

**Date:** 2026-11-10
**Scope:** genuine host ARMHF cross-build review only, no devices, no
SSH/flash/KMS/reboot/deployment. Original builder ownership preserved.

## Verdict: real executable, runtime release BLOCKED

The application is truly linked with WPE-WebKit 2.54.0-2 and passes
its *application-only* ARMv7/hard-float/VFPv3-D16 audit.

    ELF SHA256:
    1eb3c26c370037c7713250a2ce0cca3e821e9e6bebc8bacab3237d47ce583853

Inside the real development image, our offline audit scanned 148
DT_NEEDED-reachable ELF files. It resolved **all** explicit DT_NEEDED SONAMEs
but found seven libraries with non-D16 FP or NEON attributes, yielding
12 audit findings. These are **production release blockers**.

| Shared library | Attribute finding | Priority |
| --- | --- | --- |
| libc.so.6 | VFPv3 (not D16) + NEONv1 | P0 |
| libm.so.6 | VFPv4; objdump shows vfma.f32 / vfma.f64 | P0 |
| libjpeg.so.62.4.0 | VFPv3 + NEONv1 | P0 |
| libgcrypt.so.20.8.9 | FP for ARMv8 + NEON | P0 |
| libwebp.so.7.2.0 | VFPv3 + NEONv1 | P0 |
| libsharpyuv.so.0.1.2 | VFPv3 + NEONv1 | P0 |
| librav1e.so.0.8.1 | VFPv3 (not D16); needs disassembly | P0 |

objdump independently showed NEON load/store instructions in libc, libwebp
and libsharpyuv, and VFPv4 fused multiply-add instructions in libm.
An ELF attribute may represent optional CPU-dispatched code, so actual
reachability remains a separate issue. With no verified dispatcher, the
strict Tegra2 VFPv3-D16 release gate must fail.

A supplemental scan of WPEWebProcess, WPENetworkProcess and WPEGPUProcess
each traversed 147 ELF files, with zero missing DT_NEEDED SONAMEs and the
same twelve FP/SIMD findings.

## Additional code-review findings

**P1 — insufficient existing CPU gates:** original
nura-browser/scripts/qualify.py checks only selected NEON opcodes and high
registers. It would miss low-register NEON such as vadd.i8 d0,d2,d4,
as well as VFPv4 vfma.f64 d2,d0,d1. The builder worker also committed
packaging/audit-armhf-needed.py during this review; that new checker
correctly finds the five NEON-declaring libraries but does not reject
non-D16 FP attributes or disassemble instructions. Its 148-file/five-tag
report and our 148-file/seven-library report therefore agree in scope but
are *not* equivalent release qualifications. This review adds a stricter
independent verifier; integrate these checks into one canonical release
pipeline after worker claims are released, rather than maintain two
indefinitely.

**P1 — development image is not reproducibly pinned:** only the two WPE
packages (2.54.0-2) have verified SHA256s. Debian unstable packages move,
and the base Docker image uses a mutable tag. The exported
builder-packages.tsv and image digest record installed state after build,
not the exact source snapshot. Pin the entire root dependency set,
package hashes and the base-image digest before any production promotion.

**P1 — DT_NEEDED is not runtime closure:** dynamic loader search paths,
dlopen modules, GStreamer plugins, WPEPlatform modules and child programs
require additional exhaustive discovery. Some GLib/WebKit modules load on
demand; the audit cannot claim those unseen ELF files are safe.

**P1 — sandbox unverified:** presence checks for bwrap and xdg-dbus-proxy
and refusal of sandbox-disabled flags are necessary but do not prove
namespace separation, blocked syscalls or a sandboxed WebProcess.

**P2 — bloated development root:** Debian unstable Mesa/LLVM, QEMU,
compiler and dev headers must not be copied wholesale as a private
runtime root. Restrict to a minimized, audited D16 dependency closure.

## Review-owned checker

Added nura-browser/scripts/audit-runtime-closure.py and
nura-browser/tests/test_runtime_closure.py. The checker recursively resolves
DT_NEEDED via standard ARMHF library paths, guards against symlink escaping
the root, checks ARM hardfloat ABI + SIMD/FP attributes, and optionally
streams objdump to look for NEON / VFPv4 instructions. Attribute-only
inspection explicitly does not count as a passing release audit.

Run in the already built image, from repo root:

    docker run --rm --network none \
      -v "$PWD/nura-browser:/src:ro" \
      -v "$PWD/work/nura-browser-armhf-20261110/out:/out:ro" \
      --entrypoint python3 sl101-nurabrowser-wpe-dev:2.54.0-2 \
      /src/scripts/audit-runtime-closure.py \
        --root / --binary /out/build/nurabrowser-core

For the current root this deliberately exits 1 (blocked). An additional
--full-disassembly pass can inspect selected machine instructions but its
pattern recognizer does not constitute a formal complete ISA proof.

## Remediation required before deployment

1. Build or pin a private ARMHF GLIBC root whose complete runtime closure is
   compatible with ARMv7 VFPv3-D16. Investigate/rebuild all seven flagged
   libraries, especially libm's actual VFPv4 code and libgcrypt's ARMv8 FP
   attribute. A libwebp-only replacement is insufficient.
2. Repeat ISA/ELF and dynamic loader audits across WPE child processes,
   GStreamer/WPEPlatform modules and every shipped ELF; verify SONAME
   mappings against the staged install root, not just the build image.
3. Establish sandbox proof, headless/software runtime tests in a controlled
   namespace, and explicitly authorized device/Grate/Wayland qualification
   only after the tablets are recovered.

**Verification evidence:** ARMHF executable linked; core audit passed;
148 DT_NEEDED ELFs resolved; zero missing direct/transitive SONAMEs; five
NEON-tag libraries plus two outside the D16 FP baseline; WebKit children
similarly blocked. New offline tests: 7/7. Entire NuraBrowser offline suite:
43/43. Repository make test: 2092 OK, 3 skipped. make check: exit 0.
A native WPE runtime, sandbox, device or rendering test was *not* performed.

No changes to immutable contract.h, old builder worker paths, Mesa, Ansible
or either tablet in this independent review.
