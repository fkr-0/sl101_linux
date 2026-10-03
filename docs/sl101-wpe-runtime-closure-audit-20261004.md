# SL101 WPE full-runtime CPU/ISA closure audit — 2026-10-04

## Why this follow-up exists

The earlier WPE ARMHF audit did **not** cover the complete browser runtime. Its
fetch script downloaded nine selected top-level packages with `apt-get download`
and extracted only those packages into the audit root. It did not resolve and
extract the installed dependency closure.

That distinction became observable on the SL101: a page-load crash was captured
in GDB as SIGILL in the `ImageDecoder` thread inside the deployed
`libwebp.so.7`. The faulting sequence included `vldr d16` and NEON
`vst1.32`, both outside Tegra20's ARMv7-A / VFPv3-D16 / no-NEON contract.
`libwebp7` is a declared dependency of WPE WebKit 2.54.0-2, but it was absent
from the selected-package audit root.

Therefore:

- the previous 136-ELF result remains evidence for those selected package
  objects;
- it is **not** evidence that the complete installed browser root is CPU-safe;
- a full-runtime clean claim now requires the closure audit in this document.

The live browser repair is independently using a rebuilt libwebp 1.6.0 with
NEON disabled. Its archived audit reports six ELF objects, zero failures, with
ARMv7, VFPv3-D16 and hard-float attributes.

## Audit contract

`scripts/sl101-wpe-runtime-closure-audit.py` accepts a **complete prepared
Debian ARMHF browser root**, not a directory of selected package extracts. It:

1. requires `/var/lib/dpkg/status`;
2. resolves the installed recursive `Pre-Depends` / `Depends` closure
   starting from `libwpewebkit-2.0-1` and `cog`;
3. requires dpkg file-list metadata for every package in that closure;
4. discovers every ELF object under the supplied root independently;
5. runs the established ARMHF disassembly/attribute auditor over the entire
   root;
6. fails if any discovered ELF is missing from the audit;
7. fails on every unexpected ISA violation;
8. permits only exact-path failures explicitly supplied with
   `--allow-failure`.

There is deliberately no default allowlist. The historical
`gst-ptp-helper` finding should normally be handled by removing that helper
from the prepared browser root. If a qualification run must retain it as
evidence, the operator has to name its exact path explicitly.

## Usage

Against a fully prepared private root on the host:

    python3 scripts/sl101-wpe-runtime-closure-audit.py /path/to/private-root \
      --json-output work/sl101-wpe-runtime-closure-audit-20261004/full-root-audit.json \
      --text-output work/sl101-wpe-runtime-closure-audit-20261004/full-root-audit.txt \
      --raw-audit-json work/sl101-wpe-runtime-closure-audit-20261004/raw-armhf-audit.json \
      --raw-audit-text work/sl101-wpe-runtime-closure-audit-20261004/raw-armhf-audit.txt

A successful result means the package dependency closure is present and every
ELF object in that supplied root is represented in the ARMv7/VFPv3-D16/no-NEON
audit with no unexpected failures.

It still does not prove JIT-generated instructions or runtime IFUNC/HWCAP
selection. Those remain live execution gates.

## Current evidence and remaining gap

The repository retains the exact WPE engine package and selected-package audit,
but it does not currently retain a complete post-install private root with all
transitive Debian packages. Therefore the host-only WPEPlatform qualifier now
fails closed with `runtime_closure.status=unqualified` until a full-root
closure receipt exists.

This is intentional. The earlier overall green result was too broad after the
libwebp counterexample.

The currently deployed WPE root also upgraded glibc from the base root's
2.41 series to libc6/libc-bin 2.43-6. Any future static loader/libc proof must
audit the **deployed/prepared 2.43 runtime**, not the original 2.41 base tarball.

## Boundaries

This follow-up is offline only. It does not:

- connect to or mutate the SL101;
- alter the active Cog review launcher;
- deploy the rebuilt libwebp;
- run Grate, Skia, GBM/DMA-BUF or WebGL;
- replace host or Nura system libraries.

Live software-first proof remains owned by the existing Cog/WPE qualification
lane and must retain the hardware qualification lock.
