# SL101 7.0.1: CMA A/B release-candidate pair

**Built:** 2026-11-10. **Current verified status 2026-11-11**: four-patch CMA RC successfully flashed, booted and GPU/VDE functionally qualified first on .106, then deployed to Debian .100 and independently boot-confirmed (new boot ID b0236ec3-8c7f-4ad6-af5b-9dc9f5e76174), with 587 modules and working real H.264 VDE decode. The .106 device now runs the minus-CMA control and completed 60 battery-powered decode benchmarks with 2040 traced CMA allocations and no failures. **This battery benchmark is NOT a matched AC-powered A-B-A comparison**; full performance gate remains OPEN. Details in docs/sl101-100-cma-flash-readback-reboot-pending-20261111.md and docs/sl101-106-minus-cma-deployment-20261111.md.

## Artifact identities

| Role | Human-facing label | Actual `uname -r` / kernel module ABI |
| --- | --- | --- |
| **Proposed production RC** | `7.0.1-pmos-grate-dmavde1` | `7.0.1-postmarketos-grate-dmavde1` |
| **CMA-only benchmark control** | `7.0.1-pmos-grate-dmavde1-minus-cma` | `7.0.1-postmarketos-grate-dmavde1-minus-cma` |

`pmos` is the requested *short label*. The original, already-built
kernel ABI uses `postmarketos` spelled out. **Do not use the short
label as a literal `/lib/modules` directory or module `vermagic`**.
Both actual kernel releases must remain unique, so no benchmark module
can be loaded accidentally into the RC or stock kernel.

The immutable production source baseline and configuration are identical
to the existing production 7.0.1-r4 kernel, excluding the deliberately
different `CONFIG_LOCALVERSION` and identical disabled debug-info
settings in both experimental builds.

| Patch | RC | Minus-CMA benchmark |
| --- | --- | --- |
| 0001 ARM CMA lowmem direct-map remap | **ON** | **OFF** |
| 0002 DMA-direct NO_KERNEL_MAPPING zero/sync | ON | ON |
| 0003 VDE cached CAPTURE v2 (module default OFF) | ON | ON |
| 0004 VDE async mutex → semaphore | ON | ON |

### Exact source-diff proof

Both trees were extracted independently from the **same SHA512-pinned
linux-postmarketos-grate-stable source archive** and modified with
zero-fuzz patch application. All three shared patches have byte-identical
SHA-256 hashes.

The complete recursive source-tree comparison (ignoring only intentionally
different provenance marker files) showed **exactly one changed path**:

    arch/arm/mm/dma-mapping.c

The original CMA patch is cleanly forward-applicable with zero fuzz to
the control and reverse-applicable to the full RC; reversing it produces
byte-identical control CMA source. The source/code change for the A/B
experiment is therefore isolated to CMA, not to an unrelated VDE or
DMA-direct optimization.

Both builds use identical `make ARCH=arm LLVM=1
CROSS_COMPILE=arm-linux-gnueabi- ... zImage modules dtbs` options and
the same productive kernel configuration. Only their
`CONFIG_LOCALVERSION` differs. Each must carry its own full
**587-module ABI tree** and independent release archive. Their ARM
board DTB SHA-256 must match exactly; the zImages intentionally differ
due to CMA and release metadata.

## Reproducible host workflow

The complete four-patch RC was built already; its current artifact is:

    work/sl101-prod-dmavde-rc3-20261110/sl101-7.0.1-dmavde1-four-patch-candidate.tar.zst

Pinned SHA-256:

    d7781381ee52efb3be6edf885857b2800a4e1e00ce989a63a00955035183d8dc

Build the independent benchmark control:

    bash scripts/sl101-dmavde-minus-cma-prepare.sh
    SL101_JOBS=12 bash scripts/sl101-dmavde-minus-cma-build.sh
    python3 scripts/sl101-dmavde-minus-cma-package.py

Then verify that CMA is **the only source difference** and both packages
have the same module inventory and DTB:

    python3 scripts/sl101-dmavde-ab-verify.py --deep-source
    python3 -m unittest discover -s tests -p 'test_sl101_dmavde_ab_pair_20261110.py' -v

The checker intentionally fails closed if any additional source file,
Kconfig value, module filename, module vermagic, source patch or DTB
differs unexpectedly, or if source/packed checksums are invalid.
Kernel images are **expected** to differ; comparing their SHA-256 for
equality would falsely reject a correct A/B experiment.

### Verified host artifacts (build completed 2026-11-10)

Both crossbuilds, kernel ABI verifications, portable archives and
full-file integrity checks completed successfully. Independent A/B
verifier output is preserved under:

    work/sl101-prod-dmavde-minus-cma-20261110/evidence/ab-pair-verification.json
    work/sl101-prod-dmavde-minus-cma-20261110/evidence/source-isolation.json

The validator returned **HOST_AB_PAIR_PASS**, with exactly 587 shared
module paths and **identical DTB SHA-256**:

    01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0

