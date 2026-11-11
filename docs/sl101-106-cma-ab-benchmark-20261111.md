# SL101 .106 — CMA vs minus-CMA: physical benchmark gate

Date: 2026-11-11. **No promotion to Debian .100 before this A-B-A gate.**

## Two independently built benchmark kernels

| Phase | Human label | Actual kernel release | Artifact SHA-256 |
| --- | --- | --- | --- |
| A | 7.0.1-pmos-grate-dmavde1 | 7.0.1-postmarketos-grate-dmavde1 | d7781381ee52efb3be6edf885857b2800a4e1e00ce989a63a00955035183d8dc |
| B | 7.0.1-pmos-grate-dmavde1-minus-cma | 7.0.1-postmarketos-grate-dmavde1-minus-cma | 774931dae8224afb78bd2f38272bcfbe6496f3b8db86b600fb26d81f208e4c3d |

The already-completed host A/B gate proved that the source trees differ
only in arch/arm/mm/dma-mapping.c by the CMA remap patch. The kernel
configurations are otherwise identical apart from LOCALVERSION; both
have the same SL101 DTB and 587 matching module paths. **B is NOT yet
booted on .106; do not claim benchmark results for it.**

## Actual hardware qualification of A on .106

Successful normal boot ID:
d31d3cd8-87b9-4dfb-a697-71e4b577f91a.

- GPU first-use/zeroing: **216/216** passing with no RGB/alpha pixel
  mismatches, Sway PID unchanged, no added kernel lines.
- Bilinear/texture sampler matrix: **120/120** passing on the
  existing supervised GPU test oracle, Sway PID unchanged.
- VDE H.264: full decode of 414 frames successful with
  cached_capture=N and cached_capture=Y, mode restored to N.
- 96 decoded I420 frames **bit-exact against FFmpeg software decode**
  after accounting for hardware strides Y=856 and UV=428 versus tight
  software strides Y=854 and UV=427; zero differing pixels/bytes.
- No new DMA/CMA/VDE decoder errors during these workloads. The
  existing wm8903 codec probe warning was also seen on stock .100.

This does **not** establish the effect of the CMA remap on throughput
or allocation latency. It qualifies A's functional behavior only.

The full host repository test suite is not yet green: a separate
Cog-KMS SIGINT session cleanup test timed out in two cases. Do not
interpret the successful kernel tests as blanket CI success.

## Hardware allocation-path evidence

VDE uses DMA_ATTR_NO_KERNEL_MAPPING for its decode buffers. On .106
the kernel exposes tracepoints cma_alloc_start and cma_alloc_finish.
A private, automatically removed tracefs instance can measure the
*underlying* CMA page allocation latency; the complete VDE pipeline
also includes the post-CMA remap, buffer initialization, decoding and
userspace overhead.

A five-repetition **instrumentation smoke test**, not a valid A/B:

- A kernel: 7.0.1-postmarketos-grate-dmavde1
- VDE pipeline median: **879.381 ms**, p95 **947.693 ms**
- CMA core allocation: 170 events, median **1007 μs**, p95 **3042.6 μs**
- Zero CMA allocation failures, CPU start/end 1000 MHz,
  temperature from 28C to 29C.
- Raw evidence (Git-ignored, host):
  work/sl101-106-dmavde1-hwqual-20261111/cma-A-smoke-result.json

**This is insufficient to claim no CMA performance penalty.** The
CMA core tracepoint ends before the patched lowmem remap. Therefore
do not assign the remap cost to the tracepoint's p50/p95/p99 directly.
A separately verified kernel-function kprobe was used for a brief
probe only, but the reproducible benchmark script intentionally uses
private CMA tracepoints and non-invasive end-to-end timing.

## Reproducible A-B-A qualification

Scripts:

- scripts/sl101-dmavde-cma-ab-bench.py
- scripts/sl101-dmavde-cma-ab-compare.py

Each physical run checks actual uname release, pinned module hash,
SD/eMMC IDs, AC, battery, Sway PID, video corpus hash, CPU clock,
thermal state, CMA failures, and trace sample integrity. It prewarms
3 decodes then records **at least 60 independent H.264 decode
pipelines** plus kernel allocation tracepoints, user/system CPU times
and p50/p95/p99. It leaves the production compositor, video module
parameter, global tracer, and display alone.

The required sequence is:

1. **A1**: existing .106 full-CMA kernel; 60 or more measured runs.
2. **B**: after an explicitly backed-up and read-back-verified exact
   8-MiB .106 LNX kernel swap plus its own complete matching module
   directory, normal reboot into the minus-CMA release, then 60 or
   more identical measured runs. Re-run GPU first-use/pixel and
   bit-exact H.264 checks to exclude correctness regressions.
3. **A2**: restore A's exact LNX, normal reboot with recovery confirmed,
   then an equivalent measurement phase to check thermal/time drift.

All three phases must have **different confirmed boot IDs**.
A2 must be the exact same zImage, DTB, module set and corpus as A1.
These are **device operations requiring proven recovery**; do not
replace /boot/extlinux.conf and presume that changes the normal boot.
The actual .106 boot source is the backed-up, physically verified
8-MiB Android-header eMMC LNX slot; exact offset 8,912,896.

Expected device-side use after staging the benchmark script:

    sudo python3 /root/hwrun/qa-dmavde1/cma-ab-bench.py \
      --variant cma --repeats 60 \
      --output /root/hwrun/qa-dmavde1/cma-ab-A1

The corresponding B command changes --variant to minus-cma and output
to cma-ab-B. A2 uses variant cma again and output cma-ab-A2.

After exporting the three result.json files to the host, compare:

    python3 scripts/sl101-dmavde-cma-ab-compare.py \
      A1/result.json B/result.json A2/result.json \
      --output work/sl101-106-dmavde1-hwqual-20261111/cma-aba-result.json

The comparator refuses absent or mismatched data, fewer than 30
repetitions per phase, different video hashes, missing power, low CPU
clock, thermal drift over 6C, A1/A2 median drift over 8%,
module/ABI mismatch or kernel CMA failures. It flags more than 5%
CMA median pipeline overhead, 10% p95 overhead or 20% p99 overhead
as a performance regression. These are operational thresholds,
not formal proofs of memory safety or perfect latency.

The automatic extended measurement was **not completed on this turn**;
the device-side five-run smoke proved only the measurement mechanism.
No minus-CMA flash, benchmark reboot or change to .100 occurred.
The promotion gate is **RED / A-B-A NOT MEASURED**.

## Release gates before .100

Do not flash Debian .100 until:
- A-B-A performance gate is measured and acceptable;
- A and B graphics + VDE correctness evidence is complete, with no
  new DMA/VDE faults, and .106 is restored to intended A state;
- exact .100 bootable ASUS LNX container and original slot rollback
  are verified, physical recovery exists;
- the full repository test suite or relevant release gate failures
  are resolved or explicitly accepted by the operator.

**Current verdict:** the four-patch A kernel is functionally good
on .106. No defensible performance comparison with minus-CMA exists
yet, so an automatic production promotion to .100 would be premature.
