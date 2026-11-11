# Debian SL101 .100 — CMA/VDE 60-run hardware benchmark

Date: 2026-11-11. Status: COMPLETED; the complete raw result, 60 pipeline
durations and trace have been copied from the actual tablet to the host,
hash-checked and structurally validated.

## Identity, media and environment

- Hostname: sltwrpbootdebian (.100); root /dev/mmcblk1p1
- Kernel: 7.0.1-postmarketos-grate-dmavde1
- Boot ID: b0236ec3-8c7f-4ad6-af5b-9dc9f5e76174
- microSD CID: 03534453553332478030be3f6400b900
- eMMC CID: 7001004d4d43333247447e682c336e00
- Kernel VDE module hash: 625bc023d0df8903f6387b9ff1c7963ed4ebb79eb3a13c8c1884b6ef4fd7b892
- 96-frame H.264 clip: EXACT same bytes as .106, SHA-256
  e554039c0214ca939cea0ecf30081664ee0a89cc2820ca63944102214dbd407c
- Pipeline: filesrc → qtdemux → h264parse → v4l2slh264dec → fakesink sync=false
- 3 prewarm launches, then 60 independent measured decode launches
- Isolated tracefs instance with CMA alloc start/finish/release tracepoints
- AC=1 throughout, battery Charging 85→86%; CPU 1000→1000 MHz;
  temperature 34→35 C.

The benchmark script was extended to require the proper Debian physical
CIDs and hostname, instead of accidentally applying the Nura-specific
Sway requirement. It neither uses KMS nor changes boot images.

## Measured CMA results on .100

| Statistic | p50 | p95 | p99 | Mean |
| --- | ---: | ---: | ---: | ---: |
| H.264 pipeline duration (ms) | 1468.307 | 1504.915 | 1536.296 | 1472.754 |
| Core CMA allocation duration (us) | 388.000 | 1148.250 | 2252.330 | 497.881 |
| Child user CPU time (ms) | 1265.998 | 1313.527 | 1323.441 | 1264.714 |
| Child system CPU time (ms) | 150.155 | 188.381 | 204.010 | 151.320 |

**60/60 full decodes PASS**, 2040 matched CMA allocation start/finish
trace pairs, **2040 CMA release events**, zero trace/parse errors and
zero CMA allocation failures. The 1:1 release count provides evidence
against decoder buffers remaining unreleased in this experiment, but
cannot rule out all forms of memory leaks. The system-wide
cma_alloc_success counter increased by 2142 (it counts events outside
the traced task scope too). nr_free_cma fell from 18432 to 2917 during
the run and later recovered to 4497 pages in a separate read-only
check; CmaFree then measured 17988 kB from CmaTotal 262144 kB,
with MemAvailable 924912 kB. This is **not by itself evidence of a
persistent DMA allocation leak**: free CMA pages can be used for
movable page cache and change due to reclaim/concurrent users.
No further cache-dropping or invasive fragmentation testing was done.

Per successive quartile (15 runs each) average pipeline time (ms):
1469.185, 1481.056, 1466.659, 1474.116; no strong monotonic
timing trend within this single run.

After benchmark, kernel tracer was restored to nop; no private tracing
instances remained. VDE cached_capture=N, video0 and DRM render node
present, and no new DMA/CMA/VDE allocation or async mutex errors found
in kernel messages.

## Correct power history: .106 first tests were ALSO on AC

The user correctly pointed out the initial .106 measurements were NOT
battery powered. The saved source JSON explicitly says AC=1 at both
start and finish for BOTH five-run tests:

| Variant | Tablet and userspace | Power | N | Pipeline p50 |
| --- | --- | --- | ---: | ---: |
| CMA first smoke | .106 Alpine/musl | AC=1, battery 99% | 5 | 879.381 ms |
| Minus-CMA first smoke | .106 Alpine/musl | AC=1, battery 99% | 5 | 902.762 ms |
| Minus-CMA later long | .106 Alpine/musl | AC=0, battery 88% | 60 | 1021.452 ms |
| CMA current long | .100 Debian/glibc | AC=1, battery 85→86% | 60 | 1468.307 ms |

The first two .106 tests do compare kernels on the same device and
on AC. Numerically B minus-CMA p50 was about 2.7% slower than A CMA
for only five measurements each. They are too small and had different
boot/thermal/CPU-frequency histories (B 912→1000 MHz vs A
1000→1000 MHz) to infer a robust performance ranking.

The two longer 60-run data sets are NOT a clean A/B: different physical
tablets and user spaces, AC versus battery, governors/CPU frequencies,
and temperatures. The .100 1468-ms versus .106 1021-ms p50 contrast
must NOT be attributed to CMA. Kernel cma_alloc_finish also occurs
before the extra remap work, so the CMA tracepoint alone does not
measure the remap penalty.

The SAME-DEVICE full A1–B–A2 experiment remains OPEN.

## Reproducibility and evidence

Benchmark source:

    scripts/sl101-dmavde-cma-ab-bench.py

Actual device-run output:

    /root/hwrun/qa-dmavde1/cma-ab-A60-debian-ac-20261111/

Private host-side unmodified evidence (not added to Git):

    work/sl101-100-cma-benchmark-20261111/A60-debian-ac-result.json
    work/sl101-100-cma-benchmark-20261111/A60-debian-ac-pipelines.json
    work/sl101-100-cma-benchmark-20261111/A60-debian-ac-trace.txt
    work/sl101-100-cma-benchmark-20261111/pinned-short-h264-96f.mp4

Checksums:
- result JSON e4c087588946f9e630ed6f84a9414e9e9ef79965fc1593555f186b6a53394ca0
- timings JSON 617012db9fda74b17c8dae9363add1b2e8c3c21d0b5615064ceef15fd79bbb40
- trace text 0feba076151987419b0fc8e9310e617c8e9dbe2319f84e389255aac22e287348

No flash, reboot or KMS change was made as part of this benchmark.
Hardware performance qualified on .100 does not yet imply memory safety
proof or A/B CMA performance parity.