| Verified property | Four-patch RC | Three-patch benchmark |
| --- | --- | --- |
| Human label | `7.0.1-pmos-grate-dmavde1` | `7.0.1-pmos-grate-dmavde1-minus-cma` |
| zImage SHA-256 | `79911fc494207ff0607373ceed2ff848e8b6b9252e97599a0e75913965e941aa` | `16772701116246c569ebf3ca956a3d13fa2e2e2c3d11f9d20ac48a870c9aa25e` |
| VDE module SHA-256 | `625bc023d0df8903f6387b9ff1c7963ed4ebb79eb3a13c8c1884b6ef4fd7b892` | `be44097b3fe220fa8083abb7cf7dbbcea396ce28d41e8c15199617b15aecc24b` |
| Portable archive SHA-256 | `d7781381ee52efb3be6edf885857b2800a4e1e00ce989a63a00955035183d8dc` | `774931dae8224afb78bd2f38272bcfbe6496f3b8db86b600fb26d81f208e4c3d` |
| Full module inventory | 587 | 587 |
| Patch count | 4 | 3 (CMA excluded) |
| Kernel and hardware status | Previously booted and GPU/VDE qualified on .106; **staged on .100, not flashed due to low/discharging battery** | **Currently running on .106**; eMMC LNX readback and new boot ID verified, 587 modules, Sway/NuraLoumi/WayVNC; 5-decode smoke, not full A-B-A verdict |

The benchmark archive is:

    work/sl101-prod-dmavde-minus-cma-20261110/sl101-7.0.1-pmos-grate-dmavde1-minus-cma-benchmark.tar.zst

Its SHA-256 is pinned separately in the adjacent `.sha256` file.
The binaries differ because the CMA code and
`CONFIG_LOCALVERSION` differ; neither is an error.

**10/10** dedicated A/B contract regression tests pass. These are
*host* tests, not runtime performance results. The work tree retains
both packages for further per-device boot and graphics qualification.

### Full repository test-suite exception (unrelated to A/B build)

The separate `make test` run completed 2117 cases (3 skipped), but did
**not** pass globally: one source-derived CMA test written by another
review lane contains an overly broad string assertion that mistakes
fixture calls for copied function definitions; one pre-existing Cog KMS
session SIGINT cleanup test timed out after 8 seconds. Neither error
arose in the ten isolated A/B tests, source/patch verification, kernel
linking, module ABI checks, or either packaged release. Track and
repair these tests separately; do not claim whole-tree CI green based
solely on the A/B result.

## Benchmarks for the two *hardware* identities

Run alternating A/B hardware tests only after both recovery procedures
are separately qualified: **.100 has ASUS LNX/eMMC and Debian/microSD
root; .106 has an experimentally confirmed active eMMC Android-header
LNX kernel container with Nura/microSD root** (the precise first-stage
bootloader identity remains distinct/uncertain). The .106 full four-patch
RC booted successfully and was then replaced by the **running minus-CMA**
benchmark kernel. The .100 four-patch release is staged but has not
been flashed because the battery is discharging at 22%. Do NOT execute
blind `kexec`, take over the live Sway DRM master, or treat SD
`/boot/extlinux.conf` as the normal eMMC boot selector.

Use controlled alternating sequences (ABBA or BAAB) **per tablet** with
physical recovery and identical CPU clock, device temperature, AC power,
memory pressure, page-cache state, software stack and benchmark corpus.
A and B may have separate boot container formats for each device, but
must use their same respective zImage+DTB+module checksums across
the devices. For VDE, test both `cached_capture=0` and `=1`.

Measure:
- 4 KiB, 64 KiB, 256 KiB, 1 MiB and 4 MiB CMA allocations/frees,
  at least 500–1000 iterations per size. Record p50/p95/p99 latency,
  allocation failure and buddy/CMA fragmentation.
- First-use BO zeroing and pixel comparison, including the historical
  <256-vertex/BO corruption cases, 216+108 baseline cases,
  indexed draws and reallocation/fence churn. Require **zero** pixel
  mismatches and no fresh DMA data leaks.
- Complete VDE decode with repeatable H.264 samples, frame/CRC matches,
  throughput (FPS), CPU %, peak RSS, and no
  `__mutex_unlock_slowpath`, ref-count, VDE lock or DMA warnings.
- Sway and shell usability on Nura, kernel boot and graphics correctness
  on Debian; kernel Oops/WARN, active kernel localversion, module
  `vermagic` and tested DTB.
- CPU frequency/temperature to distinguish DMA/cache coherence fixes
  from unrelated throttling. Include alternating order to detect drift.

**Promotion criterion:** Prefer four-patch RC if both are stable and
CMA prevents cache-coherence artifacts or imposes no meaningful overall
latency/frame-rate regression. A measurable allocation cost is
acceptable only with an explicit, evidence-based tradeoff in favor
of correctness. **Host compilation alone cannot establish performance
parity**. The minus-CMA package is a benchmark/reference, *not*
an automatic production fallback and never the default boot.

Status of each host and device will be documented explicitly rather
than interpreting an attempted `kexec -e` as a successful reboot.
